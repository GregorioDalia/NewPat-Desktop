"""Compare the installed native Apple Silicon candidate with the recorded synthetic M1 workload."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/acceptance"))
from installed_suite import verify_run
from installed_workflows import check_plan
from newpat.errors import NipatError
from newpat.macos_runtime import LimaRuntime, rosetta_enabled


def read(path):
    return json.loads(path.read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def input_files(folder, baseline):
    with zipfile.ZipFile(PROJECT / "examples/newpat-synthetic-trio.zip") as bundled:
        for name, digest in baseline["timing_inputs_sha256"].items():
            raw = bundled.read("synthetic-trio/timing/" + name)
            require(hashlib.sha256(raw).hexdigest() == digest, f"Timing input differs from baseline: {name}")
            (folder / name).write_bytes(raw)
    for count in (1, 2, 3, 4):
        for suffix in ("bam", "bam.bai"):
            (folder / f"replica{count}.{suffix}").write_bytes((folder / f"timing.{suffix}").read_bytes())


def power_source():
    value = subprocess.check_output(["/usr/bin/pmset", "-g", "batt"], text=True, timeout=10)
    return "battery" if "'Battery Power'" in value else "ac" if "'AC Power'" in value else "unknown"


def record_result(run, image, count, expected_hashes):
    verify_run(run, image)
    root, plan, state = check_plan(run, ["dnp-call", *(["snp-call"] * count)])
    marker = {step["id"]: step["workflow"].split("-")[0] for step in plan["steps"]}
    found = {}
    for step in state["steps"]:
        kind = marker[step["id"]]
        for table in step["artifacts"][kind + "-tables"]:
            key = kind + "/" + table["sample"]
            require(key not in found, f"Duplicate sample table: {key}")
            found[key] = table["sha256"]  # check_plan verified the actual bytes.
    require(found == {f"{kind}/sample{i}": digest for kind, digest in expected_hashes.items()
                      for i in range(1, count + 1)}, "Scientific tables differ from the 0.9.10 oracle")
    record = read(run / "run.json")
    require(record["runtime"]["architecture"] == "arm64", "Experiment did not use the ARM64 engine")
    diag = read(run / "performance/engine/summary.json")
    budget = record["resource_budget"]
    acquisition = read(root / "steps/dnp/work/dnp-pileup.json")
    blocks_path = root / "steps/dnp/work/dnp-blocks.json"
    blocks = read(blocks_path) if blocks_path.is_file() else {}
    def elapsed(start, end):
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 3)
    return {"run_seconds": elapsed(record["started_at"], record["finished_at"]),
            "step_seconds": {s["id"]: elapsed(s["started_utc"], s["finished_utc"]) for s in state["steps"]},
            "acquisition_seconds": acquisition.get("elapsed_seconds"),
            "samtools_observed": (acquisition.get("parallel") or {}).get("observed_max_processes"),
            "r_workers_observed": blocks.get("observed_workers"), "r_calculation_seconds": blocks.get("processing_seconds"),
            "cpu_limit": budget["cpu_limit"], "memory_capacity_mib": budget["memory_capacity_mib"],
            "memory_kernel_peak_bytes": diag.get("observed_kernel_memory_peak_bytes"),
            "memory_sampled_max_bytes": diag.get("sampled_memory_max_bytes"),
            "diagnostics_status": diag.get("status"), "table_sha256": found}


def compare(baseline, report):
    warm = [r for r in report["measurements"] if r["trial"] > 0]
    median = {str(n): statistics.median(r["run_seconds"] for r in warm if r["bam_count"] == n) for n in (1, 2, 4)}
    report["warm_median_seconds"] = median
    issues = [k for k in ("model", "physical_ram_bytes", "logical_cpus", "release") if report["host"][k] != baseline["host"][k]]
    for key in ("cpu_limit", "memory_capacity_mib"):
        if any(r[key] != baseline[key] for r in report["measurements"]):
            issues.append(key)
    if any(power != baseline["host"]["power_source"] for r in report["measurements"] for power in r["power_source"]):
        issues.append("power_source")
    report["different_conditions"] = issues
    if not issues:
        report["time_reduction_percent"] = {n: round(100 * (1 - v / baseline["warm_median_seconds"][n]), 1)
                                            for n, v in median.items()}


def run_benchmark(output, commit):
    require(sys.platform == "darwin" and platform.machine() == "arm64", "Apple Silicon Mac required")
    resources = PROJECT.parent
    launcher = resources / "NewPat.command"
    workspace = Path.home() / "Library/Application Support/NIPAT-Desktop"
    runtime = LimaRuntime(PROJECT, workspace, resources / "lima/bin/limactl")
    manifest = read(PROJECT / ".distribution/macos-manifest.json")
    require(manifest["source_commit"] == commit and manifest["scientific_platform"] == "linux/arm64",
            "Install the Apple Silicon package included with this trial first")
    baseline = read(PROJECT / "docs/validation/0.9.10-apple-silicon-timing.json")
    report = {"status": "RUNNING", "version": manifest["version"], "source_commit": commit,
              "workload_id": baseline["workload_id"], "baseline_seconds": baseline["warm_median_seconds"],
              "baseline_commit": baseline["source_commit"], "measurements": []}
    def save():
        temporary = output / "comparison.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(output / "comparison.json")
    def launch(args, name):
        with (output / (name + ".log")).open("x") as log:
            subprocess.run([launcher, *args], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                           timeout=3600, check=True)
    try:
        save()
        host = {"release": platform.mac_ver()[0], "logical_cpus": os.cpu_count()}
        for field, key in (("model", "hw.model"), ("physical_ram_bytes", "hw.memsize")):
            v = subprocess.check_output(["/usr/sbin/sysctl", "-n", key], text=True, timeout=10).strip()
            host[field] = int(v) if field == "physical_ram_bytes" else v
        report["host"] = host
        before = read(runtime.state_path) if runtime.state_path.exists() else {}
        owner = read(runtime.owner_path).get("token") if runtime.owner_path.is_file() else None
        before_vm = None
        if owner and runtime.instance_dir.exists():
            runtime._assert_owned()
            before_vm = runtime._instance_info()
        # Existing experiment IDs stay local. Only preservation and counts go into the shareable report.
        runs = {f for f in (workspace / "runs").glob("*/run.json")}
        launch(["--runtime", "prepare"], "prepare")
        state = read(runtime.state_path)
        info = runtime._instance_info()
        config = info["config"]
        require(state["phase"] == "ready" and state["source_commit"] == commit and info["status"] == "Running"
                and not rosetta_enabled(config), "Lima has not prepared the native guest with Rosetta disabled")
        require(all(p.is_file() for p in runs), "Existing experiment records are missing")
        if owner and before_vm:
            require(read(runtime.owner_path)["token"] == owner and all(
                config.get(k) == before_vm["config"].get(k) for k in ("cpus", "memory", "disk")),
                "Owned VM identity or resource allocation changed during preparation")
        image = state["runtime_image"]
        active = subprocess.check_output(runtime.docker_command(["ps", "-q"]), text=True, timeout=90)
        require(not active.strip(), "Wait for other container jobs to finish before comparing timings")
        report["runtime"] = {**runtime.native_evidence(image), "image": image, "previous_version": before.get("version"),
                             "previous_rosetta_enabled": rosetta_enabled(before_vm["config"]) if before_vm else None,
                             "existing_experiment_records_preserved": len(runs),
                             "owned_vm_preserved": True if before_vm and owner else None}
        folder = output / "inputs"
        folder.mkdir()
        input_files(folder, baseline)
        for trial, order in enumerate(baseline["rounds"]):
            for count in order:
                name = f"timing-{count}-r{trial}"
                print(f"{count} BAM · {trial + 1}/4", flush=True)
                args = ["--data-dir", folder, "--runs-dir", output / "runs", "--input-hashes", "full",
                        "--execution-mode", "auto", "--set", "dnp-call.max_depth=8000", "--performance-diagnostics",
                        "workflow", "analyze", "--caller", "both", "--reference", folder / "reference.fa",
                        "--dnp-panel", folder / "dnp.tsv", "--snp-panel", folder / "snp.tsv", "--run-name", name]
                for i in range(1, count + 1):
                    args.extend(["--sample", f"sample{i}", folder / f"replica{i}.bam"])
                power = power_source()
                start = time.monotonic()
                launch(args, name)
                wall = round(time.monotonic() - start, 3)
                row = record_result(output / "runs" / name, image, count, baseline["table_sha256"])
                report["measurements"].append(dict(row, bam_count=count, trial=trial, wall_seconds=wall,
                                                   power_source=[power, power_source()]))
                save()
        compare(baseline, report)
        report["status"] = "PASS"
    except (NipatError, OSError, ValueError, KeyError, AssertionError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        report.update(status="FAILED", error=str(exc) or type(exc).__name__)
        raise
    finally:
        save()
        print(f"Report: {output / 'comparison.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit-file", type=Path, required=True)
    options = parser.parse_args()
    parent = Path.home() / "Downloads"
    parent.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="NewPat-Mac-Comparison-", dir=parent))
    run_benchmark(destination, options.source_commit_file.read_text().strip())
