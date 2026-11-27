"""Run the existing homozygous-ALT and masked-genotype fixtures in the candidate image."""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from newpat.validation.self_test import compare_snp_outputs
from verify_dnp_engine import expected_rows, keyed_rows
from verify_engine_package import run_container, write_request


def check_edge_tables(dnp_table: Path, snp_table: Path) -> None:
    expected = expected_rows("A")
    actual = keyed_rows(dnp_table)
    if actual.keys() != expected.keys():
        raise ValueError("The DNP edge case returned unexpected loci for sample A")
    for key, row in expected.items():
        for field in ("REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count", "GT"):
            if actual[key][field] != row[field]:
                raise ValueError(f"DNP sample A {key}: {field}={actual[key][field]}, expected {row[field]}")
    compare_snp_outputs(FIXTURES / "snp_engine/expected.tsv", snp_table)


def verify_edges(image: str, work: Path) -> None:
    inputs = work / "inputs"
    inputs.mkdir(parents=True)
    for marker, sam, panel in (("dnp", "reads_A.sam", "DNP_list.txt"), ("snp", "reads.sam", "SNPlist.tsv")):
        fixture = FIXTURES / f"{marker}_engine"
        shutil.copyfile(fixture / sam, inputs / f"{marker}.sam")
        shutil.copyfile(fixture / panel, inputs / f"{marker}.tsv")
        shutil.copyfile(fixture / "reference.fa", inputs / f"{marker}.fa")

    results = work / "results"
    write_request(results, {
        "schema_version": 1,
        "samples": [
            {"id": "A", "kind": "bam", "path": "/results/work/sample_0001.bam"},
            {"id": "SNP_sample", "kind": "bam", "path": "/results/work/snp.bam"},
        ],
        "steps": [
            {"id": "dnp", "workflow": "dnp-call", "inputs": {
                "samples": ["A"], "reference": "/results/work/dnp.fa", "panel": "/inputs/dnp.tsv",
            }, "parameters": {"parallel": False}},
            {"id": "snp", "workflow": "snp-call", "inputs": {
                "sample": "SNP_sample", "reference": "/results/work/snp.fa", "panel": "/inputs/snp.tsv",
            }, "parameters": {"mode": "bam"}},
        ],
    })
    # The image supplies samtools and both callers. Keep each fixture on its own reference.
    run_container(image, ["sh", "-eu", "-c", """
        for marker in dnp snp; do
            cp "/inputs/$marker.fa" "$marker.fa"
            samtools faidx "$marker.fa"
        done
        samtools view -b -o sample_0001.bam /inputs/dnp.sam
        samtools view -b -o snp.bam /inputs/snp.sam
        exec python3 /opt/nipat/engine/main.py execute-plan \
            --plan /results/work/request.json --run-dir /results/workflow
    """], inputs=inputs, results=results)
    steps = results / "workflow/steps"
    check_edge_tables(steps / "dnp/output/individual_outputs/full_output_sample_0001.txt",
                      steps / "snp/output/SNPcall_output.txt")
