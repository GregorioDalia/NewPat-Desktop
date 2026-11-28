"""The mini-suite must separate numerical regressions from actual process overlap."""
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

from scripts import mini_suite_macos as mini


ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("peaks,expected", [
    ([(4, 2), (1, 1)], "Più processi"),
    ([(4, 1), (1, 1)], "Da verificare"),
    ([(4, None), (1, 1)], "Misure incomplete"),
    ([(1, 1), (1, 1)], "Un processo"),
    ([], "Nessuna misura"),
])
def test_planned_concurrency_is_not_reported_as_observed(peaks, expected):
    observations = [("DNP", None, planned, observed, "") for planned, observed in peaks]
    assert mini.parallel_verdict(observations).startswith(expected)


def test_samtools_window_uses_elapsed_time_not_sum_of_overlapping_tasks():
    intervals = [{"started_at_unix": 4, "finished_at_unix": 7}, {"started_at_unix": 3, "finished_at_unix": 6}]
    assert mini.process_window(intervals) == 4
    assert mini.process_window([*intervals, {"started_at_unix": 4}]) is None


@pytest.mark.parametrize("problem,expected_code", [("none", 0), ("runtime", 1), ("oracle", 1),
                                                   ("prepare", 1), ("wrong-build", 1)])
def test_mini_records_failures_and_completes_independent_cases(tmp_path, monkeypatch, problem, expected_code):
    app, output = tmp_path / "app", tmp_path / "output"
    output.mkdir()
    commit, image = "a" * 40, "sha256:" + "b" * 64
    write(app / ".distribution/macos-manifest.json", {"architecture": "arm64", "scientific_platform": "linux/arm64",
                                                      "source_commit": commit, "version": "0.9.99"})
    pinned = tmp_path / "source-commit"
    pinned.write_text("c" * 40 if problem == "wrong-build" else commit)
    state = tmp_path / "Library/Application Support/NewPat-Desktop/.runtime/macos/runtime.json"
    write(state, {"phase": "ready", "source_commit": commit, "runtime_image": image})
    monkeypatch.syspath_prepend(str(ROOT / "scripts/acceptance"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mini.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(mini.platform, "mac_ver", lambda: ("14", None, None))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    launches, checked = [], []

    def validate(run):
        checked.append(run.name)
        if problem == "oracle" and run.name == "sesso":
            raise ValueError("Tabella diversa dal riferimento")
        return "Verificato"

    cases = [mini.Case(name, ["workflow", "analyze"], validate) for name in mini.TITLES]
    monkeypatch.setattr(mini, "prepare_cases", lambda *args: cases)

    def launch(_launcher, args, log):
        if args == ["--runtime", "prepare"]:
            if problem == "prepare":
                raise ValueError("Preparazione fallita")
            return
        name = args[args.index("--run-name") + 1]
        launches.append(name)
        assert "--performance-diagnostics" not in args and args[args.index("--execution-mode") + 1] == "auto"
        run = output / "run" / name
        if problem == "runtime" and name == "prenatale":
            write(run / "run.json", {"commands": [{"returncode": 255}]})
            write(run / "output/workflow/workflow-state.json", {"steps": [{"id": "dnp", "status": "running",
                                                                           "workflow": "dnp-call"}]})
            raise ValueError("Il launcher è terminato con codice 1")
        write(run / "run.json", {"status": "succeeded", "engine_verification": "verified",
                                 "runtime": {"image_id": image, "architecture": "arm64"},
                                 "execution_options": {"execution_mode": "auto", "performance_diagnostics": False},
                                 "commands": [{"status": "succeeded"}]})

    monkeypatch.setattr(mini, "launch", launch)
    assert mini.run_suite(app, output, pinned) == expected_code
    html = (output / mini.REPORT).read_text(encoding="utf-8")
    assert f"Mini-suite NewPat · {'PASS' if not expected_code else 'FAIL'}</h1>" in html
    if problem in ("prepare", "wrong-build"):
        assert not launches and html.count("NON ESEGUITO") == 3
    else:
        assert launches == list(mini.TITLES) and "calling" in checked
        if problem == "runtime":
            assert "Codice del runtime 255" in html and "Fase DNPcall" in html and "prenatale" not in checked
        elif problem == "oracle":
            assert "Tabella diversa dal riferimento" in html


def test_downloadable_kit_matches_the_tested_sources_and_launches_from_finder():
    paths = ["installer/macos/Mini-Test-NewPat.command", "scripts/mini_suite_macos.py", "docs/MINI_SUITE_MAC.md"]
    archive = ROOT / "docs/validation/NewPat-0.9.99-Mini-Test-Mac.zip"
    with ZipFile(archive) as kit:
        assert sorted(kit.namelist()) == sorted(Path(path).name for path in paths)
        for path in paths:
            assert kit.read(Path(path).name) == (ROOT / path).read_bytes()
        assert kit.getinfo("Mini-Test-NewPat.command").external_attr >> 16 & 0o111 == 0o111
