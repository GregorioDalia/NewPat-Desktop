"""Compare complete serial and chromosome-parallel callers on indexed synthetic BAMs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from verify_dnp_engine import FIXTURE, expected_rows

CONTIGS = ("chr2", "chr10")  # BAM dictionary order deliberately differs from lexical order.
POSITIONS = (50, 140, 230)


def indexed_inputs(identifier: str, root: Path, run_container) -> Path:
    generated = root / "indexed caller fixture"
    inputs = generated / "work"
    inputs.mkdir(parents=True)
    reference = "".join(line for line in (FIXTURE / "reference.fa").read_text().splitlines()
                        if not line.startswith(">"))
    (inputs / "reference.fa").write_text("".join(f">{contig}\n{reference}\n" for contig in CONTIGS))
    dnp_rows = (FIXTURE / "DNP_list.txt").read_text().splitlines()
    (inputs / "dnp.tsv").write_text("".join(
        row.replace("chrDnpSynthetic", contig) + "\n" for contig in CONTIGS for row in dnp_rows))
    (inputs / "snp.tsv").write_text("pos\tref\talt\n" + "".join(
        f"{contig}:{pos}\t{ref}\t{alt}\n" for contig in CONTIGS
        for pos, ref, alt in zip(POSITIONS, "ATG", "GCA")))
    for number, sample in enumerate(("A", "B"), start=1):
        lines = (FIXTURE / f"reads_{sample}.sam").read_text().splitlines()
        hd, sq, *reads = lines
        sam = inputs / f"sample_{number:04d}.sam"
        sam.write_text(hd + "\n" + "".join(sq.replace("chrDnpSynthetic", contig) + "\n" for contig in CONTIGS)
                       + "".join(f"{contig}_" + row.replace("chrDnpSynthetic", contig) + "\n"
                                 for contig in CONTIGS for row in reads))
    run_container(identifier, ["sh", "-ec", """
        samtools faidx reference.fa
        for sample in sample_0001 sample_0002; do
            samtools view -b -o "$sample.bam" "$sample.sam"
            samtools index "$sample.bam"
        done"""], results=generated)
    return inputs


def table_digests(output: Path) -> dict[str, str]:
    return {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*.txt")) if "presentation" not in path.relative_to(output).parts}


def check_called_loci(output: Path, workflow: str) -> None:
    files = (sorted((output / "individual_outputs").glob("full_output_*.txt"))
             if workflow == "dnp-call" else [output / "SNPcall_output.txt"])
    if len(files) != (2 if workflow == "dnp-call" else 1):
        raise ValueError(f"Missing sample tables in {output}")
    expected_keys = {(contig, str(pos)) for contig in CONTIGS for pos in POSITIONS}
    for sample, path in zip(("A", "B"), files):
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        pos = "pos1" if workflow == "dnp-call" else "pos"
        if len(rows) != len(expected_keys) or {(row["chr"], row[pos]) for row in rows} != expected_keys:
            raise ValueError(f"Lost or duplicated a chromosome/locus in {path}")
        if any(int(row["total_count"]) <= 0 for row in rows):
            raise ValueError(f"Missing observations in indexed fixture output {path}")
        if workflow == "dnp-call":
            oracle = expected_rows(sample)
            for row in rows:
                wanted = oracle["chrDnpSynthetic", row["pos1"], row["pos2"]]
                if any(row[field] != wanted[field] for field in ("N_REF", "N_ALT", "N_Other", "GT")):
                    raise ValueError(f"Indexed DNP results disagree with synthetic {sample} at {row['chr']}:{row[pos]}")


def qualify_acquisitions(identifier: str, root: Path, *, run_container, write_request) -> dict:
    inputs = indexed_inputs(identifier, root, run_container)
    common = {"schema_version": 1, "work_dir": "/results/work", "out_dir": "/results/output",
              "reference": "/inputs/reference.fa"}
    requests = {
        "dnp-call": {**common, "panel": "/inputs/dnp.tsv", "samples": [
            {"sample_id": f"sample_{i:04d}", "path": f"/inputs/sample_{i:04d}.bam"} for i in (1, 2)]},
        "snp-call": {**common, "panel": "/inputs/snp.tsv", "bam": "/inputs/sample_0001.bam",
                     "mode": "bam", "pileup": None},
    }
    report = {}
    for workflow, request in requests.items():
        tables, pileups = {}, {}
        for mode in ("serial", "auto"):
            run = root / f"indexed {workflow} {mode}"
            configuration = {**request, "workflow": workflow}
            if workflow == "dnp-call":
                configuration["parallel"] = mode == "auto"
            write_request(run, configuration)
            run_container(identifier, ["env", f"NIPAT_EXECUTION_MODE={mode}", "NIPAT_MAX_WORKERS=2",
                "NIPAT_DNP_KEEP_PILEUP=1", "python3", "/opt/nipat/engine/main.py", "execute",
                workflow, "--request", "/results/work/request.json"], inputs=inputs, results=run)
            check_called_loci(run / "output", workflow)
            tables[mode] = table_digests(run / "output")
            pileup = (run / ("mpileup.txt" if workflow == "dnp-call" else "work/pileup.txt")).read_bytes()
            order = list(dict.fromkeys(line.split(b"\t", 1)[0].decode() for line in pileup.splitlines()))
            if order != list(CONTIGS):
                raise ValueError(f"{workflow} {mode} pileup lost BAM dictionary order")
            pileups[mode] = hashlib.sha256(pileup).hexdigest()
        if not tables["serial"] or tables["serial"] != tables["auto"] or pileups["serial"] != pileups["auto"]:
            raise ValueError(f"Chromosome scheduling changed the {workflow} pileup or scientific tables.")
        name = "dnp-pileup.json" if workflow == "dnp-call" else "snp-acquisition.json"
        evidence = json.loads((run / "work" / name).read_text(encoding="utf-8"))
        tasks = sorted((item for item in evidence["processes"] if item["stage"] == "mpileup-chromosome"),
                       key=lambda item: item["task_index"])
        observed = evidence["parallel"]["observed_max_processes"]
        if (evidence["strategy"] != "indexed-chromosomes" or evidence["parallel"]["workers"] != 2
                or not 0 <= observed <= 2 or [item["contig"] for item in tasks] != list(CONTIGS)
                or len({item["pid"] for item in tasks}) != len(CONTIGS)
                or any(type(item["pid"]) is not int or item["pid"] <= 0 or item["returncode"] != 0
                       or item["outcome"] != "succeeded" for item in tasks)):
            raise ValueError(f"Expected two successful indexed chromosome tasks in {workflow}: {evidence}")
        report[workflow] = {"bam_count": len(request["samples"]) if workflow == "dnp-call" else 1,
                            "contigs": list(CONTIGS), "strategy": evidence["strategy"],
                            "workers": evidence["parallel"]["workers"], "observed_max_processes": observed,
                            "child_pids": [item["pid"] for item in tasks],
                            "pileup_sha256": pileups, "scientific_tables_sha256": tables}
    return report
