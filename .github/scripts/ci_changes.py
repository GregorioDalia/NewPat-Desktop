"""Select scientific integration checks without ever skipping the required CI gate."""

import argparse
import json
from pathlib import Path
import re
import subprocess


LAYERS = ("client", "scientific", "runtime", "packaging")
ACCEPTANCE_PATH = re.compile(r"\.github/release-acceptance/v[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?\.json")
IMAGE_NOTICES = {"LICENSE", "THIRD_PARTY_NOTICES.md"}
DOCUMENTATION = {
    "README.md", "SUNTO.md", ".github/RELEASE.md", "assets/branding/README.md", "engine/README.md",
    "scientific/README.md", "scientific/vendor/DNPcall/README.md", "tests/r_optimization/README.md",
    "installer/windows/testing-readme.txt", "installer/windows/zip-readme.txt",
    *(f"scientific/vendor/NEWPAT/{module}/README.md" for module in (
        "CPI_from_cffDNA", "CPI_postnatal", "SNPcall", "contamination")),
}


def is_documentation(path):
    # Scope the shortcut to guide directories and reviewed standalone documents.
    # Markdown under scientific inputs, fixture directories or the GUI can be executable input.
    return (path in DOCUMENTATION
            or re.fullmatch(r"docs/(?:archive/)?[^/]+\.md", path) is not None
            or re.fullmatch(r"\.github/release-acceptance/v[0-9]+\.[0-9]+\.[0-9]+-evidence\.md", path) is not None)

SCIENTIFIC_PREFIXES = ("src/", "scientific/", "docker/", "engine/", "tests/")
SCIENTIFIC_FILES = {
    "compose.yaml", "pyproject.toml", ".dockerignore", "LICENSE", "THIRD_PARTY_NOTICES.md",
    "scripts/scientific_worker_evidence.py",
    ".github/workflows/ci.yml", ".github/workflows/windows-installer.yml",
    ".github/scripts/ci_changes.py", ".github/scripts/test_ci_changes.py",
    ".github/scripts/ci_control.py", ".github/scripts/test_ci_control.py",
    ".github/scripts/test_r_equivalence_ci.py",
    ".github/scripts/check_native_r.py", ".github/scripts/qualification_evidence.py",
    ".github/scripts/test_qualification_evidence.py", ".github/scripts/release_acceptance.py",
    ".github/scripts/test_release_acceptance.py",
    ".github/scripts/installer_science_wait.py", ".github/scripts/test_installer_science_wait.py",
    ".github/scripts/scientific_reuse.py", ".github/scripts/test_scientific_reuse.py",
    ".github/scripts/test_scientific_reuse_workflows.py",
}


def affects_scientific(path):
    return (path.startswith(SCIENTIFIC_PREFIXES) or path in SCIENTIFIC_FILES
            or path.startswith("scripts/verify_")
            or path.startswith("scripts/check_runtime_"))


def layers_for_path(path):
    """Add integration coverage by changed layer; never reduce the scientific gate."""
    layers = set()
    if path in IMAGE_NOTICES:
        return {"scientific"}
    if is_documentation(path) or ACCEPTANCE_PATH.fullmatch(path):
        return layers
    if (path.startswith(("src/nipat/", "tests/test_", "scripts/windows/", "scripts/acceptance/"))
            or path.startswith("config/")):
        layers.add("client")
    if affects_scientific(path):
        layers.add("scientific")
    if path.startswith(("scripts/windows/", "scripts/acceptance/", "config/")):
        layers.add("packaging")
    if path.startswith("installer/runtime/"):
        layers.update(("runtime", "packaging"))
    if (path.startswith("installer/") or path.startswith("scripts/build_")
            or path.startswith(".github/scripts/")
            or path in {"distribution-files.txt", "scripts/distribution_support.py", "pyproject.toml"}
            or path.startswith("scripts/verify_linux_")
            or path in {"scripts/verify_windows_payload.py", ".github/scripts/verify_installer_set.py"}):
        layers.add("packaging")
    if path == ".github/workflows/publish-windows-release.yml":
        # Publication revalidates existing installers and evidence; it does not
        # build or execute the scientific runtime. Required quick checks remain.
        layers.add("packaging")
    elif path.startswith(".github/workflows/") or path in {
        ".github/scripts/ci_changes.py", ".github/scripts/test_ci_changes.py",
        ".github/scripts/ci_control.py", ".github/scripts/test_ci_control.py",
    }:
        layers.update(LAYERS)
    # Future input locations have no proven owner. Run every layer until reviewed.
    return layers or set(LAYERS)


def changed_paths(base, head, *, repository=Path(".")):
    if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
        return None
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", base or "") or base == "0" * 40:
            return None
        return [path for path in subprocess.check_output(
            ["git", "diff", "--no-renames", "--name-only", "-z", base, head, "--"],
            cwd=repository, stderr=subprocess.PIPE,
        ).decode("utf-8").split("\0") if path]
    except (subprocess.CalledProcessError, UnicodeDecodeError, OSError):
        return None


def acceptance_only(paths):
    return bool(paths) and all(ACCEPTANCE_PATH.fullmatch(path) for path in paths)


def select_layers(paths, *, force=False):
    if force:
        return dict.fromkeys(LAYERS, True), "Manual verification requests every integration layer."
    # Unknown comparisons include every layer. --no-renames keeps old and new
    # names so moving/deleting code cannot bypass the integration that owned it.
    if not paths:
        return dict.fromkeys(LAYERS, True), "Comparison unavailable; all integration layers are required."
    selected = set().union(*(layers_for_path(path) for path in paths if path))
    decision = {name: name in selected for name in LAYERS}
    reason = ("Selected integration layers: " + ", ".join(sorted(selected))
              if selected else "Only documentation or release records changed.")
    return decision, reason


def layer_decision(base, head, *, force=False, repository=Path(".")):
    return select_layers(changed_paths(base, head, repository=repository), force=force)


def scientific_decision(base, head, *, force=False, repository=Path(".")):
    # Compatibility API for existing consumers and historical tests.
    decision, reason = layer_decision(base, head, force=force, repository=repository)
    return decision["scientific"], reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = changed_paths(args.base, args.head)
    decision, reason = select_layers(paths, force=args.event == "workflow_dispatch")
    metadata = acceptance_only(paths) and args.event != "workflow_dispatch"
    records = []
    docs = "none"
    if paths and args.event != "workflow_dispatch":
        records = [path for path in paths if ACCEPTANCE_PATH.fullmatch(path)]
        if all(is_documentation(path) or path in IMAGE_NOTICES for path in paths):
            docs = "image" if IMAGE_NOTICES.intersection(paths) else "guides"
    with args.output.open("a", encoding="utf-8") as handle:
        for name, selected in decision.items():
            handle.write(f"{name}={str(selected).lower()}\n")
        handle.write(f"reason={reason}\n")
        handle.write(f"acceptance_only={str(metadata).lower()}\n")
        handle.write(f"documentation_scope={docs}\n")
        handle.write(f"acceptance_paths={json.dumps(records)}\n")
    print(json.dumps({**decision, "reason": reason}))


if __name__ == "__main__":
    main()
