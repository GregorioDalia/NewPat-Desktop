"""Qualify downstream science against independent oracles and frozen R.

Runs with local R or against an immutable scientific image using --image.
This complements (does not replace) DNP/SNP caller equivalence and BAM workflow
tests. The image gate runs installed candidate code with read-only oracle inputs
and no network. Local R qualification does not require a Docker daemon.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
FIXTURE = PROJECT / "tests/fixtures/five_modules"
REFERENCE = PROJECT / "tests/reference_r/NEWPAT_20261125"
SOURCES = {
    "cpin": "CPI_postnatal/Postnatal_CPI.R",
    "cpi": "CPI_from_cffDNA/cfDNA_CPI_estimator.R",
    "contamination": "contamination/detect_contamination.R",
}
REFERENCE_SHA256 = {
    "CPI_postnatal/Postnatal_CPI.R": "611fd93c4606298e97174c5c7b55f9a34445b95389537c994b7f41ffa43a05e6",
    "CPI_from_cffDNA/cfDNA_CPI_estimator.R": "263b517d37532b724f429b9ee883a64d748a8d5d2398444f2956d6eda3a2ac81",
    "contamination/detect_contamination.R": "afbbf20b937dfef356d0046e18ffff3d6746113ae771dd87745369b3e64081ca",
}
HELPERS = ("__init__.py", "errors.py", "settings.py", "settings.R", "settings_data.json",
           "parallel.R", "plots.R")
CANDIDATE_ROOT = PROJECT / "scientific/vendor/NEWPAT"
HELPER_ROOT = PROJECT / "src/nipat_scientific"
REPORT_NAME = "five-module-qualification.json"
SUMMARIES = {"cpin": "Summary_Postnatal_CPI.txt", "cpi": "Summary_FetalFraction_CPI.csv",
             "contamination": "contamination_summary.txt"}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(root):
    return {path.relative_to(root).as_posix(): file_hash(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def same_settings(actual, expected):
    """Compare native R provenance independently, including JSON value types."""
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same_settings(actual[key], value) for key, value in expected.items()))
    if type(expected) in (int, float):
        return (type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, rel_tol=1e-14, abs_tol=0))
    return type(actual) is type(expected) and actual == expected


def verify_installed_payload(bundle):
    """Fail stale images before running any candidate science from that image."""
    hashes = {}
    mappings = [(PROJECT / "scientific/vendor/NEWPAT" / path,
                 bundle / "scientific/vendor/NEWPAT" / path) for path in SOURCES.values()]
    mappings.extend((PROJECT / "src/nipat_scientific" / name,
                     bundle / "lib/nipat_scientific" / name) for name in HELPERS)
    for checkout, installed in mappings:
        require(installed.is_file(), f"Installed payload missing: {installed}")
        actual = hashlib.sha256(installed.read_bytes()).hexdigest()
        require(actual == hashlib.sha256(checkout.read_bytes()).hexdigest(),
                f"Stale scientific image: {installed}")
        hashes[installed.relative_to(bundle).as_posix()] = actual
    return hashes


def snapshot_local_payload(destination):
    """Rscript streams source files; freeze a development tree for this run.

    This also makes the exact tested source available with the evidence while
    other developers edit their checkout. Image qualification never uses this
    snapshot: it must run the payload installed in the requested image.
    """
    bundle = destination / "candidate-snapshot"
    for name in SOURCES.values():
        target = bundle / "scientific/vendor/NEWPAT" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / "scientific/vendor/NEWPAT" / name, target)
    for name in HELPERS:
        target = bundle / "lib/nipat_scientific" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / "src/nipat_scientific" / name, target)
    return bundle, verify_installed_payload(bundle)


def mount(source, target, readonly=False):
    stream = io.StringIO()
    csv.writer(stream, lineterminator="").writerow(
        ["type=bind", f"source={source}", f"target={target}", *(["readonly"] if readonly else [])])
    return stream.getvalue()


def qualify_image(image, destination, full):
    require(shutil.which("docker"), "Docker is required for --image qualification")
    inspected = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                               capture_output=True, text=True, check=True)
    image_id = inspected.stdout.strip()
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id), "Invalid immutable Docker image ID")
    command = ["docker", "run", "--rm", "--network=none", "--cpus=4", "--memory=8g",
               "--env", "HOME=/tmp", "--env", "TMPDIR=/tmp"]
    if hasattr(os, "getuid"):
        # Atomic settings files intentionally retain mode 0600. Create the
        # synthetic evidence as the runner, so upload/archiving can read it
        # without relaxing either scientific file permissions or ownership.
        command += ["--user", f"{os.getuid()}:{os.getgid()}"]
    command += [
               "--mount", mount(PROJECT, "/qualification", readonly=True),
               "--mount", mount(destination, "/evidence"), "--workdir", "/evidence",
               "--entrypoint", "python3", image_id, "/qualification/scripts/verify_five_modules.py",
               "--installed-root", "/opt/nipat", "--image-id", image_id, "--output", "/evidence"]
    if full:
        command.append("--full")
    # No candidate bind mount, helper override, host PYTHONPATH, or settings
    # environment is forwarded. Installed Python/R helpers are selected below.
    process = subprocess.run(command, capture_output=True, text=True)
    (destination / "container-stdout.log").write_text(process.stdout)
    (destination / "container-stderr.log").write_text(process.stderr)
    require(process.returncode == 0,
            f"Scientific image qualification failed ({process.returncode}): {process.stderr[-1500:]}")
    report = json.loads((destination / REPORT_NAME).read_text())
    require(report["status"] == "passed" and report["runtime"]["image_id"] == image_id,
            "Image qualification evidence is incomplete")
    return report


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def table(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="," if Path(path).suffix == ".csv" else "\t"))


def number(value, expected, label="number"):
    if expected is None:
        require(str(value) in {"NA", "NaN", "nan"}, f"{label}: expected NA, got {value}")
        return
    actual = float(value)
    require(math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-11),
            f"{label}: expected {expected}, got {value}")


def compare_tables(observed, expected):
    """Compare all reference fields, permitting additional candidate diagnostics."""
    require(len(observed) == len(expected), "Reference row count differs")
    for index, (actual, wanted) in enumerate(zip(observed, expected, strict=True)):
        require(set(wanted).issubset(actual), f"Missing reference columns in row {index}")
        for key, value in wanted.items():
            if value in {"NA", "NaN"}:
                number(actual[key], None, key)
                continue
            try:
                expected_number = float(value)
            except ValueError:
                require(actual[key] == value, f"{index}/{key}: {actual[key]!r} != {value!r}")
            else:
                number(actual[key], expected_number, f"{index}/{key}")


def verify_frozen_sources():
    manifest = json.loads((REFERENCE / "manifest.json").read_text())
    require(manifest["upstream_commit"] == "97c4eb5f7a901d0435b950c3e2a52a8bd7eae9d4",
            "Unexpected upstream reference identity")
    require(manifest["sha256"] == REFERENCE_SHA256, "Immutable reference manifest altered")
    for name, expected in manifest["sha256"].items():
        require(hashlib.sha256((REFERENCE / name).read_bytes()).hexdigest() == expected,
                f"Immutable reference altered: {name}")
    return manifest


def check_cpin(output, marker, families=1):
    rows = table(output / "Summary_Postnatal_CPI.txt")
    trios = ([f"MotherM-FatherF-ChildC_{marker}s"] if families == 1 else
             [f"MotherM{i}-FatherF{i}-ChildC{i}_{marker}s" for i in range(1, families + 1)])
    require(len(rows) == families and {row["Trio"] for row in rows} == set(trios),
            "Postnatal CPI must retain each distinct trio exactly once")
    epsilon = .001 if marker == "SNP" else .0000892303778101497
    # Positions 100, 200, 300, 500 and 600 pass. Position 500 is neutral
    # (heterozygous mother and child). Positions 200 and 600 mismatch.
    cpi = (0.5 / 0.4) * (epsilon / 0.4) * (1 / 0.6) * (epsilon / 0.4)
    for row in rows:
        require(row["Marker_type"] == marker, "Wrong postnatal marker type")
        for key, expected in {"N_sites": 5, "N_hom_hom": 1, "N_hom_het": 3,
                              "N_het_hom": 0, "N_het_het": 1, "Matching_sites": 2,
                              "Mismatching_sites": 2, "No_obligatory_allele_sites": 1,
                              "Maternal_incompatible_sites": 1, "Mismatch_probability": epsilon,
                              "Min_coverage": None, "CPI": cpi, "Log10_CPI": math.log10(cpi)}.items():
            number(row[key], expected, key)
        sites = table(output / (row["Trio"] + "_sites.txt"))
        require(len(sites) == 9 and sum(site["Status"] == "eligible" for site in sites) == 5,
                "Postnatal CPI must report all nine input sites and five eligible sites")
    return rows


def check_cpi(output, marker, minimum=2, families=1, mismatch=False, *, candidate=True):
    rows = table(output / "Summary_FetalFraction_CPI.csv")
    require(len(rows) == (2 if families == 1 else families), "CPI lost an informative/no-sites pair")
    epsilon = .001 if marker == "SNP" else .0000892303778101497
    pairs = ([f"MotherM-FatherF_{marker}s", f"MotherN-FatherN_{marker}s"] if families == 1 else
             [f"MotherM{i}-FatherF{i}_{marker}s" for i in range(1, families + 1)])
    require({row["Pair"] for row in rows} == set(pairs), "CPI must retain each distinct pair exactly once")
    for row in rows:
        if candidate:
            require(row["Marker_type"] == marker, "Wrong CPI marker type")
            number(row["Min_fetal_reads"], minimum)
        empty = "MotherN-FatherN" in row["Pair"] or minimum > 4
        expected = {
            "N_sites_mother": 0 if empty else (4 if minimum == 1 else 3),
            "N_sites_father": 0 if empty else (4 if minimum == 1 else 3),
            "Median_fetal_fraction_raw": None if empty else (.05 if minimum == 1 else .06),
            "Median_fetal_fraction_percent": None if empty else (5 if minimum == 1 else 6),
            "Max_logCPI": None if empty else (2 if minimum == 1 else 1.301),
            "Min_logCPI": None if empty else .301,
            "Median_logCPI": None if empty else (.952 if minimum == 1 else .602),
            "Mean_logCPI": None if empty else (1.051 if minimum == 1 else .735),
            "CPI_medianFF": None if empty else (1.301 if minimum == 1 else .602),
            "Error_constant": epsilon,
        }
        if mismatch and not empty:
            logs = [math.log10(value) for value in (40 * epsilon, 8 * epsilon, 2)]
            expected.update({"Max_logCPI": round(max(logs), 3),
                             "Min_logCPI": round(min(logs), 3),
                             "Median_logCPI": round(sorted(logs)[1], 3),
                             "Mean_logCPI": round(sum(logs) / len(logs), 3),
                             "CPI_medianFF": round(logs[1], 3)})
        for key, value in expected.items():
            number(row[key], value, key)
    return rows


def check_cpi_curves(output, minimum, marker, families=1, mismatch=False):
    paths = sorted((output / "curves").glob("*.tsv"))
    require(len(paths) == (2 if families == 1 else families), "CPI must export every pair curve, including empty ones")
    epsilon = .001 if marker == "SNP" else .0000892303778101497
    contributions = [(1, 5), (2, 5), (3, 4 * epsilon if mismatch else 2), (4, 2)]
    for path in paths:
        rows = table(path)
        if "MotherN-FatherN" in path.name or minimum > 4:
            require(not rows, "No-sites pair must have an empty curve")
            continue
        require([int(row["Iteration"]) for row in rows] == list(range(minimum, 5)),
                "CPI curve has missing or duplicate thresholds")
        for row in rows:
            threshold = int(row["Iteration"])
            retained = [value for support, value in contributions if support >= threshold]
            product = math.prod(retained)
            mismatches = int(mismatch and threshold <= 3)
            for name, expected in {"InfSites_mother": len(retained), "InfSites_father": len(retained),
                                   "CPI": product, "log_CPI": math.log10(product),
                                   "Mismatch": mismatches, "NotMismatch": len(retained) - mismatches}.items():
                number(row[name], expected, name)


def check_contamination(output, include_zero, samples=1):
    rows = table(output / "contamination_summary.txt")
    require(len(rows) == samples, "Contamination lost or duplicated samples")
    require({row["individuo"] for row in rows} == {f"Sample{i}" for i in range(1, samples + 1)},
            "Contamination must retain each distinct sample exactly once")
    for row in rows:
        number(row["informative_sites"], 2 if include_zero else 1)
        number(row["mean_contamination"], .025 if include_zero else .05)
        number(row["sd_contamination"], math.sqrt(.00125) if include_zero else None)
    return rows


def check_worker_limits(path, cap):
    events = []
    for item in sorted(path.glob("*.jsonl")):
        events.extend(json.loads(line) for line in item.read_text().splitlines() if line.strip())
    plans = [event for event in events if event["event"] == "plan"]
    require(plans, "Candidate did not record its parallel budget")
    budget_fields = ("workers", "tasks", "mode", "cpu_limit", "memory_worker_limit")
    for plan in plans:
        require(type(plan["workers"]) is int and type(plan["tasks"]) is int
                and plan["tasks"] >= 0 and plan["workers"] >= 1
                and (cap is None or plan["workers"] <= cap),
                "Worker budget exceeded the requested limit")
        cpu, memory = plan.get("cpu_limit"), plan.get("memory_worker_limit")
        require(type(cpu) in (int, float) and 0 < cpu < math.inf
                and type(memory) in (int, float) and 1 <= memory < math.inf,
                "Missing or invalid CPU/memory limits in worker plan")
        require(plan["workers"] <= min(math.ceil(cpu), memory, max(1, plan["tasks"])),
                "Worker budget exceeded available CPU/memory/tasks")
    current_budgets = {}
    pending, completed, children = {}, set(), set()
    generations, expected = {}, set()
    peak = 0
    for event in sorted(events, key=lambda item: item["observed_at_unix"]):
        plan_key = (event["coordinator_pid"], event["label"])
        if event["event"] == "plan":
            # CPI reuses a cutoff label sequentially for each prenatal pair.
            # Task indices are unique within that invocation, not process-wide.
            generation = generations.get(plan_key, 0) + 1
            generations[plan_key] = generation
            current_budgets[plan_key] = tuple(event[field] for field in budget_fields)
            expected.update((generation, *plan_key, index)
                            for index in range(1, event["tasks"] + 1))
            continue
        if event["event"] not in {"task-start", "task-end"}:
            continue
        require(tuple(event[field] for field in budget_fields) == current_budgets.get(plan_key),
                "Scientific task has no matching resource plan")
        require(type(event["task_index"]) is int and 1 <= event["task_index"] <= event["tasks"],
                "Scientific task index is outside its resource plan")
        key = (generations[plan_key], *plan_key, event["task_index"])
        if event["event"] == "task-start":
            require(key not in pending and key not in completed, "Duplicated scientific task start")
            pending[key] = event
            if event["pid"] != event["coordinator_pid"]:
                children.add(event["pid"])
        else:
            require(key in pending and event["outcome"] == "succeeded"
                    and pending[key]["pid"] == event["pid"], "Unmatched or failed worker end")
            pending.pop(key)
            completed.add(key)
        # Nested serial work in the same process still consumes one worker.
        # A serial coordinator awaiting its loaded inner pool is not itself
        # another computing worker. Forked outer workers still share the same
        # ceiling and must not multiply it with their own descendants.
        coordinating = {item["coordinator_pid"] for item in pending.values()
                        if item["pid"] != item["coordinator_pid"]}
        live_pids = {item["pid"] for item in pending.values()} - coordinating
        active = len(live_pids)
        peak = max(peak, active)
        require(cap is None or active <= cap, "Observed worker concurrency exceeded requested cap")
        if active:
            outer = [item["workers"] for item in pending.values()
                     if item["coordinator_pid"] not in live_pids
                     and not (item["pid"] == item["coordinator_pid"]
                              and item["pid"] in coordinating)]
            if not outer:
                outer = [item["workers"] for item in pending.values()
                         if item["pid"] == item["coordinator_pid"]]
            require(outer and active <= min(outer), "Observed worker concurrency exceeded shared budget")
    require(not pending and completed, "Scientific workers did not complete")
    require(completed == expected, "Scientific workers did not complete every planned task")
    return {"plans": len(plans), "max_planned_workers": max(event["workers"] for event in plans),
            "observed_peak_workers": peak, "completed_worker_tasks": len(completed),
            "observed_child_pids": sorted(children), "event_sha256": tree_hashes(path),
            "phase_plans": [{key: event[key] for key in
                             ("label", "workers", "tasks", "reason", "worker_ceiling", "workload_model",
                              "memory_worker_limit") if key in event}
                            for event in plans]}


def prepare_inputs(root, marker, workflow, families=1, metadata=False, mismatch=False):
    directory = root / "inputs"
    shutil.copytree(FIXTURE / marker / workflow, directory)
    if workflow == "cpin" and families > 1:
        for index in range(1, families + 1):
            for role, name in (("Mother", "M"), ("Father", "F"), ("Child", "C")):
                shutil.copyfile(directory / f"{role}{name}.txt", directory / f"{role}{name}{index}.txt")
    if workflow == "cpi" and mismatch:
        path = directory / "FatherF.txt"
        rows = table(path)
        rows[1].update({"N_REF": "100", "N_ALT": "0"})
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0], delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
    if workflow == "cpi" and families > 1:
        for index in range(1, families + 1):
            for role, name in (("Mother", "M"), ("Father", "F")):
                shutil.copyfile(directory / f"{role}{name}.txt", directory / f"{role}{name}{index}.txt")
    if workflow == "contamination":
        calls = directory / "calls"
        calls.mkdir()
        for index in range(1, families + 1):
            shutil.copyfile(directory / "Calls.txt", calls / f"Sample{index}.txt")
    if metadata:
        path = directory / "population.tsv"
        lines = path.read_text().splitlines()
        path.write_text(lines[0] + "\tunused_metadata\n" + "".join(line + "\tNA\n" for line in lines[1:]))
    return directory


def run_case(root, name, workflow, marker, *, candidate=True, minimum=2,
             include_zero=True, families=1, mode="serial", cap=None, metadata=False, mismatch=False):
    from nipat_scientific.settings import settings_context

    destination = root / name
    destination.mkdir()
    inputs = prepare_inputs(destination, marker, workflow, families, metadata, mismatch)
    input_hashes = tree_hashes(inputs)
    output = destination / "output"
    work = destination / "work"
    work.mkdir()
    helper = HELPER_ROOT
    script = (CANDIDATE_ROOT if candidate else REFERENCE) / SOURCES[workflow]
    arguments = []
    overrides = {}
    if workflow == "contamination":
        arguments = [str(inputs / "panel.tsv"), str(inputs / "calls"), str(output)]
        overrides = {"include_zero": include_zero}
        if not candidate and not include_zero:
            arguments.append("--exclude_zero")
    else:
        arguments = ["--pileup_dir", str(inputs), "--out_dir", str(output),
                     "--popfreq", str(inputs / "population.tsv"),
                     "--mother_prefix", "Mother", "--father_prefix", "Father"]
        if workflow == "cpi":
            pairs = "M:F,N:N" if families == 1 else ",".join(f"M{i}:F{i}" for i in range(1, families + 1))
            arguments += ["--pairs", pairs]
            overrides = {"min_fetal_reads": minimum}
            if not candidate:
                arguments += ["--min_fetal_reads", str(minimum)]
        else:
            trios = "M:F:C" if families == 1 else ",".join(f"M{i}:F{i}:C{i}" for i in range(1, families + 1))
            arguments += ["--child_prefix", "Child", "--trios", trios]

    context = settings_context(workflow, overrides, work) if candidate else nullcontext()
    start = time.monotonic()
    with context:
        environment = dict(os.environ)
        environment.update({"NIPAT_PARALLEL_HELPER": str(helper / "parallel.R"),
                            "NIPAT_PLOTS_HELPER": str(helper / "plots.R"),
                            "NIPAT_SETTINGS_HELPER": str(helper / "settings.R"),
                            "NIPAT_EXECUTION_MODE": mode,
                            "NIPAT_PARALLEL_LOG_DIR": str(destination / "parallel")})
        environment.pop("NIPAT_MAX_WORKERS", None)
        environment.pop("NIPAT_PARALLEL_CHILD", None)
        if cap is not None:
            environment["NIPAT_MAX_WORKERS"] = str(cap)
        if not candidate:
            environment.pop("NIPAT_SCIENTIFIC_SETTINGS", None)
        process = subprocess.run(["Rscript", str(script), *arguments], cwd=destination,
                                 env=environment, capture_output=True, text=True, timeout=180)
    (destination / "stdout.log").write_text(process.stdout)
    (destination / "stderr.log").write_text(process.stderr)
    require(process.returncode == 0, f"{name}: R exited {process.returncode}; {process.stderr[-1200:]}")
    if workflow == "cpin":
        rows = check_cpin(output, marker, families)
    elif workflow == "cpi":
        rows = check_cpi(output, marker, minimum, families, mismatch, candidate=candidate)
        if candidate:
            check_cpi_curves(output, minimum, marker, families, mismatch)
    else:
        rows = check_contamination(output, include_zero, families)
    require(tree_hashes(inputs) == input_hashes, f"{name}: scientific execution changed its inputs")
    effective_settings = None
    if candidate:
        effective_settings = json.loads((work / "effective-scientific-settings.json").read_text())
        actual_settings = json.loads((output / "scientific-settings.json").read_text())
        require(same_settings(actual_settings, effective_settings),
                f"{name}: native R effective settings differ from the requested settings")
    worker = check_worker_limits(destination / "parallel", 1 if mode == "serial" else cap) if candidate else None
    if candidate and workflow == "contamination" and mode == "auto":
        outer = [item for item in worker["phase_plans"] if item["label"] == "contamination-samples"]
        require(len(outer) == 1 and outer[0]["tasks"] == families,
                "Contamination must record all input tables in one sample plan")
        if families > 1:
            phase = outer[0]
            require(phase["workload_model"] == "max-loaded-coordinator-rss-x2-and-module-estimate"
                    and phase["workers"] == min(families, phase["worker_ceiling"], phase["memory_worker_limit"]),
                    "Contamination sample workers must fit measured table and coordinator memory")
    if candidate and families > 1 and mode == "auto":
        # Millisecond workloads need not overlap on a loaded host. Require real
        # child execution here; the controlled scheduler barrier test proves overlap.
        require(worker["max_planned_workers"] > 1 and len(worker["observed_child_pids"]) > 1,
                "Parallel qualification requires enough CPU/RAM and actual distinct child workers")
    return {"name": name, "workflow": workflow, "marker": marker, "candidate": candidate,
            "elapsed_seconds": round(time.monotonic() - start, 3), "status": "passed",
            "mode": mode, "max_workers": cap, "batch_size": families,
            "worker_evidence": worker, "rows": rows,
            "variant": {"minimum": minimum, "include_zero": include_zero,
                        "metadata": metadata, "mismatch": mismatch},
            "inputs_unchanged": True, "input_sha256": input_hashes,
            "output_sha256": tree_hashes(output),
            "summary_sha256": file_hash(output / SUMMARIES[workflow]),
            "log_sha256": {item.name: file_hash(item) for item in (destination / "stdout.log", destination / "stderr.log")},
            "scientific_settings": effective_settings, "settings_match": True if candidate else None}


def qualify(destination, full=False, runtime=None):
    reference = verify_frozen_sources()
    verifier_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixture_hashes = tree_hashes(FIXTURE)
    source_hashes = {str(path): file_hash(path) for path in
                     [*(CANDIDATE_ROOT / name for name in SOURCES.values()),
                      *(HELPER_ROOT / name for name in HELPERS), Path(__file__)]}
    results = []
    pairs = []
    comparison_evidence = {}
    try:
        for marker in ("SNP", "DNP"):
            for workflow, variants in (("cpin", [{}]),
                                       ("cpi", [{}, {"minimum": 1}, {"minimum": 5}, {"metadata": True}, {"mismatch": True}]),
                                       ("contamination", [{}, {"include_zero": False}])):
                for index, variant in enumerate(variants):
                    case = f"{marker}-{workflow}-{index}"
                    wanted = run_case(destination, case + "-reference", workflow, marker, candidate=False, **variant)
                    results.append(wanted)
                    actual = run_case(destination, case + "-candidate", workflow, marker, **variant)
                    results.append(actual)
                    compare_tables(actual["rows"], wanted["rows"])
                    if workflow == "cpin":
                        for row in actual["rows"]:
                            sites = row["Trio"] + "_sites.txt"
                            compare_tables(table(destination / actual["name"] / "output" / sites),
                                           table(destination / wanted["name"] / "output" / sites))
                    pairs.append(case)
                    comparison_evidence[case] = {"equal": True,
                        "candidate_sha256": actual["summary_sha256"],
                        "reference_sha256": wanted["summary_sha256"]}
            if full:
                for workflow in ("cpin", "cpi", "contamination"):
                    for count in (2, 3, 5):
                        baseline = None
                        for mode, cap in (("serial", None), ("auto", None), ("auto", 2)):
                            name = f"{marker}-{workflow}-batch{count}-{mode}-cap{cap}"
                            result = run_case(destination, name, workflow, marker, families=count, mode=mode, cap=cap)
                            results.append(result)
                            if baseline is None:
                                baseline = result["rows"]
                            else:
                                compare_tables(result["rows"], baseline)
        require(tree_hashes(FIXTURE) == fixture_hashes, "Qualification fixtures changed during execution")
        require(all(file_hash(path) == sha for path, sha in source_hashes.items()),
                "Qualification source changed during execution")
        report = {"schema_version": 2, "status": "passed", "verification_script_sha256": verifier_hash,
                  "runtime": runtime or {"kind": "local-R"},
                  "upstream_reference": reference, "full_batch_matrix": full,
                  "scope": "CPI/CPIN/Contamination science from SNP and DNP count tables; caller BAM qualification is separate",
                  "reference_comparisons": pairs, "reference_comparison_evidence": comparison_evidence,
                  "inputs_unchanged": True, "source_unchanged": True, "fixture_sha256": fixture_hashes,
                  "hash_scope": "Raw execution bytes before archive path redaction; reference equality compares numerical fields, not PDF bytes",
                  "results": results}
    except Exception as error:
        report = {"schema_version": 2, "status": "failed", "verification_script_sha256": verifier_hash,
                  "runtime": runtime or {"kind": "local-R"},
                  "error": f"{type(error).__name__}: {error}", "results": results}
        (destination / REPORT_NAME).write_text(json.dumps(report, indent=2) + "\n")
        raise
    (destination / REPORT_NAME).write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    global CANDIDATE_ROOT, HELPER_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New, empty directory for all evidence")
    parser.add_argument("--full", action="store_true", help="Also run 2/3/5 batches in serial, auto and capped modes")
    parser.add_argument("--image", help="Qualify the actual installed payload in this immutable Docker image")
    parser.add_argument("--installed-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--image-id", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.image and not shutil.which("Rscript"):
        parser.error("Rscript is required; activate the scientific runtime")
    if args.output:
        destination = args.output.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            parser.error("--output must be empty")
    else:
        destination = Path(tempfile.mkdtemp(prefix="nipat-0850-qualification-"))
    if args.image:
        if args.installed_root or args.image_id:
            parser.error("--image cannot be combined with internal container options")
        report = qualify_image(args.image, destination, args.full)
    else:
        runtime = {"kind": "local-R"}
        if args.installed_root:
            bundle = args.installed_root.resolve()
            hashes = verify_installed_payload(bundle)
            runtime = {"kind": "installed-image", "image_id": args.image_id,
                       "candidate_and_helper_sha256": hashes}
        else:
            bundle, hashes = snapshot_local_payload(destination)
            runtime["candidate_and_helper_sha256"] = hashes
        CANDIDATE_ROOT = bundle / "scientific/vendor/NEWPAT"
        HELPER_ROOT = bundle / "lib/nipat_scientific"
        sys.path.insert(0, str(bundle / "lib"))
        runtime.update({"candidate_root": str(CANDIDATE_ROOT), "helper_root": str(HELPER_ROOT)})
        version = subprocess.run(["Rscript", "--version"], capture_output=True, text=True, check=True)
        runtime["r_version"] = (version.stdout + version.stderr).strip()
        report = qualify(destination, args.full, runtime)
    print(f"{len(report['results'])} R executions passed; evidence: {destination / REPORT_NAME}")


if __name__ == "__main__":
    main()
