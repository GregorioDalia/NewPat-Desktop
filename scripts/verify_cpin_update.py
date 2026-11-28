"""Verify the installed postnatal workflow against independent analytical loci."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

# Embedded Python excludes the script directory from its default search path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from newpat.errors import NewPatError, ValidationError
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.workflows import Workflows
from newpat.paths import ProjectLayout
from verify_contamination_update import check_bundled_run, check_number, read_tsv


def check_outputs(run_dir: Path, marker: str) -> None:
    output = run_dir / "output"
    trio = f"MotherM1-FatherF1-ChildC1_{marker}s"
    epsilon = 0.001 if marker == "SNP" else 0.0000892303778101497
    expected_cpi = 1.25 * (epsilon / .4) ** 2 / .6
    rows = read_tsv(output / "Summary_Postnatal_CPI.txt",
                    {"Trio", "N_sites", "Log10_CPI", "CPI", "Mismatch_probability"})
    if len(rows) != 1 or rows[0]["Trio"] != trio or rows[0]["Marker_type"] != marker:
        raise ValidationError("Postnatal CPI: expected one result for the requested trio and marker type.")
    row = rows[0]
    for key, expected in {
        "N_sites": 5, "N_hom_hom": 1, "N_hom_het": 3, "N_het_hom": 0, "N_het_het": 1,
        "Matching_sites": 2, "Mismatching_sites": 2, "No_obligatory_allele_sites": 1,
        "Maternal_incompatible_sites": 1, "CPI": expected_cpi,
        "Log10_CPI": math.log10(expected_cpi), "Mismatch_probability": epsilon,
    }.items():
        check_number(row[key], expected, f"Postnatal CPI {marker}: {key}")
    sites = read_tsv(output / f"{trio}_sites.txt", {"Status", "Paternity_status", "Paternity_Index"})
    expected_sites = [
        ("eligible", "match", 1.25), ("eligible", "match", 1 / .6),
        ("eligible", "mismatch", epsilon / .4), ("mother_child_incompatible", "NA", None),
        ("quality_filter", "NA", None), ("quality_filter", "NA", None),
        ("eligible", "mismatch", epsilon / .4), ("father_unassigned", "NA", None),
        ("eligible", "no_obligatory_allele", 1),
    ]
    position = "pos" if marker == "SNP" else "pos1"
    if len(sites) != len(expected_sites) or {int(s[position]) for s in sites} != set(range(1, 10)):
        raise ValidationError("Postnatal CPI: expected all nine distinct loci.")
    for site in sites:
        status, paternity, pi = expected_sites[int(site[position]) - 1]
        if (site["Status"], site["Paternity_status"]) != (status, paternity):
            raise ValidationError(f"Postnatal CPI: unexpected classification for locus {site[position]}.")
        if pi is None:
            if site["Paternity_Index"] != "NA":
                raise ValidationError("Postnatal CPI: excluded locus has a numerical PI.")
        else:
            check_number(site["Paternity_Index"], pi, f"Postnatal CPI {marker}/{site[position]}: PI")
    if (output / "curves").exists() or any(output.rglob("*.pdf")):
        raise ValidationError("Postnatal CPI: unexpected legacy curve or plot output.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", help="prefisso opzionale delle due nuove esecuzioni")
    args = parser.parse_args()
    layout = ProjectLayout.discover()
    try:
        if layout.project_dir != Path(__file__).resolve().parents[1]:
            raise ValidationError("Usare la venv di questa repository e verificare NEWPAT_PROJECT_DIR.")
        fixture = layout.project_dir / "tests/fixtures/cpin"
        workflow = Workflows(layout, DockerComposeRunner(layout))
        for marker in ("SNP", "DNP"):
            directory = fixture / marker
            originals = {path: path.read_bytes() for path in directory.iterdir()}
            run_dir = workflow.cpin(input_dir=directory, trios="M1:F1:C1",
                                    popfreq=directory / "population.txt",
                                    run_name=f"{args.run_name}-{marker.lower()}" if args.run_name else None)
            print(f"Risultati CPIN {marker}: {run_dir}", flush=True)
            if any(path.read_bytes() != data for path, data in originals.items()):
                raise ValidationError("CPIN: un input originale è stato modificato.")
            check_outputs(run_dir, marker)
            check_bundled_run(run_dir, layout, workflow="cpin")
    except (NewPatError, OSError) as exc:
        print(f"Verifica CPIN fallita: {exc}", file=sys.stderr)
        return 1
    print("Verifica CPI postnatale superata per SNP e DNP, con un valore per trio e i dettagli di ogni sito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
