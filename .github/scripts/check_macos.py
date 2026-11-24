"""Run native macOS client checks without claiming a guest VM was executed."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--desktop-only", action="store_true")
    args = parser.parse_args()
    architecture = platform.machine()
    if platform.system() != "Darwin" or architecture not in {"arm64", "x86_64"}:
        raise SystemExit("Native macOS arm64 or x86_64 is required")
    if architecture != os.environ.get("EXPECTED_ARCHITECTURE"):
        raise SystemExit("The runner architecture does not match its matrix entry")
    major = int(platform.mac_ver()[0].split(".")[0])
    if major < 14:
        raise SystemExit("macOS 14 or later is required")
    commands = [[sys.executable, "-m", "pip", "install", "-r", ".github/quality-requirements.txt"]]
    if args.desktop_only:
        commands.append([sys.executable, "-m", "pytest", "tests", "-k", "gui"])
    else:
        commands.extend((
            [sys.executable, "-m", "pytest", "tests"],
            [sys.executable, "-m", "unittest", "discover", "-s", ".github/scripts", "-p", "test_*.py", "-v"],
            [sys.executable, "-m", "nipat", "--help"],
        ))
    for command in commands:
        subprocess.run(command, check=True)
    evidence = {
        "schema_version": 1, "platform": "darwin", "architecture": architecture,
        "macos_version": platform.mac_ver()[0], "python_version": platform.python_version(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "checks": {"gui_tests": True, "unit_tests": not args.desktop_only,
                   "ci_policy_tests": not args.desktop_only, "cli_help": not args.desktop_only},
        "runtime_vm_qualified": False, "desktop_acceptance": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
