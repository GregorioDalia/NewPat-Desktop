"""Exercise the shipped application in its native window with isolated user data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess


def verify(app: Path, python: Path, workspace: Path, report: Path, screenshot: Path,
           *, timeout: int = 90, scope: str = "packaged-native-application") -> dict:
    if scope not in {"packaged-native-application", "source-native-application"}:
        raise ValueError("Unknown native GUI evidence scope")
    app, python, workspace, report, screenshot = (path.resolve() for path in
                                                 (app, python, workspace, report, screenshot))
    if not (app / "src/nipat/gui/web/index.html").is_file():
        raise ValueError("The actual packaged GUI assets are missing")
    if report.exists() or screenshot.exists():
        raise ValueError("Native GUI evidence must be written to fresh paths")
    workspace.mkdir(parents=True, exist_ok=False)
    report.parent.mkdir(parents=True, exist_ok=True)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(("NIPAT_", "PYTHON", "DOCKER", "COMPOSE"))}
    environment.update({
        "NIPAT_PROJECT_DIR": str(app), "NIPAT_WORKSPACE_DIR": str(workspace),
        "NIPAT_DATA_DIR": str(workspace / "data"), "NIPAT_RUNS_DIR": str(workspace / "runs"),
        "NIPAT_SETTINGS_FILE": str(workspace / "preferences.json"),
    })
    code = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
            "from nipat.cli import main;raise SystemExit(main())")
    subprocess.run([
        str(python), "-I", "-B", "-X", "utf8", "-c", code, str(app / "src"),
        "gui", "--smoke-test", "--smoke-report", str(report),
        "--smoke-screenshot", str(screenshot), "--smoke-timeout", str(timeout),
    ], env=environment, cwd=workspace, check=True, timeout=timeout + 360)
    result = json.loads(report.read_text(encoding="utf-8"))
    result["scope"] = scope
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if (result.get("status") != "passed" or result.get("nativeWebView") is not True
            or result.get("appReady") is not True):
        raise ValueError("The production application did not reach native GUI readiness")
    if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The native application screenshot is missing or invalid")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--scope", choices=("packaged-native-application", "source-native-application"),
                        default="packaged-native-application")
    args = parser.parse_args()
    result = verify(args.app, args.python, args.workspace, args.report, args.screenshot,
                    timeout=args.timeout, scope=args.scope)
    print(json.dumps({"status": "passed", "host": result.get("host"),
                      "appReady": True, "scope": result["scope"]}))


if __name__ == "__main__":
    main()
