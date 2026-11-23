"""Compare DNP worker ceilings with the installed Apple Silicon package."""

import argparse
import json
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import time


CONDITIONS = [
    ("serial", ["--execution-mode", "serial"]),
    ("two", ["--execution-mode", "auto", "--max-workers", "2"]),
    ("auto", ["--execution-mode", "auto"]),
]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def scientific_tables(work):
    report = read_json(work / "scientific-validation.json")
    if report["status"] != "validated" or report["workflow"] != "dnp-call":
        raise ValueError("DNP output validation did not pass.")
    artifacts = report["artifacts"]
    tables = artifacts["dnp-tables"]
    if not tables:
        raise ValueError("Missing individual DNP tables.")
    digests = {row["sample"]: row["sha256"] for row in tables}
    if len(digests) != len(tables):
        raise ValueError("Duplicate sample in validated DNP tables.")
    digests["genotype-matrix"] = artifacts["dnp-summary"]["genotypes"]["sha256"]
    if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in digests.values()):
        raise ValueError("Invalid scientific output checksum.")
    return digests


def compare(args):
    resources = args.app.expanduser().resolve() / "Contents/Resources"
    manifest = read_json(resources / "app/.distribution/macos-manifest.json")
    if sys.platform != "darwin" or platform.machine() != "arm64" or manifest["architecture"] != "arm64":
        raise ValueError("Use the Apple Silicon package and its bundled ARM Python on the Mac to test.")
    launcher = str(resources / "NewPat.command")
    dnp = ["dnp-call", "--bamlist", str(args.bamlist.resolve(strict=True)),
           "--reference", str(args.reference.resolve(strict=True)), "--panel", str(args.panel.resolve(strict=True))]
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    log_path = output / "benchmark.json"
    cases = []
    report = {"package_version": manifest["version"], "source_commit": manifest["source_commit"],
              "macOS": platform.mac_ver()[0], "image": manifest["runtime_image"], "cases": cases}
    print(f"Results: {output}", flush=True)
    try:
        subprocess.run([launcher, "--runtime", "prepare"], check=True, stdin=subprocess.DEVNULL)
        baseline = None
        for number in range(args.rounds):
            start = number % len(CONDITIONS)
            for label, options in CONDITIONS[start:] + CONDITIONS[:start]:
                name = f"{label}-{number + 1}"
                run = output / "runs" / name
                print(name, flush=True)
                case = {"run": name, "condition": label}
                cases.append(case)
                with (output / f"{name}.log").open("x", encoding="utf-8") as log:
                    tick = time.monotonic()
                    proc = subprocess.run([launcher, "--runs-dir", str(run.parent), *options, *dnp,
                                           "--run-name", name], stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT)
                    case.update(wall_seconds=round(time.monotonic() - tick, 3), exit_code=proc.returncode)
                if proc.returncode:
                    raise ValueError(f"{name} failed. See {name}.log.")
                record = read_json(run / "run.json")
                if record["status"] != "succeeded":
                    raise ValueError(f"{name}: unexpected status {record['status']}.")
                work = run / "work"
                pileup = read_json(work / "dnp-pileup.json")
                blocks = read_json(work / "dnp-blocks.json")
                pool = pileup.get("parallel", {})
                case.update(resources=record["resource_snapshot"], budget=record["resource_budget"],
                            acquisition_strategy=pileup["strategy"], acquisition_seconds=pileup.get("elapsed_seconds"),
                            observed_samtools=pool.get("observed_max_processes"), acquisition_reason=pool.get("reason"),
                            indexing_seconds=blocks.get("index_seconds"), calculation_seconds=blocks.get("processing_seconds"),
                            observed_r_workers=blocks.get("observed_workers"))
                tables = scientific_tables(work)
                if baseline is None:
                    baseline = tables
                case["matches_serial_tables"] = tables == baseline
                if not case["matches_serial_tables"]:
                    raise ValueError(f"{name}: individual DNP tables or genotype matrix differ from serial.")
                log_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["median_wall_seconds"] = {
            label: statistics.median(case["wall_seconds"] for case in cases if case["condition"] == label)
            for label, _ in CONDITIONS
        }
        print(json.dumps(report["median_wall_seconds"], indent=2))
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        report["error"] = str(exc) or type(exc).__name__
        raise
    finally:
        log_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("/Applications/NewPat.app"))
    for arg in ("bamlist", "reference", "panel", "output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=(1, 2, 3), default=1)
    try:
        compare(parser.parse_args())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
