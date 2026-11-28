"""Compare DNP worker ceilings with the installed Apple Silicon package."""

import argparse
from datetime import datetime, timezone
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


def optional_report(path):
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
    matrix = artifacts["dnp-summary"]["genotypes"]["sha256"]
    if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in [matrix, *digests.values()]):
        raise ValueError("Invalid scientific output checksum.")
    return {"samples": digests, "genotype_matrix": matrix}


def startup_timings(record, launched_at):
    """Read host timestamps already recorded by the installed client."""
    timings = {}
    commands = record.get("commands") or []
    if commands and commands[0].get("started_at"):
        first = datetime.fromisoformat(commands[0]["started_at"])
        seconds = (first - launched_at).total_seconds()
        if seconds >= 0:
            timings["launcher_to_first_command_seconds"] = round(seconds, 3)
    for check in record.get("checks", []):
        argv = check.get("argv", [])
        if argv[-1:] == ["ensure"]:
            field = "runtime_ensure_seconds"
        elif argv[-3:] == ["/opt/newpat/engine/main.py", "describe", "--json"]:
            field = "engine_describe_seconds"
        else:
            continue
        if check.get("started_at") and check.get("finished_at"):
            elapsed = datetime.fromisoformat(check["finished_at"]) - datetime.fromisoformat(check["started_at"])
            if elapsed.total_seconds() >= 0:
                timings[field] = round(elapsed.total_seconds(), 3)
    return timings


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
    conditions = list(CONDITIONS)
    if args.include_four:
        conditions.append(("four", ["--execution-mode", "auto", "--max-workers", "4"]))
    cases = []
    report = {"package_version": manifest["version"], "source_commit": manifest["source_commit"],
              "macOS": platform.mac_ver()[0], "image": manifest["runtime_image"], "cases": cases}
    print(f"Results: {output}", flush=True)
    try:
        tick = time.monotonic()
        subprocess.run([launcher, "--runtime", "prepare"], check=True, stdin=subprocess.DEVNULL)
        report["initial_prepare_seconds"] = round(time.monotonic() - tick, 3)
        baseline = None
        for number in range(args.rounds):
            start = number % len(conditions)
            for label, options in conditions[start:] + conditions[:start]:
                name = f"{label}-{number + 1}"
                run = output / "runs" / name
                print(name, flush=True)
                case = {"run": name, "condition": label}
                cases.append(case)
                with (output / f"{name}.log").open("x", encoding="utf-8") as log:
                    tick = time.monotonic()
                    launched_at = datetime.now(timezone.utc)
                    proc = subprocess.run([launcher, "--runs-dir", str(run.parent), "--performance-diagnostics", *options, *dnp,
                                           "--run-name", name], stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT)
                    case.update(wall_seconds=round(time.monotonic() - tick, 3), exit_code=proc.returncode)
                if proc.returncode:
                    raise ValueError(f"{name} failed. See {name}.log.")
                record = read_json(run / "run.json")
                if record["status"] != "succeeded":
                    raise ValueError(f"{name}: unexpected status {record['status']}.")
                case["startup"] = startup_timings(record, launched_at)
                work = run / "work"
                pileup = read_json(work / "dnp-pileup.json")
                blocks = read_json(work / "dnp-blocks.json")
                pool = pileup.get("parallel", {})
                memory = optional_report(run / "performance/engine/summary.json")
                case.update(resources=record["resource_snapshot"], budget=record["resource_budget"],
                            acquisition_strategy=pileup["strategy"], acquisition_seconds=pileup.get("elapsed_seconds"),
                            observed_samtools=pool.get("observed_max_processes"), acquisition_reason=pool.get("reason"),
                            indexing_seconds=blocks.get("index_seconds"), calculation_seconds=blocks.get("processing_seconds"),
                            observed_r_workers=blocks.get("observed_workers"),
                            sampled_cgroup_max_bytes=memory.get("sampled_memory_max_bytes"),
                            observed_kernel_memory_peak_bytes=memory.get("observed_kernel_memory_peak_bytes"))
                # Older packages do not record the block reader and computation separately.
                case["block_work"] = {key: blocks[key] for key in (
                    "task_count", "sample_block_count", "block_read_count", "block_logical_bytes_read",
                    "block_read_seconds", "block_compute_seconds") if key in blocks}
                tables = scientific_tables(work)
                if baseline is None:
                    baseline = tables
                    report["serial_tables_sha256"] = tables
                case["matches_serial_tables"] = tables == baseline
                if not case["matches_serial_tables"]:
                    raise ValueError(f"{name}: individual DNP tables or genotype matrix differ from serial.")
                log_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["median_wall_seconds"] = {
            label: statistics.median(case["wall_seconds"] for case in cases if case["condition"] == label)
            for label, _ in conditions
        }
        print(json.dumps(report["median_wall_seconds"], indent=2))
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as exc:
        report["error"] = str(exc) or type(exc).__name__
        if cases:
            last = cases[-1]
            path = output / "runs" / last["run"] / "work/dnp-block-progress.json"
            if partial := optional_report(path):
                last["last_completed_block_work"] = partial
        raise
    finally:
        log_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("/Applications/NewPat.app"))
    for arg in ("bamlist", "reference", "panel", "output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--include-four", action="store_true",
                        help="Also test a ceiling of four workers and record the concurrency actually observed.")
    try:
        compare(parser.parse_args())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
