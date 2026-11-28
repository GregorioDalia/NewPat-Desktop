#!/usr/bin/env python3
"""Opt-in acceptance evidence on a real, dedicated macOS runner.

Run after installing the same-build .pkg. Keeps the owned VM and all results;
does not edit, stop, or delete user-managed Docker/Lima installations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time


def snapshot(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    files = [path] if path.is_file() else sorted(path.rglob("*"))
    result = {}
    for item in files:
        # User Lima VM disks may be large/running: only inventory ordinary config,
        # not large runtime files. This also avoids reading arbitrary symlinks.
        if item.is_symlink() or not item.is_file() or item.stat().st_size > 1024 * 1024:
            continue
        result[str(item)] = hashlib.sha256(item.read_bytes()).hexdigest()
    return result


def check_cold_start(execute, runtime, project: Path, run_root: Path, image: str) -> dict:
    from installed_suite import verify_run
    from installed_workflows import check_positive_cpi
    from newpat.desktop.examples import save_example_data

    prior_runs = run_root / "self-tests"
    retained = snapshot(prior_runs)
    if not any(Path(name).name == "SNPcall_output.txt" for name in retained):
        raise ValueError("Missing completed SNP result from the preceding numerical self-tests")
    data = run_root / "inputs"
    data.mkdir()
    trio = save_example_data(project, data, "en")
    # The maintenance launcher also holds the exclusive installation lease.
    if subprocess.check_output(runtime.docker_command(["ps", "-q"]), text=True, timeout=30).strip():
        raise ValueError("The dedicated VM is busy; cold-start qualification requires an idle runtime")
    execute("cold-stop", ["--runtime", "stop"], 240)
    if runtime._instance_info()["status"] != "Stopped":
        raise ValueError("Could not verify that the dedicated VM stopped")
    name = "dnp-cpi-after-stop"
    execute("cold-start", [
        "--runs-dir", str(run_root), "workflow", "dnp-cpi", "--run-name", name,
        "--pair", "family_a", str(trio / "alignments/mother.bam"), str(trio / "alignments/father.bam"),
        "--reference", str(trio / "reference/synthetic.fa"), "--panel", str(trio / "panels/dnp.tsv"),
        "--popfreq", str(trio / "frequencies/dnp.tsv"),
    ], 900)
    run = run_root / name
    evidence = verify_run(run, image)
    options = json.loads((run / "run.json").read_bytes())["execution_options"]
    if options["performance_diagnostics"] is not False or options["execution_mode"] != "auto":
        raise ValueError("Cold-start analysis did not use ordinary execution settings")
    evidence.update(check_positive_cpi(run, contamination=False, snp=False, cutoffs=False))
    if snapshot(prior_runs) != retained:
        raise ValueError("Restart altered results or records from the preceding self-tests")
    return evidence


def verify(app: Path, output: Path) -> dict:
    if sys.platform != "darwin":
        raise ValueError("This verification requires a real macOS host with Virtualization.framework.")
    app = app.expanduser().resolve()
    launcher = app / "Contents/Resources/NewPat.command"
    manifest_path = app / "Contents/Resources/app/.distribution/macos-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not launcher.is_file() or manifest.get("channel") != "desktop":
        raise ValueError("An installed desktop package is required.")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Runtime verification report already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    log_root = output.parent / (output.stem + "-logs")
    log_root.mkdir()
    workspace = Path.home() / "Library/Application Support/NewPat-Desktop"
    run_root = workspace / "runs" / ("acceptance-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{time.time_ns()}")
    records = []
    report = {
        "schema_version": 1, "evidence": "real-macos-runtime", "channel": "desktop",
        "version": manifest.get("version"), "source_commit": manifest.get("source_commit"),
        "host_architecture": platform.machine(), "macos_version": platform.mac_ver()[0],
        "package_architecture": manifest.get("architecture"), "runtime_image": None,
        "runs_dir": str(run_root), "checks": records, "passed": False,
    }
    protected = [Path.home() / ".docker/config.json", Path.home() / ".lima/_config"]
    before = {str(path): snapshot(path) for path in protected}

    def execute(name: str, arguments: list[str], timeout: int) -> None:
        log = log_root / (name + ".log")
        started = time.monotonic()
        with log.open("w", encoding="utf-8") as stream:
            try:
                result = subprocess.run([str(launcher), *arguments], stdout=stream, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, check=False, timeout=timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
        records.append({"name": name, "passed": code == 0, "exit_code": code,
                        "seconds": round(time.monotonic() - started, 2), "log": str(log)})
        if code:
            raise RuntimeError(f"{name} failed (exit {code}); see {log}")

    try:
        execute("prepare", ["--runtime", "prepare"], 3600)
        execute("prepare-again", ["--runtime", "prepare"], 600)
        state_path = workspace / ".runtime/macos/runtime.json"
        first_state = json.loads(state_path.read_text())
        execute("doctor", ["doctor", "--runtime"], 600)
        project = app / "Contents/Resources/app"
        sys.path.insert(0, str(project / "src"))
        from newpat.errors import NewPatError
        from newpat.macos_runtime import LimaRuntime
        runtime = LimaRuntime(project, workspace, app / "Contents/Resources/lima/bin/limactl")
        try:
            native = runtime.native_evidence(first_state["runtime_image"])
        except NewPatError as exc:
            raise ValueError(str(exc)) from exc
        if first_state.get("scientific_platform") != native["scientific_platform"]:
            raise ValueError("The prepared guest platform differs from the installed scientific image")
        report.update(native)
        records.append({"name": "native-scientific-runtime", "passed": True})
        execute("numerical-self-tests", ["--runs-dir", str(run_root / "self-tests"), "self-test"], 3600)
        sys.path.insert(0, str(project / "scripts/acceptance"))
        try:
            cold_check = check_cold_start(execute, runtime, project, run_root, first_state["runtime_image"])
        except (NewPatError, AssertionError) as exc:
            raise ValueError(str(exc)) from exc
        records.append({"name": "cold-start-scientific-results", "passed": True, **cold_check})
        execute("doctor-after-restart", ["doctor", "--runtime"], 600)
        second_state = json.loads(state_path.read_text())
        stable = first_state["runtime_image"] == second_state["runtime_image"]
        report["runtime_image"] = second_state["runtime_image"]
        records.append({"name": "image-identity-after-restart", "passed": stable})
        unchanged = all(snapshot(path) == before[str(path)] for path in protected)
        records.append({"name": "external-docker-lima-config-unchanged", "passed": unchanged})
        report["passed"] = all(item["passed"] for item in records)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.app, args.output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
