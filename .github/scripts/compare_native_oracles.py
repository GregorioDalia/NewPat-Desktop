"""Compare results from the same scientific oracle suite on native AMD64 and ARM64."""

import argparse
import json
from pathlib import Path
import subprocess

from native_evidence import NativeEvidenceError, verify_report


def compare_reports(directory, commit):
    reports = []
    for arch, machine in (("amd64", "x86_64"), ("arm64", "aarch64")):
        evidence = directory / f"scientific-oracles-{arch}"
        if (evidence / "source-commit").read_text().strip() != commit:
            raise NativeEvidenceError(f"The {arch} report belongs to a different checkout")
        architecture = (evidence / "architecture.txt").read_text().splitlines()
        if architecture != [f"runner={machine}", f"image=linux/{arch}", f"R={machine}"]:
            raise NativeEvidenceError(f"The {arch} evidence does not identify a matching native environment")
        raw = (evidence / "native-r.json").read_bytes()
        verify_report(raw, commit)
        reports.append(json.loads(raw))

    baseline, candidate = reports
    for version in ("r_version", "samtools_version"):
        if baseline[version] != candidate[version]:
            raise NativeEvidenceError(f"Native tool versions differ for {version}")
    cases = [{row["case"] for row in report["subcases"]} for report in reports]
    if cases[0] != cases[1]:
        raise NativeEvidenceError("The architectures exercised different scientific oracle subcases")
    return (f"Both native images passed {baseline['tests_run']} tests with the same "
            f"{len(cases[0])} subcases at `{commit}`. "
            f"{baseline['r_version']}, samtools {baseline['samtools_version']}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory with both architecture-specific evidence artifacts")
    args = parser.parse_args()
    print(compare_reports(args.directory, subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
