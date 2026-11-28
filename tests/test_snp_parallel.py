"""Exercise bounded SNP worker processes, state ownership and descendant cleanup."""

import errno
import gzip
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import Mock, patch

from newpat_scientific.executor import _atomic_json, _Cancellation, execute_plan
from newpat_scientific.parallel import THREAD_LIMITS
from newpat_scientific.snp_parallel import (
    _indexed_observations, _kill_group, _ProbeWindow, _query_budget, _sample_estimate, execute_independent_snp_steps,
)


FAKE_R = r'''
import json, os, pathlib, signal, subprocess, sys, time
args = sys.argv[1:]
if args[0] == "-e":
    assert "memory_mib=m, workload_observed=observed" in args[1]
    tasks = int(args[-2])
    estimate = None if args[-1] == "unknown" else int(args[-1])
    capacity = int(os.environ.get("SNP_FIXTURE_MEMORY_MIB", 16384))
    slots = max(1, capacity // estimate) if estimate else 1
    cap = int(os.environ.get("NEWPAT_MAX_WORKERS") or tasks)
    print(json.dumps({"mode":"auto", "max_workers":cap, "workers":min(tasks,cap,slots),
                      "tasks":tasks, "memory_budget_mib":capacity+60, "coordinator_rss_mib":60,
                      "memory_per_worker_mib":estimate, "reason":"controlled-test-budget"}))
    raise SystemExit(0)
if pathlib.Path(args[0]).name == "contamination.R":
    selected, output = pathlib.Path(args[2]), pathlib.Path(args[3])
    (output / "scientific-settings.json").write_bytes(pathlib.Path(os.environ["NEWPAT_SCIENTIFIC_SETTINGS"]).read_bytes())
    names = [source.stem for source in sorted(selected.iterdir())]
    for name in names:
        (output / ("contamination_" + name + ".txt")).write_text("chr\tpos\tcontamination\nchr1\t10\t0.01\n")
    (output / "contamination_summary.txt").write_text("individuo\tinformative_sites\tmean_contamination\tsd_contamination\n" +
        "".join(name + "\t1\t0.01\tNA\n" for name in names))
    raise SystemExit(0)
work = pathlib.Path.cwd()
(work / "observed-environment.json").write_text(json.dumps(dict(os.environ)))
mode = os.environ.get("SNP_FIXTURE_MODE", "normal")
if mode != "normal":
    child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(120)"])
    (work / "descendant.pid").write_text(str(child.pid))
    if mode == "fail" and "snp0" in str(work):
        time.sleep(.4)
        raise SystemExit(17)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(120)
time.sleep(.25)
out = pathlib.Path(args[args.index("--out")+1])
(out.parent / "scientific-settings.json").write_bytes(pathlib.Path(os.environ["NEWPAT_SCIENTIFIC_SETTINGS"]).read_bytes())
out.write_text("chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\tratio\tGL0\tGL1\tGL2\tGT\treads_discarded_for_indels\tratio_reads_discarded_for_indels\tcombined_bases\tcombined_counts\n"
               "chr1\t10\tA\tG\t1\t1\t0\t2\t0.5\t-9.21\t-1.386\t-9.21\t0/1\t0\t0\tA-G\t1-1\n")
summary = out.parent / "summary"
summary.mkdir()
(summary / "SNPcall_AllGenotypes.txt").write_text("chr\tpos\tREF\tALT\tGT_sample_0001\nchr1\t10\tA\tG\t0/1\n")
(summary / "resources.tsv").write_text("sample\tseconds\tresident_MB_start\tresident_MB_end\nsample_0001\t1\t10\t11\n")
(summary / "Unassigned_genotypes.pdf").write_bytes(b"%PDF-fixture\n")
plots = out.parent / "plots/sample_0001"
plots.mkdir(parents=True)
for name in ("N_genotypes", "Ref_read_count", "Alt_read_count", "Other_read_count"):
    (plots / f"sample_0001_{name}.pdf").write_bytes(b"%PDF-fixture\n")
'''


@unittest.skipUnless(os.name == "posix", "Scientific batch execution runs inside Linux")
class SnpParallelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="newpat-snp-batch-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        executable = self.bin / "Rscript"
        executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_R), encoding="utf-8")
        executable.chmod(0o755)
        self.script = self.root / "SNPcall.R"
        self.script.write_text("# fixture executable is supplied by PATH\n")
        panel = self.root / "panel.tsv"
        panel.write_text("chr\tpos\tref\talt\nchr1\t10\tA\tG\n")
        self.plan = {"schema_version": 1, "samples": [], "steps": []}
        for index in range(3):
            pileup = self.root / f"sample{index}.pileup"
            pileup.write_text("chr1\t10\tA\t2\t.G\tII\tread1,read2\n")
            self.plan["samples"].append({"id": f"sample{index}", "kind": "snp-pileup", "path": str(pileup)})
            self.plan["steps"].append({"id": f"snp{index}", "workflow": "snp-call",
                "inputs": {"sample": f"sample{index}", "panel": str(panel), "reference": None},
                "parameters": {"mode": "pileup"}})
        self.environment = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                            "NEWPAT_PARALLEL_CHILD": "", "NEWPAT_EXECUTION_MODE": "auto", "NEWPAT_MAX_WORKERS": ""}

    def execute(self, run, **environment):
        with patch.dict(os.environ, {**self.environment, **environment}), \
                patch("newpat_scientific.snp_summary.finalize_snp_summaries", return_value=[]):
            return execute_plan(self.plan, run_dir=run, script_paths={"snp-call": self.script})

    def table_values(self, state, run):
        return {record["id"]: (run / record["artifacts"]["snp-tables"][0]["path"]).read_bytes()
                for record in state["steps"]}

    def test_three_samples_auto_and_manual_two_equal_serial_without_nested_workers(self):
        serial_dir = self.root / "serial"
        serial = self.execute(serial_dir, NEWPAT_EXECUTION_MODE="serial")
        self.assertEqual(serial["status"], "succeeded", serial)
        expected = self.table_values(serial, serial_dir)
        self.assertFalse((serial_dir / "parallel/snp").exists())
        for mode, cap, expected_workers in (("auto", "", 3), ("manual", "2", 2)):
            run = self.root / mode
            state = self.execute(run, NEWPAT_MAX_WORKERS=cap)
            self.assertEqual(state["status"], "succeeded", state)
            self.assertEqual(expected, self.table_values(state, run))
            self.assertEqual(state, json.loads((run / "workflow-state.json").read_text()))
            self.assertEqual(state["snp_parallel"]["workers"], expected_workers)
            events = [json.loads(line) for file in (run / "parallel/snp").glob("worker-*.jsonl")
                      for line in file.read_text().splitlines()]
            intervals = sorted((row["observed_at_unix"], 1 if row["event"] == "task-start" else -1)
                               for row in events if row["event"] in {"task-start", "task-end"})
            active = maximum = 0
            for _timestamp, change in intervals:
                active += change
                maximum = max(maximum, active)
            self.assertEqual(active, 0)
            self.assertEqual(maximum, expected_workers)
            for record in state["steps"]:
                observed = json.loads((run / record["work_dir"] / "observed-environment.json").read_text())
                self.assertEqual(observed["NEWPAT_PARALLEL_CHILD"], "1")
                self.assertEqual(observed["NEWPAT_MAX_WORKERS"], "1")
                self.assertTrue(all(observed[key] == "1" for key in THREAD_LIMITS))
                worker_state = json.loads((run / "parallel/snp" / f"state-{record['id']}.json").read_text())
                self.assertEqual(record, worker_state)

    def test_mixed_costs_limit_the_active_sum_and_keep_small_samples_parallel(self):
        run = self.root / "low-memory"
        # The fake R budget enforces the passed MiB, a CPU cap of 3 would
        # otherwise admit three samples. Changing input size affects admission.
        pileup = Path(self.plan["samples"][2]["path"])
        with pileup.open("a") as stream:
            stream.write("chr1\t10\tA\t1\t.\tI\t" + "x" * (2 * 1024 * 1024) + "\n")
        state = self.execute(run, NEWPAT_MAX_WORKERS="3", SNP_FIXTURE_MEMORY_MIB="3200")
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(state["snp_parallel"]["workers"], 2)
        directory = run / "parallel/snp"
        estimates = json.loads((directory / "sample-estimates.json").read_text())
        self.assertGreater(estimates["snp2"]["memory_mib"], 1600)
        self.assertLess(estimates["snp0"]["memory_mib"], 1000)
        active = self.active_sets(directory)
        self.assertIn({1, 2}, active)
        for tasks in active:
            self.assertLessEqual(sum(estimates[f"snp{i-1}"]["charge_mib"] for i in tasks), 3200)

    @staticmethod
    def active_sets(directory):
        events = [json.loads(line) for path in directory.glob("worker-*.jsonl")
                  for line in path.read_text().splitlines()]
        intervals = sorted((event["observed_at_unix"], event["event"] == "task-start", event["task_index"])
                           for event in events if event["event"] in {"task-start", "task-end"})
        active = set()
        observed = []
        for _, started, index in intervals:
            if started:
                active.add(index)
            else:
                active.remove(index)
            if active:
                observed.append(active.copy())
        return observed

    def test_later_small_jobs_fill_capacity_without_overlapping_two_heavy_jobs(self):
        sizes = [1400, 1400, 400, 400, 400]
        for index in (3, 4):
            self.plan["steps"].append({**self.plan["steps"][2], "id": f"snp{index}"})
        def estimate(step, source, directory, probe):
            return sizes[int(step["id"][-1])] * 1024**2, {"basis": "fixture"}
        run = self.root / "weighted"
        with patch("newpat_scientific.snp_parallel._sample_estimate", side_effect=estimate):
            state = self.execute(run, NEWPAT_MAX_WORKERS="4", SNP_FIXTURE_MEMORY_MIB="1900")
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(state["snp_parallel"]["workers"], 3)
        observed = self.active_sets(run / "parallel/snp")
        self.assertTrue(any(1 in jobs and any(i > 2 for i in jobs) for jobs in observed))
        self.assertTrue(all(sum(sizes[i - 1] for i in jobs) <= 1900 for jobs in observed))
        self.assertEqual([step["id"] for step in state["steps"]], [f"snp{i}" for i in range(len(sizes))])

    def test_unknown_first_preserves_inner_budget_and_runs_apart_from_two_small_samples(self):
        run = self.root / "heterogeneous"
        def estimate(step, source, directory, probe):
            size = None if step["id"] == "snp0" else 800 * 1024**2
            return size, {"basis": "fixture"}
        with patch("newpat_scientific.snp_parallel._sample_estimate", side_effect=estimate):
            state = self.execute(run, NEWPAT_MAX_WORKERS="3", SNP_FIXTURE_MEMORY_MIB="2200")
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(state["snp_parallel"]["workers"], 2)
        directory = run / "parallel/snp"
        observed = self.active_sets(directory)
        self.assertIn({1}, observed)
        self.assertIn({2, 3}, observed)
        self.assertTrue(all(1 not in tasks or len(tasks) == 1 for tasks in observed))
        self.assertEqual([s["id"] for s in state["steps"]], ["snp0", "snp1", "snp2"])
        for index, record in enumerate(state["steps"]):
            env = json.loads((run / record["work_dir"] / "observed-environment.json").read_text())
            self.assertEqual(env["NEWPAT_PARALLEL_CHILD"], "" if index == 0 else "1")
            self.assertEqual(env["NEWPAT_MAX_WORKERS"], "3" if index == 0 else "1")

    def test_bam_estimate_uses_decompressed_records_or_bounded_depth_then_real_panel_count(self):
        reference = self.root / "reference.fa"
        Path(str(reference) + ".fai").write_text("chr1\t5000\t0\t5000\t5001\n")
        source = self.root / "reads.bam"
        source.write_bytes(gzip.compress(b"BAM\1" + bytes(396)))
        step = {**self.plan["steps"][0], "inputs": {**self.plan["steps"][0]["inputs"],
                "reference": str(reference)}, "parameters": {"mode": "bam"}}
        size, observation = _sample_estimate(step, source, self.root, _Cancellation())
        self.assertGreater(size, 0)
        self.assertEqual(observation["observations"], 3 * (400 // 36))
        self.assertEqual(observation["largest_target_contig"], 5000)
        # A highly compressible large workload is not admitted as a small BAM.
        source.write_bytes(gzip.compress(b"BAM\1" + bytes(1024 * 1024)))
        self.assertIsNone(_sample_estimate(step, source, self.root, _Cancellation())[0])
        step["parameters"]["scientific_settings"] = {"max_depth": 200}
        _, bounded = _sample_estimate(step, source, self.root, _Cancellation())
        self.assertEqual((bounded["basis"], bounded["observations"]), ("configured-bam-depth", 600))
        step["parameters"].pop("scientific_settings")
        source.with_suffix(".bai").touch()

        def count(command, directory, path, cancellation):
            if command[1] == "view":
                self.assertEqual(command[:5], ["samtools", "view", "--no-PG", "-H", "-o"])
                Path(command[-2]).write_text("@HD\tSO:coordinate\n@SQ\tSN:chr1\tLN:5000\n")
            else:
                self.assertEqual(command[:6], ["samtools", "bedcov", "-g", "0x704", "-c", "--max-depth"])
                self.assertEqual(Path(command[-2]).read_text(), "chr1\t8\t11\n")
                path.write_text("chr1\t8\t11\t31\t12\n")
            self.assertEqual(command[-1], str(source))
            return 0

        with patch("newpat_scientific.executor._run_process", side_effect=count):
            _, counted = _sample_estimate(step, source, self.root, _Cancellation())
        self.assertEqual((counted["basis"], counted["observations"]), ("indexed-window-coverage", 31))
        self.assertEqual(counted["peak_depth_bound"], 12)
        os.utime(source.with_suffix(".bai"), ns=(1, 1))
        with patch("newpat_scientific.executor._run_process") as probe:
            self.assertIsNone(_sample_estimate(step, source, self.root, _Cancellation())[0])
            probe.assert_not_called()
        source.with_suffix(".bai").touch()
        panel = Path(step["inputs"]["panel"])
        panel.write_text("chr\tpos\tref\talt\n" + "".join(f"chr1\t{i}\tA\tG\n" for i in range(10, 2059)))
        with patch("newpat_scientific.executor._run_process") as probe:
            self.assertIsNone(_sample_estimate(step, source, self.root, _Cancellation())[0])
            probe.assert_not_called()

    def test_unusable_bam_header_or_probe_io_reverts_to_normal_calling(self):
        reference = self.root / "ref.fa"
        Path(str(reference) + ".fai").write_text("chr1\t50\t0\t50\t51\n")
        path = self.root / "large.bam"
        with path.open("wb") as handle:
            handle.truncate(2 * 1024 * 1024)
        path.with_suffix(".bai").touch()
        steps = [{**step, "inputs": {**step["inputs"], "reference": str(reference)},
                  "parameters": {"mode": "bam"}} for step in self.plan["steps"]]
        source = {step["inputs"]["sample"]: str(path) for step in steps}
        from newpat_scientific.executor import _run_process
        for case in ("header-length", "unsorted", "samtools-error", "wrong-region", "io"):
            with self.subTest(case=case):
                directory = self.root / case
                directory.mkdir()

                def run(command, work, log, cancellation):
                    if command[0] == "Rscript":
                        return _run_process(command, work, log, cancellation)
                    if case == "io":
                        raise OSError("temporary input error")
                    if command[1] == "view":
                        header = "@HD\tSO:" + ("unsorted" if case == "unsorted" else "coordinate")
                        length = 51 if case == "header-length" else 50
                        Path(command[-2]).write_text(header + f"\n@SQ\tSN:chr1\tLN:{length}\n")
                    elif case == "samtools-error":
                        return 1
                    else:
                        log.write_text("chr1\t9\t12\t10\t4\n")
                    return 0

                with patch.dict(os.environ, self.environment), patch(
                        "newpat_scientific.executor._run_process", side_effect=run):
                    result, _ = _query_budget(steps, source, directory, _Cancellation())
                self.assertEqual(result["workers"], 1)
                estimates = json.loads((directory / "sample-estimates.json").read_text())
                self.assertIsNone(estimates["snp0"]["memory_mib"])

    @unittest.skipUnless(shutil.which("samtools"), "requires real samtools")
    def test_real_indexed_projection_counts_overlaps_indels_skips_and_flagged_reads(self):
        sam = self.root / "reads.sam"
        source = self.root / "reads.bam"
        header = "@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chr1\tLN:10000\n"
        sam.write_text(header + "".join(
            f"read{i}\t{flag}\tchr1\t10\t60\t{cigar}\t*\t0\t0\t{'A' * length}\t{'I' * length}\n"
            for i, (flag, cigar, length) in enumerate(((0, "4M2D4M", 8), (0, "3M4N3M", 6),
                                                       (0, "2M3I3M", 8), (1024, "5M", 5)))))
        subprocess.run(["samtools", "view", "-b", "-o", str(source), str(sam)], check=True)
        subprocess.run(["samtools", "index", str(source)], check=True)
        positions = [("chr1", 13), ("chr1", 14)] + [("chr1", i) for i in range(30, 1030)]
        self.assertEqual(_indexed_observations(source, positions, {"chr1": 10000}, self.root,
                                               "sparse", _ProbeWindow(_Cancellation())), (22, 4))

        sam.write_text(header + "".join(
            f"high{i}\t0\tchr1\t10\t60\t10M\t*\t0\t0\tAAAAAAAAAA\tIIIIIIIIII\n"
            for i in range(2100)))
        subprocess.run(["samtools", "view", "-b", "-o", str(source), str(sam)], check=True)
        subprocess.run(["samtools", "index", str(source)], check=True)
        self.assertIsNone(_indexed_observations(source, positions[:1], {"chr1": 10000}, self.root,
                                                "saturated", _ProbeWindow(_Cancellation())))

    def test_expiring_optional_probe_reaps_a_stubborn_descendant_and_does_not_cancel_analysis(self):
        source = self.root / "reads.bam"
        source.touch()
        source.with_suffix(".bai").touch()
        fake = self.bin / "samtools"
        ext = self.root / "descendant.pid"
        fake.write_text(f"#!{sys.executable}\n" + textwrap.dedent(f"""
            import pathlib, signal, subprocess, sys, time
            if sys.argv[1] == "view":
                pathlib.Path(sys.argv[-2]).write_text("@HD\\tSO:coordinate\\n@SQ\\tSN:chr1\\tLN:100\\n")
            else:
                child = subprocess.Popen([sys.executable, "-c",
                    "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)"])
                pathlib.Path({str(ext)!r}).write_text(str(child.pid))
                time.sleep(20)
        """))
        fake.chmod(0o755)
        real = _Cancellation()
        with patch.dict(os.environ, self.environment), patch("newpat_scientific.snp_parallel._PROBE_SECONDS", .7):
            self.assertIsNone(_indexed_observations(source, [("chr1", 12)], {"chr1": 100}, self.root,
                                                    "timeout", _ProbeWindow(real)))
        self.assertIsNone(real.signum)
        self.assertTrue(ext.exists())
        self.assert_descendants_stopped(self.root)

    def test_all_unknown_inputs_are_recorded_and_request_only_one_worker(self):
        directory = self.root / "admission"
        directory.mkdir()
        paths = {item["id"]: item["path"] for item in self.plan["samples"]}
        with patch.dict(os.environ, self.environment), patch(
                "newpat_scientific.snp_parallel._sample_estimate", return_value=(None, {"basis": "unknown"})
        ) as estimate:
            budget, _ = _query_budget(self.plan["steps"], paths, directory, _Cancellation())
        self.assertEqual(estimate.call_count, 3)
        self.assertEqual(budget["workers"], 1)

    def test_mixed_plan_batches_ready_snp_samples_and_registers_each_result_for_downstream(self):
        panel = self.root / "contamination_panel.tsv"
        panel.write_text("chr\tpos\nchr1\t10\n")
        script = self.root / "contamination.R"
        script.write_text("# fake Rscript fixture dispatch\n")
        self.plan["steps"].append({"id": "analysis", "workflow": "contamination", "inputs": {
            "samples": [{"sample": "sample2", "step": "snp2", "output": "snp-tables"},
                        {"sample": "sample0", "step": "snp0", "output": "snp-tables"}],
            "panel": str(panel)}, "parameters": {}})
        with patch.dict(os.environ, {**self.environment, "NEWPAT_MAX_WORKERS": "2"}), \
                patch("newpat_scientific.snp_summary.finalize_snp_summaries", return_value=[]):
            run = self.root / "mixed"
            state = execute_plan(self.plan, run_dir=run,
                script_paths={"snp-call": self.script, "contamination": script})
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(state["snp_parallel"]["workers"], 2)
        self.assertEqual(state["snp_parallel"]["tasks"], 3)
        result = next(row for row in state["steps"] if row["id"] == "analysis")
        self.assertEqual([row["sample"] for row in result["artifacts"]["contamination-tables"]], ["sample2", "sample0"])
        request = json.loads((run / result["request"]).read_text())
        self.assertIn("steps/snp2/output/SNPcall_output.txt", request["samples"][0]["path"])
        self.assertIn("steps/snp0/output/SNPcall_output.txt", request["samples"][1]["path"])
        self.assertTrue(all(row["status"] == "succeeded" for row in state["steps"]))

    def test_ineligible_plans_never_query_a_budget_or_launch_workers(self):
        scenarios = [({"NEWPAT_EXECUTION_MODE": "serial"}, self.plan),
                     ({"NEWPAT_MAX_WORKERS": "1"}, self.plan),
                     ({"NEWPAT_PARALLEL_CHILD": "1"}, self.plan),
                     ({}, {"steps": self.plan["steps"][:1]})]
        with patch("newpat_scientific.snp_parallel._query_budget") as budget:
            for environment, plan in scenarios:
                with self.subTest(environment=environment, plan=plan), patch.dict(os.environ, {**self.environment, **environment}):
                    self.assertFalse(execute_independent_snp_steps(plan, {"steps": [{"id": step["id"], "status": "pending"} for step in plan["steps"]]}, self.root / "unused", {}, _Cancellation(),
                                     atomic_json=_atomic_json))
            budget.assert_not_called()

    def test_darwin_exited_group_permission_error_does_not_mask_the_primary_failure(self):
        for platform, returncode in (("darwin", 0), ("darwin", 17), ("darwin", None), ("linux", 0)):
            with self.subTest(platform=platform, returncode=returncode):
                worker = Mock(pid=123, poll=Mock(return_value=returncode))
                with patch("newpat_scientific.snp_parallel.sys.platform", platform), \
                        patch("newpat_scientific.snp_parallel.os.killpg", side_effect=PermissionError(errno.EPERM, "no signalable members")):
                    if platform == "darwin" and returncode is not None:
                        _kill_group(worker, signal.SIGTERM)
                    else:
                        with self.assertRaises(PermissionError):
                            _kill_group(worker, signal.SIGTERM)

    def test_state_replacement_during_worker_execution_cannot_abort_the_batch(self):
        # A host-mounted filesystem need not let the coordinator open a record
        # while its worker is replacing it. Model that condition at the read
        # boundary, with real worker processes and independently checked tables.
        original_popen = subprocess.Popen
        original_read = Path.read_text
        workers = {}

        def start(command, *args, **kwargs):
            process = original_popen(command, *args, **kwargs)
            if "--worker" in command:
                identifier = Path(command[-1]).stem.removeprefix("job-")
                workers[f"state-{identifier}.json"] = process
            return process

        def read(path, *args, **kwargs):
            process = workers.get(path.name)
            if process is not None and process.poll() is None:
                raise PermissionError(errno.EACCES, "record is being replaced", str(path))
            return original_read(path, *args, **kwargs)

        run = self.root / "concurrent-replacement"
        with patch("newpat_scientific.snp_parallel.subprocess.Popen", side_effect=start), \
                patch.object(Path, "read_text", read):
            state = self.execute(run)
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(len(self.table_values(state, run)), 3)
        self.assertTrue(all(process.poll() == 0 for process in workers.values()))

    def test_final_state_visibility_recovers_without_restarting_workers(self):
        original_read = Path.read_text
        failures = {}

        def read(path, *args, **kwargs):
            if path.name.startswith("state-snp"):
                attempt = failures.get(path.name, 0)
                failures[path.name] = attempt + 1
                if attempt == 0:
                    raise FileNotFoundError(errno.ENOENT, "record temporarily unavailable", str(path))
                if attempt == 1:
                    return ""  # temporarily incomplete content must not be merged
            return original_read(path, *args, **kwargs)

        run = self.root / "delayed-visibility"
        with patch.object(Path, "read_text", read):
            state = self.execute(run)
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual(len(self.table_values(state, run)), 3)
        self.assertEqual(len(list((run / "parallel/snp").glob("job-*.json"))), 3)
        self.assertEqual(set(failures), {"state-snp0.json", "state-snp1.json", "state-snp2.json"})

    def test_unreadable_final_state_fails_with_details_and_preserves_cleanup(self):
        original_read = Path.read_text
        for failure in ("missing", "malformed", "wrong-identity"):
            with self.subTest(failure=failure):
                def read(path, *args, **kwargs):
                    if path.name == "state-snp0.json":
                        if failure == "missing":
                            raise FileNotFoundError(errno.ENOENT, "record never became readable", str(path))
                        if failure == "malformed":
                            return "{broken"
                        record = json.loads(original_read(path, *args, **kwargs))
                        record["id"] = "another-sample"
                        return json.dumps(record)
                    return original_read(path, *args, **kwargs)

                run = self.root / failure
                with patch.object(Path, "read_text", read):
                    state = self.execute(run, NEWPAT_MAX_WORKERS="2")
                self.assertEqual(state["status"], "failed", state)
                self.assertEqual(state["error"]["code"], "execution.worker_state", state["error"])
                self.assertIn("state-snp0.json", state["error"]["message"])
                if failure != "wrong-identity":
                    self.assertIn("FileNotFoundError" if failure == "missing" else "JSONDecodeError",
                                  state["error"]["message"])
                self.assertEqual(state, json.loads((run / "workflow-state.json").read_text()))
                self.assertTrue(all(item["status"] not in {"pending", "running"}
                                    for item in state["steps"]))
                self.assertFalse((run / "snp_summary").exists())

    def test_insufficient_shared_budget_falls_back_to_serial_execution(self):
        run = self.root / "limited"
        with patch("newpat_scientific.snp_parallel._query_budget", return_value=({"workers": 1, "tasks": 3, "reason": "memory"}, {})):
            state = self.execute(run)
        self.assertEqual(state["status"], "succeeded", state)
        self.assertFalse(list((run / "parallel/snp").glob("job-*.json")))

    def assert_descendants_stopped(self, run):
        descendants = [int(file.read_text()) for file in run.rglob("descendant.pid")]
        self.assertGreaterEqual(len(descendants), 1)
        for pid in descendants:
            # A killed child can briefly remain a zombie until the host reaps it.
            status = Path(f"/proc/{pid}/stat")
            deadline = time.monotonic() + 3
            while status.exists() and status.read_text().split()[2] != "Z" and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(not status.exists() or status.read_text().split()[2] == "Z", f"Live orphan {pid}")

    def test_failure_stops_running_siblings_and_does_not_start_pending_sample(self):
        run = self.root / "failed"
        state = self.execute(run, NEWPAT_MAX_WORKERS="2", SNP_FIXTURE_MODE="fail")
        self.assertEqual(state["status"], "failed", state)
        self.assertEqual(state["exit_code"], 17)
        self.assertEqual(state["steps"][0]["status"], "failed")
        self.assertEqual(state["steps"][0]["exit_code"], 17)
        self.assertEqual(state["steps"][1]["status"], "cancelled")
        self.assertEqual(state["steps"][2]["status"], "blocked")
        self.assertFalse((run / "steps/snp2").exists())
        self.assert_descendants_stopped(run)

    def test_cleanup_read_error_preserves_original_worker_failure_and_stops_siblings(self):
        original_read = Path.read_text

        def read(path, *args, **kwargs):
            if path.name == "state-snp1.json":
                raise PermissionError(errno.EACCES, "cancelled sibling state unavailable", str(path))
            return original_read(path, *args, **kwargs)

        run = self.root / "failed-with-unreadable-sibling"
        with patch.object(Path, "read_text", read):
            state = self.execute(run, NEWPAT_MAX_WORKERS="2", SNP_FIXTURE_MODE="fail")
        self.assertEqual(state["status"], "failed", state)
        self.assertEqual(state["exit_code"], 17)
        self.assertEqual(state["error"]["code"], "execution.process")
        self.assertEqual([item["status"] for item in state["steps"]], ["failed", "cancelled", "blocked"])
        diagnostic = state["steps"][1]["state_read_error"]
        self.assertEqual(diagnostic["code"], "execution.worker_state")
        self.assertIn("PermissionError", diagnostic["message"])
        self.assertEqual(state, json.loads((run / "workflow-state.json").read_text()))
        self.assertFalse((run / "steps/snp2").exists())
        self.assert_descendants_stopped(run)

    def test_cancellation_persists_state_and_kills_stubborn_grandchildren(self):
        run = self.root / "cancelled"
        config = self.root / "config.json"
        config.write_text(json.dumps({"plan": self.plan, "run": str(run), "script": str(self.script)}))
        code = ("import json,sys; from pathlib import Path; from unittest.mock import patch; "
                "from newpat_scientific.executor import execute_plan; c=json.load(open(sys.argv[1])); "
                "p=patch('newpat_scientific.snp_summary.finalize_snp_summaries',return_value=[]); p.start(); "
                "execute_plan(c['plan'],run_dir=Path(c['run']),script_paths={'snp-call':Path(c['script'])})")
        environment = {**os.environ, **self.environment, "NEWPAT_MAX_WORKERS": "2", "SNP_FIXTURE_MODE": "cancel"}
        with (self.root / "coordinator.log").open("wb") as log:
            coordinator = subprocess.Popen([sys.executable, "-c", code, str(config)], env=environment, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 10
                while len(list(run.rglob("descendant.pid"))) < 2 and coordinator.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertEqual(len(list(run.rglob("descendant.pid"))), 2)
                coordinator.send_signal(signal.SIGTERM)
                coordinator.wait(timeout=10)
            finally:
                if coordinator.poll() is None:
                    coordinator.kill()
                    coordinator.wait()
        state = json.loads((run / "workflow-state.json").read_text())
        self.assertEqual(state["status"], "cancelled", state)
        self.assertEqual(state["exit_code"], 143)
        self.assertEqual([item["status"] for item in state["steps"]], ["cancelled", "cancelled", "blocked"])
        self.assert_descendants_stopped(run)


if __name__ == "__main__":
    unittest.main()
