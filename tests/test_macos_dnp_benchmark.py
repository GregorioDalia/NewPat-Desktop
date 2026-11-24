import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import benchmark_macos_dnp as benchmark


def test_startup_report_separates_existing_checks_without_timing_additional_commands():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def stamp(seconds):
        return start.replace(second=seconds).isoformat()
    record = {
        "commands": [{"started_at": stamp(12)}],
        "checks": [
            {"argv": ["python", "-c", "runpy...", "/app/src", "ensure"],
             "started_at": stamp(2), "finished_at": stamp(6)},
            {"argv": ["limactl", "shell", "docker", "run", "python3", "/opt/nipat/engine/main.py", "describe", "--json"],
             "started_at": stamp(7), "finished_at": stamp(9)},
            {"argv": ["docker", "inspect"], "started_at": stamp(9), "finished_at": stamp(11)},
        ],
    }
    assert benchmark.startup_timings(record, start) == {
        "launcher_to_first_command_seconds": 12, "runtime_ensure_seconds": 4, "engine_describe_seconds": 2}
    assert benchmark.startup_timings({}, start) == {}


@pytest.mark.parametrize(("interrupt", "include_four"), [(False, False), (False, True), (True, False)])
def test_benchmark_keeps_native_digests_and_available_diagnostics(tmp_path, monkeypatch, interrupt, include_four):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    app = tmp_path / "NewPat.app"
    write(app / "Contents/Resources/app/.distribution/macos-manifest.json", {
        "version": "test", "architecture": "arm64", "source_commit": "test", "runtime_image": "test",
    })
    inputs = {key: tmp_path / key for key in ("bamlist", "reference", "panel")}
    for path in inputs.values():
        path.touch()
    output = tmp_path / "out"
    monkeypatch.setattr(benchmark.sys, "platform", "darwin")
    monkeypatch.setattr(benchmark.platform, "machine", lambda: "arm64")

    def launch(command, **_kwargs):
        if command[-1] == "prepare":
            return SimpleNamespace(returncode=0)
        assert "--performance-diagnostics" in command
        run = output / "runs" / command[-1]
        if interrupt and run.name == "two-1":
            write(run / "work/dnp-block-progress.json", {"completed_groups": 5, "planned_groups": 12})
            return SimpleNamespace(returncode=130)
        write(run / "run.json", {"status": "succeeded", "resource_snapshot": {}, "resource_budget": {}})
        write(run / "work/dnp-pileup.json", {"strategy": "test"})
        blocks = {"task_count": 2}
        if run.name == "four-1":
            assert command[command.index("--max-workers") + 1] == "4"
            blocks["observed_workers"] = 3
        if run.name == "two-1":
            blocks.update(sample_block_count=4, block_read_count=2, block_logical_bytes_read=200,
                          block_read_seconds=0.1, block_compute_seconds=0.4)
            write(run / "performance/engine/summary.json", {"sampled_memory_max_bytes": 1024})
        write(run / "work/dnp-blocks.json", blocks)
        write(run / "work/scientific-validation.json", {
            "status": "validated", "workflow": "dnp-call", "artifacts": {
                "dnp-tables": [{"sample": "genotype-matrix", "sha256": "a" * 64}],
                "dnp-summary": {"genotypes": {"sha256": "b" * 64}},
            }})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(benchmark.subprocess, "run", launch)
    args = SimpleNamespace(app=app, output_dir=output, rounds=1, include_four=include_four, **inputs)
    if interrupt:
        with pytest.raises(ValueError, match="two-1 failed"):
            benchmark.compare(args)
        failed = json.loads((output / "benchmark.json").read_text())["cases"][-1]
        assert failed["exit_code"] == 130
        assert failed["last_completed_block_work"] == {"completed_groups": 5, "planned_groups": 12}
        return
    benchmark.compare(args)
    report = json.loads((output / "benchmark.json").read_text())
    assert report["initial_prepare_seconds"] >= 0
    assert all(case["startup"] == {} for case in report["cases"])
    assert report["serial_tables_sha256"] == {"samples": {"genotype-matrix": "a" * 64},
                                               "genotype_matrix": "b" * 64}
    serial, two, auto, *extra = report["cases"]
    assert [(case["condition"], case["observed_r_workers"]) for case in extra] == (
        [("four", 3)] if include_four else [])
    assert serial["block_work"] == auto["block_work"] == {"task_count": 2}
    assert two["block_work"]["block_read_count"] == 2 and two["block_work"]["sample_block_count"] == 4
    assert serial["sampled_cgroup_max_bytes"] is None and two["sampled_cgroup_max_bytes"] == 1024
    assert two["observed_kernel_memory_peak_bytes"] is None
    assert all(case["matches_serial_tables"] for case in report["cases"])
