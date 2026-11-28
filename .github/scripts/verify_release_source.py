"""Allow deliberate candidate builds on main or the matching release branch."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

import release_acceptance as acceptance


PROFILE = {
    "schema_version": 1, "channel": "desktop", "display_name": "NewPat",
    "app_dir_name": "NewPat-Desktop", "data_dir_name": "NewPat-Desktop",
    "distro_prefix": "NewPat-Desktop-", "resume_key": "NewPat-Desktop-ResumeSetup",
    "mutex_prefix": "Local\\NewPat-Desktop-Setup-",
    "app_id": "B870A3DA-56E8-4F27-A571-86FCEDD83F25",
}


def validate_dispatch(event, ref, version, profile):
    if event != "workflow_dispatch":
        raise ValueError("Installer candidates require a deliberate manual dispatch.")
    if (not isinstance(version, str) or not re.fullmatch(r"0\.9\.[0-9]+", version)
            or tuple(map(int, version.split("."))) < (0, 9, 99)):
        raise ValueError("Clean NewPat builds require version 0.9.99 or later in the current release series.")
    if ref != "refs/heads/main" and not re.fullmatch(
            r"refs/heads/release/" + re.escape(version) + r"(?:-[a-z0-9-]+)?", ref):
        raise ValueError("Build main or a release branch matching the package version.")
    if profile != PROFILE:
        raise ValueError("The official build requires the Desktop installation identity.")


def historical_baseline(version, directory):
    target = tuple(map(int, version.split(".")))
    records = {}
    for path in directory.glob("v*.json"):
        match = re.fullmatch(r"v([0-9]+)\.([0-9]+)\.([0-9]+)", path.stem)
        if match:
            key = tuple(map(int, match.groups()))
            if key <= target:
                records[key] = path
    if not records:
        raise ValueError("No previous acceptance record. Supply the observed baseline commit.")
    record = json.loads(records[max(records)].read_bytes())
    return record["observed_baseline"]["source_commit"]


def check_reviewable_delta(version, baseline, candidate, *, repository=Path(".")):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repository)

    for commit in (baseline, candidate):
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("The observed baseline and candidate require full Git commit IDs.")
    present = subprocess.run(["git", "cat-file", "-e", f"{baseline}^{{commit}}"], cwd=repository,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if present.returncode:
        git("fetch", "--no-tags", "--depth=1", "origin", baseline)
    def inventory_blobs(commit, *, layout_version=None):
        inventory = acceptance.operative_inventory(git("show", f"{commit}:distribution-files.txt"), version=layout_version)
        blobs = {}
        for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if entry:
                info, raw_path = entry.split(b"\t", 1)
                _, kind, blob = info.split()
                path = os.fsdecode(raw_path)
                if path in inventory and kind == b"blob":
                    blobs[path] = blob
        missing = inventory - blobs.keys()
        if missing:
            raise ValueError(f"Missing distribution files in {commit}: " + ", ".join(sorted(missing)))
        return blobs

    before, after = inventory_blobs(baseline), inventory_blobs(candidate, layout_version=version)
    changes = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    timing_sha256 = None
    if acceptance.MAC_TIMING_BASELINE in changes and acceptance.MAC_TIMING_BASELINE in after:
        timing_sha256 = hashlib.sha256(git("show", f"{candidate}:{acceptance.MAC_TIMING_BASELINE}")).hexdigest()
    rejected = sorted(path for path in changes if not acceptance.reviewable_path(
        path, version=version, removed=path not in after, after_sha256=timing_sha256,
        reliability=acceptance.reliability_contract(version),
        multiplatform=acceptance.multiplatform_contract(version), revised_r=acceptance.revised_r_contract(version)))
    if rejected:
        raise ValueError("Protected distribution inputs differ from the observed baseline: " + ", ".join(rejected))
    print(f"Source preflight checked {len(changes)} distribution changes from {baseline} to {candidate}.")
    return changes


def main():
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    profile = json.loads(Path("installer/windows/install-profile.json").read_text(encoding="utf-8"))
    validate_dispatch(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"], version, profile)
    if os.environ.get("NEWPAT_CHECK_ACCEPTANCE_DELTA") == "1":
        baseline = os.environ.get("NEWPAT_OBSERVED_BASELINE") or historical_baseline(
            version, Path(".github/release-acceptance"))
        check_reviewable_delta(version, baseline, os.environ["GITHUB_SHA"])
    print(f"Candidate build authorized for this checkout: {version}; publication is a separate operation.")


if __name__ == "__main__":
    main()
