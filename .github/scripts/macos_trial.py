"""Assemble the Apple Silicon field trial from the verified installer set."""

import argparse
import hashlib
from pathlib import Path
import re
import tempfile
import zipfile

from macos_release import read_json, require

PROJECT = Path(__file__).resolve().parents[2]
VERSION = "0.9.99"
PACKAGE = f"NIPAT-{VERSION}-macos-arm64.pkg"
LAUNCHER = "Mini-Test-NewPat.command"


def build_kit(evidence, packages, commit, output):
    record = read_json(evidence)
    require(re.fullmatch(r"[0-9a-f]{40}", commit) and record.get("source_commit") == commit
            and record.get("version") == VERSION and record.get("publication_authorized") is False,
            "The trial must use the verified 0.9.99 candidate for this exact source")
    arm = record["macos_arm64"]
    package = packages / PACKAGE
    require(arm.get("file") == PACKAGE and package.is_file() and not package.is_symlink()
            and package.stat().st_size == arm.get("size")
            and re.fullmatch(r"[0-9a-f]{64}", arm["sha256"]),
            "The ARM64 installer must match the verified file and size")
    files = {
        PACKAGE: package,
        LAUNCHER: PROJECT / "installer/macos" / LAUNCHER,
        "mini_suite_macos.py": PROJECT / "scripts/mini_suite_macos.py",
        "LEGGIMI.txt": PROJECT / "docs/MINI_SUITE_MAC.md",
    }
    # GitHub's outer artifact ZIP resets executable permissions. Finder extracts
    # this Unix-created inner ZIP with the tracked launcher's executable bit.
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        staging = Path(tmp) / "trial.zip"
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_STORED) as kit:
            for name, source in files.items():
                kit.write(source, name)
            kit.writestr("source-commit", commit + "\n")
            kit.writestr("SHA256SUMS", f"{arm['sha256']}  {PACKAGE}\n")
        with zipfile.ZipFile(staging) as kit:
            with kit.open(PACKAGE) as stream:
                require(hashlib.file_digest(stream, "sha256").hexdigest() == arm["sha256"],
                        "The archived ARM64 installer differs from the verified package SHA-256")
            require(kit.getinfo(LAUNCHER).external_attr >> 16 & 0o100,
                    "The archived mini-suite launcher must be executable")
        staging.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--packages", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build_kit(args.evidence, args.packages, args.commit, args.output)
