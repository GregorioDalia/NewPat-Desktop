"""Resolve a figure from the exact archived result selected for a detailed report."""
from __future__ import annotations

from itertools import islice
import math
from pathlib import Path
import re

from nipat.errors import ValidationError
from nipat.execution.tracking import input_stat_snapshot
from .analysis_report import _cases
from .igv import LocalIGV
from .references import reference_files
from .results import _read_count, _rows, _scoped


# Report a reproducible example, not a ranking by the strength of the evidence.
_PREVIEW_ROWS = 256
_WINDOW_FLANK = 60


def _site(store, case, group, entry, run):
    module, marker = case["module"], case["marker"]
    if module == "cpi" or entry.get("analysis") or marker not in {"SNP", "DNP"}:
        # A prenatal curve and legacy postnatal selections do not locate the
        # subset's contributing variants. Never substitute another result.
        return None
    if module.endswith("-call"):
        file_id = case["file_id"]
    else:
        count = "N_sites" if module == "cpin" else "informative_sites"
        if not _read_count(entry.get("row", {}).get(count)):
            return None
        file_id = entry.get("site_file_id")
    sources = [f for f in group["files"] if f.get("canonical") and f.get("step_id") == case["step_id"]
               and f.get("marker") == marker and f.get("module") == module and f.get("kind") == "table"]
    if module == "cpin":
        sources = [f for f in sources if f.get("family_id") == entry.get("family_id")
                   and f.get("native_family") == entry.get("native_family")
                   and f["name"].endswith(("_sites.txt", "_sites.tsv"))]
    elif module == "contamination":
        sources = [f for f in sources if f.get("sample_id") == entry.get("sample_id")
                   and f.get("native_name") == entry["row"].get("individuo")
                   and f["name"].startswith("contamination_") and f["name"] != "contamination_summary.txt"]
    else:
        sources = [f for f in sources if f["id"] == file_id]
    if len(sources) != 1 or sources[0]["id"] != file_id:
        return None
    path = _scoped(run, sources[0]["relative_path"], file=True)
    stamp = input_stat_snapshot(path.stat())
    # Do not attach a location from a changed or unauthenticated native table.
    digest = sources[0].get("recorded_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        return None
    store.verify_count_table(path, digest)
    selected = None
    for number, row in enumerate(islice(_rows(path), _PREVIEW_ROWS), 1):
        chrom = row.get("chr", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", chrom):
            continue
        if module.endswith("-call") and (row.get("GT") not in {"0/0", "0/1", "1/1"}
                                        or ("total_count" in row and not _read_count(row["total_count"]))):
            continue
        if module == "cpin" and row.get("Status") != "eligible":
            continue
        if module == "contamination":
            try:
                fraction = float(row.get("contamination", ""))
            except ValueError:
                continue
            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                continue
        start, end = (row.get("pos"), row.get("pos")) if marker == "SNP" else (row.get("pos1"), row.get("pos2"))
        if not all(isinstance(p, str) and re.fullmatch(r"[1-9][0-9]{0,9}", p) for p in (start, end)):
            continue
        if marker == "DNP" and int(end) <= int(start):
            continue
        preferred = (row.get("GT") in {"0/1", "1/1"} if module.endswith("-call") else
                     fraction > 0 if module == "contamination" else row.get("Paternity_status") == "mismatch")
        if selected is None or preferred:
            selected = (chrom, int(start), int(end), number, preferred)
        if preferred:
            break
    return selected if stamp == input_stat_snapshot(path.stat()) else None


def _sample_ids(case, entry, families):
    if case["module"] != "cpin":
        return [entry.get("sample_id")] if entry.get("sample_id") else []
    matches = [f for f in families if f["step_id"] == case["step_id"] and f.get("module") == case["module"]
               and f.get("marker") == case["marker"] and f["id"] == entry.get("family_id")
               and f["native_id"] == entry.get("native_family")]
    if len(matches) != 1:
        return []
    ids = [matches[0].get(role) for role in ("mother", "father", "child")]
    return ids if all(ids) and len(set(ids)) == 3 else []


def _recorded_identity(path, evidence):
    recorded = evidence.get(str(path))
    if not recorded or not path.is_absolute():
        return None
    current = input_stat_snapshot(path.stat())
    return current if all(recorded.get(k) == v for k, v in current.items()) else None


def _recorded_reference(reference, evidence):
    if not reference.get("fasta") or reference.get("historical_identity_incomplete"):
        return False
    files = reference_files(Path(reference["fasta"]))
    for path, key in zip(files, ("fasta_sha256", "index_sha256", "gzi_sha256")):
        stamp = _recorded_identity(path, evidence)
        digest = evidence.get(str(path), {}).get("sha256")
        if not stamp or (digest and digest != reference.get(key)):
            return False
    return True


def _tracks(sample_ids, mapping, tracks, evidence):
    selected, identities = [], {}
    for identifier in sample_ids:
        matches = [r for r in mapping if isinstance(r, dict) and r.get("sample_id") == identifier]
        if len(matches) != 1:
            return [], {}
        sample = matches[0]
        name = sample.get("biological_id") or identifier
        options = [t for t in tracks if t["name"] == name and t["path"] == sample.get("original_path")]
        if len(options) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", name):
            return [], {}
        path = Path(options[0]["path"])
        if path.suffix.lower() != ".bam" or path in identities:
            return [], {}
        indices = [i for suffix in (".bai", ".csi") for i in (Path(str(path) + suffix), path.with_suffix(suffix))
                   if str(i) in evidence]
        if not indices:
            return [], {}
        index = indices[0]
        for source in (path, index):
            stamp = _recorded_identity(source, evidence)
            if not stamp:
                return [], {}
            identities[source] = stamp
        selected.append({"name": name, "path": str(path), "index": str(index)})
    return selected, identities


def report_igv_views(store, run_id, case_ids, register):
    """Return only loopback resource URLs, never paths from the archived run."""
    def t(it, en):
        return en if store.language == "en" else it

    views = dict.fromkeys(case_ids)
    record = store.get_run(run_id)
    metadata = store.metadata(run_id)
    mapping = record["recorded_parameters"].get("sample_mapping") or []
    evidence = {r["path"]: r for r in metadata.get("inputs", []) if isinstance(r, dict) and isinstance(r.get("path"), str)}
    reference, tracks = store.igv_sources(run_id)
    run = store._run(run_id)
    reference_cache = {}
    no_files = t("FASTA, BAM o indici originali non disponibili o non verificabili per questi campioni.",
                 "The original FASTA, BAMs or indexes are unavailable or cannot be verified for these samples.")
    for case, group, entry, _ in _cases(store, run_id):
        if case["id"] not in views:
            continue
        view = views[case["id"]] = {"available": False}
        try:
            locus = _site(store, case, group, entry, run)
            if not locus:
                view["reason"] = t("Nessuna coordinata utilizzabile per questa selezione nell’anteprima dei siti archiviati.",
                                   "No usable coordinate for this selection in the archived site preview.")
                continue
            chrom, start, end, number, preferred = locus
            site = f"{chrom}:{start}-{end}"
            reason = t("primo sito utilizzabile", "first usable site")
            if preferred:
                reason = {"cpin": t("prima incompatibilità paterna registrata in un sito incluso",
                                    "first recorded paternal mismatch at an included site"),
                          "contamination": t("prima stima per sito maggiore di zero", "first positive site estimate")
                          }.get(case["module"], t("primo genotipo con allele alternativo",
                                                   "first genotype with an alternate allele"))
            note = t(f"Riga dati {number}: {reason} nelle prime {_PREVIEW_ROWS} righe. Il sito illustra solo questa posizione.",
                     f"Data row {number}: {reason} within the first {_PREVIEW_ROWS} rows. The site illustrates this position only.")
            view.update(site=site, marker=case["marker"], selection_note=note, reason=no_files)
            ids = _sample_ids(case, entry, record["families"])
            if not ids or not _recorded_reference(reference, evidence):
                continue
            selected, identities = _tracks(ids, mapping, tracks, evidence)
            if not selected:
                continue

            def register_track(path):
                # Pin each HTTP range response to the same recorded BAM and index.
                return register(path, expected_identity=identities[path])

            igv = LocalIGV(register_track, language=store.language, register_reference=register)
            prepared = igv.prepare({"reference": reference, "tracks": selected, "locus": site},
                                   reference_cache=reference_cache, require_locus=True)
            name = prepared["locus"].rsplit(":", 1)[0]
            length = next(c["length"] for c in prepared["chromosomes"] if c["name"] == name)
            views[case["id"]] = {"available": True, "site": site, "reference_site": prepared["locus"],
                                 "selection_note": note, "marker": case["marker"],
                                 "locus": f"{name}:{max(1, start - _WINDOW_FLANK)}-{min(length, end + _WINDOW_FLANK)}",
                                 "chromosomes": prepared["chromosomes"], "reference": prepared["reference"],
                                 "tracks": prepared["tracks"], "samples": [s["name"] for s in selected],
                                 "build": reference.get("build") or "custom"}
        except (OSError, KeyError, TypeError, ValueError, ValidationError):
            view["reason"] = no_files if "site" in view else t(
                "La tabella dei siti è assente, è cambiata o non è verificabile.",
                "The site table is missing, has changed or cannot be verified.")
    for case_id, view in views.items():
        if view is None:
            views[case_id] = {"available": False, "reason": t("Selezione non più disponibile.",
                                                              "The selection is no longer available.")}
    return views
