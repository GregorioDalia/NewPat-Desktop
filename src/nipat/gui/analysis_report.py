"""Printable, case-specific views of archived results. No scientific model runs here."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath

from nipat.gui.results import FIELDS, MISSING, column_description


_PREVIEW_ROWS = 8
_MAX_CURVE_POINTS = 120
_GUIDE_TEXT = {
    "below": ("Il risultato è sotto il limite inferiore", "The result is below the lower limit"),
    "at_lower": ("Il risultato coincide con il limite inferiore", "The result matches the lower limit"),
    "between": ("Il risultato rientra nella fascia intermedia", "The result falls within the middle range"),
    "at_upper": ("Il risultato coincide con il limite superiore", "The result matches the upper limit"),
    "above": ("Il risultato supera il limite superiore", "The result is above the upper limit"),
}


def _text(language, it, en):
    return en if language == "en" else it


def _public_label(value):
    # An imported archive can use a host path as a display name. Only its filename
    # belongs on a portable report. Preserve names and the GUI's family separator.
    parts = []
    for label in str(value).split(" / "):
        windows = PureWindowsPath(label)
        if windows.drive or "\\" in label:
            label = windows.name
        elif PurePosixPath(label).is_absolute() or label.startswith(("~/", "../", "./")):
            label = PurePosixPath(label).name
        parts.append(label)
    return " / ".join(parts)


def _display(value, description, language, *, concise=False, guides=None):
    if value is None or value in MISSING:
        return _text(language, "Non disponibile", "Unavailable")
    if value in description.get("values", {}):
        return description["values"][value]
    if value in ("TRUE", "FALSE"):
        return {"TRUE": _text(language, "Sì", "Yes"), "FALSE": "No"}[value]
    raw = str(value)
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return _public_label(raw)
    if not number.is_finite():
        return raw
    approximate = ""
    if concise and description.get("key") in {
        "CPI", "Log10_CPI", "CPI_medianFF", "Median_fetal_fraction_percent", "mean_contamination",
    }:
        rounded = Decimal(format(number, ".3g"))
        key = description["key"]
        limits = ([Decimal(guides["lower"]), Decimal(guides["upper"])] if guides and key in {"Log10_CPI", "CPI_medianFF"}
                  else [Decimal(1)] if key in {"CPI", "mean_contamination"} else [])
        # Do not make the displayed number cross or coincide with a reference boundary.
        if all((number < limit) == (rounded < limit) and (number > limit) == (rounded > limit) for limit in limits):
            if rounded != number:
                approximate = "≈ "
            number = rounded
            raw = str(number)
    if description.get("scale") == 100:
        # Shift by two decimal places without rounding the recorded significant digits.
        sign, digits, exponent = number.as_tuple()
        raw = str(Decimal((sign, digits, exponent + 2))) if number else "0"
    if language == "it":
        raw = raw.replace(".", ",")
    unit = description.get("unit")
    suffix = f" {unit}" if unit in {"%", "punti %", "percentage points"} else ""
    return approximate + raw + suffix


def _pair(label, value):
    return {"label": label, "value": str(value)}


def _cases(store, run_id, *, notes=None):
    overview = store.overview(run_id)
    lang = store.language
    for group in overview["modules"]:
        if group.get("summary_truncated") and notes is not None:
            scope = " · ".join(str(x) for x in (group["label"], group["marker"]) if x)
            notes.append(scope + " — " + _text(lang, "L’elenco mostra fino a 10.000 righe per tabella. "
                                               "Le altre righe sono consultabili nella tabella originale.",
                                               "The list shows up to 10,000 rows per table. "
                                               "Additional rows are available in the original table."))
        files = {item["id"]: item for item in group["files"]}
        for entry in group["entries"]:
            summary = entry["summary"]
            if summary.get("step_status") != "succeeded":
                continue
            source = files[entry["file_id"]]
            row = entry.get("row", {})
            marker = group["marker"] or row.get("Marker_type") or ""
            if row.get("Marker_type") and marker != row["Marker_type"]:
                continue
            family = entry.get("family_id")
            subject = entry.get("sample_label") or entry.get("family_label") or entry.get("label") or source["name"]
            subject = _public_label(subject)
            if family and _public_label(family) != subject:
                subject = f"{_public_label(family)} ({subject})"
            selection = []
            if entry.get("cutoff") not in (None, *MISSING):
                selection.append(_text(lang, "Pannello", "Panel") + " " + _public_label(entry["cutoff"]))
            if entry.get("analysis"):
                selection.append(_display(entry["analysis"], column_description("Analysis", language=lang), lang))
            step_id = source.get("step_id") or entry.get("step_id")
            identity = [run_id, group["module"], marker, step_id, source["id"], entry.get("row_number"),
                        family, entry.get("sample_id"), subject, row, summary.get("guide_band"),
                        [(m["key"], m["value"]) for m in summary["metrics"]]]
            case_id = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            selection = " · ".join(selection)
            label = " · ".join(str(s) for s in (group["label"], marker, subject, selection) if s)
            case = dict(id=case_id, label=label, module=group["module"], marker=marker, subject=subject,
                        selection=selection, step_id=step_id, file_id=source["id"], row_number=entry.get("row_number"))
            yield case, group, entry, source


def report_case_options(store, run_id):
    """List completed result rows. Distinct selections never share a report ID."""
    notes = []
    cases = [case for case, *_ in _cases(store, run_id, notes=notes)]
    repeated = Counter(case["label"] for case in cases)
    for case in cases:
        if repeated[case["label"]] > 1:
            row = case["row_number"]
            suffix = f" · {_text(store.language, 'riga', 'row')} {row + 1}" if row is not None else ""
            case["label"] += f" · {case['step_id']}{suffix} · {case['id'][:12]}"
    return {"cases": cases, "notes": notes}


def report_cases(store, run_id):
    return report_case_options(store, run_id)["cases"]


def _outcome(entry, module, language, *, concise):
    def t(it, en):
        return _text(language, it, en)

    summary = entry["summary"]
    measures = {m["key"]: m for m in summary["metrics"]}
    primary = {"cpi": "CPI_medianFF", "cpin": "CPI", "contamination": "mean_contamination"}.get(module, "assigned")
    if module == "cpin" and not measures[primary]["available"] and measures["Log10_CPI"]["available"]:
        primary = "Log10_CPI"
    selected = measures[primary]
    valid = selected["available"]
    value = _display(selected["value"], selected, language, concise=concise, guides=summary.get("guide_band"))
    if not valid:
        supports = {"cpi": ("N_sites_mother", "N_sites_father"), "cpin": ("N_sites",),
                    "contamination": ("informative_sites",)}.get(module, ())
        if any(_number(measures[k]["value"]) == 0 for k in supports):
            return t("Risultato non disponibile", "Result unavailable"), t(
                "Il numero di siti utilizzabili è insufficiente per questo confronto.",
                "There are insufficient usable sites for this analysis.")
        return t("Risultato non disponibile", "Result unavailable"), t(
            "I dati registrati per questa analisi non permettono di riportare una stima utilizzabile.",
            "The data recorded for this analysis do not provide a usable estimate.")
    if primary == "assigned":
        total = measures["site_count"]["value"]
        return t(f"Genotipo determinato in {value} siti su {total}", f"Genotype determined at {value} of {total} sites"), t(
            "Il genotipo descrive la combinazione di alleli osservata nel campione in una posizione del DNA.",
            "The genotype describes the combination of alleles observed in the sample at a position in its DNA.")
    if primary == "mean_contamination":
        return t(f"Contaminazione media stimata: {value}", f"Estimated mean contamination: {value}"), t(
            "La stima si basa sulle letture inattese nei siti informativi del campione.",
            "The estimate uses unexpected reads at informative sites in this sample.")
    band = summary.get("guide_band")
    if band:
        explanation = (t("NewPat ha confrontato i marcatori del DNA fetale nel campione materno con quelli del presunto padre. ",
                         "NewPat compared fetal DNA markers in the maternal sample with those of the alleged father. ") if module == "cpi" else
                       t("NewPat ha confrontato i marcatori genetici della madre, del figlio e del presunto padre. ",
                         "NewPat compared genetic markers from the mother, child and alleged father. "))
        low = _display(band["lower"], {}, language)
        high = _display(band["upper"], {}, language)
        explanation += t(f"La fascia intermedia va da {low} a {high} sulla scala logaritmica dell’indice.",
                         f"The middle range runs from {low} to {high} on the logarithmic index scale.")
        if module == "cpi" and band["position"] in {"at_lower", "at_upper"}:
            explanation += t(" Il confronto usa il valore arrotondato dal motore.", " The comparison uses the value rounded by the engine.")
        return t(*_GUIDE_TEXT[band["position"]]), explanation
    title = t("Indice di paternità combinato", "Combined paternity index") if primary == "CPI" else "log₁₀(CPI)"
    return f"{title}: {value}", t("Il confronto con i limiti di riferimento non è disponibile per questo risultato.",
                                    "A comparison with reference limits is unavailable for this result.")


def _number(value):
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _chart(title, kind, x_label, y_label, data):
    return {"title": title, "kind": kind, "x_label": x_label, "y_label": y_label,
            "points": [{"label": str(label), "x": x, "y": y} for label, x, y in data]} if data else None


def _details(store, run_id, case, entry, result):
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)

    module = case["module"]
    overview_metrics = {m["key"]: m for m in entry["summary"]["metrics"]}
    count_keys = (("hom_ref", "heterozygous", "hom_alt", "unassigned") if module in {"dnp-call", "snp-call"} else
                  ("Matching_sites", "Mismatching_sites", "No_obligatory_allele_sites") if module == "cpin" else ())
    if count_keys:
        counts = [overview_metrics[k] for k in count_keys if k in overview_metrics]
        if counts and all(_number(m["value"]) is not None for m in counts):
            title = t("Genotipi osservati", "Observed genotypes") if module.endswith("-call") else t("Confronto dei siti paterni", "Paternal site comparison")
            result["chart"] = _chart(title, "bar", "", t("Numero di siti", "Site count"),
                                     [(m["label"], i, _number(m["value"])) for i, m in enumerate(counts)])
    if module == "cpin" and entry.get("analysis"):
        # A legacy sites file can cover more than the selection printed above.
        # Use the selection-specific native intervals, without plotting a new curve.
        if len(entry.get("curve_file_ids", [])) != 1:
            return
        table = store.curve(run_id, entry["curve_file_ids"][0])
        keys = ("Min_child_reads", "Through_min_child_reads", "Log10_CPI", "N_sites")
    elif module == "cpi" and len(entry.get("curve_file_ids", [])) == 1:
        curve = store.curve(run_id, entry["curve_file_ids"][0])
        rows = curve["rows"]
        points = [(r.get("Iteration"), _number(r.get("Iteration")), _number(r.get("log_CPI"))) for r in rows]
        # Connecting points across an unavailable threshold would invent a curve segment.
        if points and all(x is not None and y is not None for label, x, y in points) and all(
                b[1] - a[1] == 1 for a, b in zip(points, points[1:])):
            if len(points) > _MAX_CURVE_POINTS:
                # Preserve the native endpoints and disclose the sampling of a dense curve.
                last = len(points) - 1
                points = [points[round(i * last / (_MAX_CURVE_POINTS - 1))] for i in range(_MAX_CURVE_POINTS)]
                result["notes"].append(t(f"Il grafico mostra {len(points)} delle {len(rows)} soglie registrate, inclusi gli estremi.",
                                         f"The chart shows {len(points)} of the {len(rows)} recorded thresholds, including both endpoints."))
            result["chart"] = _chart(t("Indice per soglia di letture fetali", "Index by fetal read threshold"), "line",
                                     t("Letture fetali minime", "Minimum fetal reads"), "log₁₀(CPI)", points)
        elif points:
            result["notes"].append(t("La curva contiene soglie o valori non utilizzabili. Consulta la tabella originale.",
                                     "The curve contains unavailable thresholds or values. See the original table."))
        table = curve
        keys = ("Iteration", "log_CPI", "InfSites_mother", "InfSites_father")
    else:
        file_id = entry.get("site_file_id") if not module.endswith("-call") else entry["file_id"]
        if not file_id:
            return
        table = store.table(run_id, file_id, limit=_PREVIEW_ROWS)
        keys = ("chr", "pos1", "pos2", "pos", "GT", "total_count") if module.endswith("-call") else (
            ("chr", "pos1", "pos2", "pos", "contamination") if module == "contamination" else
            ("chr", "pos1", "pos2", "pos", "Status", "Paternity_Index"))
    columns = {c["key"]: c for c in table["columns"]}
    keys = [key for key in keys if key in columns]
    rows = table["rows"][:_PREVIEW_ROWS]
    if not keys or not rows:
        return
    title = (t("Soglie della curva", "Curve thresholds") if "Iteration" in keys else
             t("Intervalli di lettura archiviati", "Archived read intervals") if "Through_min_child_reads" in keys else
             t("Dettaglio dei siti", "Site details"))
    result["table"] = {"title": title, "columns": [columns[k]["label"] for k in keys],
                       "rows": [[_display(row.get(k), columns[k], lang) for k in keys] for row in rows],
                       "note": t(f"Righe mostrate: {len(rows)} di {table['total']}.", f"Rows shown: {len(rows)} of {table['total']}.")}
    if module == "contamination" and "contamination" in keys:
        points = []
        for i, row in enumerate(rows):
            value = _number(row.get("contamination"))
            if value is not None and 0 <= value <= 1:
                locus = ":".join(v for v in (row.get("chr"), row.get("pos") or row.get("pos1")) if v)
                points.append((locus or str(i + 1), i, value * 100))
        result["chart"] = _chart(t("Contaminazione nei siti mostrati", "Contamination at the sites shown"), "bar", "", "%", points)


def build_report(store, run_id, case_id, *, detailed=False):
    lang = store.language
    def t(it, en):
        return _text(lang, it, en)

    selected = next((row for row in _cases(store, run_id) if row[0]["id"] == case_id), None)
    if selected is None:
        raise ValueError(t("Seleziona un risultato completato. Aggiorna l’elenco se l’esperimento è cambiato.",
                           "Select a completed result. Refresh the list if the experiment has changed."))
    case, group, entry, source = selected
    record = store.get_run(run_id)
    step_id = case["step_id"]
    if not any(s["id"] == step_id and s["status"] == "succeeded" for s in record["steps"]):
        raise ValueError(t("La fase selezionata non è completata.", "The selected step has not completed."))
    metrics = {m["key"]: _pair(m["label"], _display(m["value"], m, lang, concise=not detailed,
                                                   guides=entry["summary"].get("guide_band")))
               for m in entry["summary"]["metrics"]}
    for metric in entry["metrics"]:
        if metric["key"] not in metrics:
            metrics[metric["key"]] = _pair(metric["label"], _display(metric["value"], metric, lang))
    facts = {"cpi": ("CPI_medianFF", "paternal_used_at_median", "Median_fetal_fraction_percent"),
             "cpin": ("CPI", "Log10_CPI", "N_sites"), "contamination": ("mean_contamination", "informative_sites"),
             "dnp-call": ("assigned", "site_count", "unassigned"), "snp-call": ("assigned", "site_count", "unassigned")}
    headline, explanation = _outcome(entry, case["module"], lang, concise=not detailed)
    if record["status"] != "succeeded":
        explanation += t(" La fase selezionata è completata; l’esperimento nel suo insieme non risulta completato.",
                         " The selected step completed; the overall experiment is not recorded as completed.")
    result = {"language": lang, "case_id": case_id, "run_id": run_id, "run_name": _public_label(record["name"]), "date": record.get("finished_at") or "",
              "version": record.get("version") or "", "module": group["label"], "marker": case["marker"],
              "subject": case["subject"], "selection": case["selection"], "headline": headline, "explanation": explanation,
              "facts": [metrics[k] for k in facts[case["module"]] if k in metrics], "metrics": [], "chart": None,
              "provenance": [], "table": None, "notes": []}
    family = next((f for f in record["families"] if f["id"] == entry.get("family_id") and f["step_id"] == step_id
                   and f["native_id"] == entry.get("native_family")), None)
    result["subjects"] = []
    if family:
        labels = {sample["id"]: sample["label"] for sample in record["samples"]}
        for role, it, en in (("mother", "Campione materno", "Maternal sample"),
                             ("father", "Presunto padre", "Alleged father"), ("child", "Figlio", "Child")):
            sample_id = family.get(role)
            if sample_id:
                label = _public_label(labels.get(sample_id, sample_id))
                identifier = _public_label(sample_id)
                result["subjects"].append(_pair(t(it, en), identifier if identifier == label else f"{identifier} · {label}"))
    if result["subjects"]:
        result["subject"] = _public_label(entry["family_id"])
    elif entry.get("native_family") and _public_label(entry["native_family"]) != result["subject"]:
        result["subjects"] = [_pair(t("Identificativo nella tabella", "Identifier in the source table"),
                                    _public_label(entry["native_family"]))]
    if not detailed:
        return result
    result["provenance"] = [_pair(t("Fase", "Step"), step_id), _pair(t("Tabella del risultato", "Result table"), source["name"])]
    if case["row_number"] is not None:
        result["provenance"].append(_pair(t("Riga dati", "Data row"), case["row_number"] + 1))
    if entry.get("native_family"):
        result["provenance"].append(_pair(t("Famiglia nella tabella", "Family in the source table"), _public_label(entry["native_family"])))
    for k, value in entry.get("row", {}).items():
        if k in FIELDS and k not in metrics and k not in {"Trio", "Pair", "Analysis", "Cutoff", "Marker_type", "individuo"}:
            column = column_description(k, language=lang)
            metrics[k] = _pair(column["label"], _display(value, column, lang))
    result["metrics"] = list(metrics.values())
    if group["warnings"] or any(w.get("step_id") in (None, "", step_id) for w in record["warnings"]):
        result["notes"].append(t("L’esperimento contiene avvisi. Consulta i dettagli della fase in NewPat.",
                                 "The experiment contains warnings. Review the step details in NewPat."))
    try:
        _details(store, run_id, case, entry, result)
    except (OSError, ValueError):
        result["notes"].append(t("Il dettaglio per sito o per soglia non è disponibile nell’archivio.",
                                 "Site or threshold details are unavailable in the archive."))
    return result
