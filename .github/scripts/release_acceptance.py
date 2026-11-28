"""Bind an explicit desktop or research acceptance policy to one verified build."""

import argparse
import csv
import io
import math
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile
from urllib.parse import urlsplit

import native_evidence
from release_layout import source_path, uses_newpat_layout

SCENARIOS = {
    "windows_clean_wsl", "windows_stable_coexistence", "windows_reinstall_removal",
    "ubuntu_clean_dependencies", "ubuntu_existing_docker", "ubuntu_reinstall_removal",
}
DIGESTS = {
    "installer_manifest_sha256", "scientific_archive_sha256",
    "windows_installer_sha256", "linux_installer_sha256",
}
FIELDS = {"schema_version", "version", "source_commit", "build_run_id", "decision", "tests"} | DIGESTS
RESEARCH_FIELDS = (FIELDS - {"tests"}) | {
    "scope", "review", "observed_baseline", "deferred_desktop_scenarios", "domain_validation",
}
REVIEWED_RESEARCH_FIELDS = RESEARCH_FIELDS | {"reviewed_source_changes"}
RELIABILITY_DIGESTS = {"qualification_evidence_sha256", "linux_upgrade_check_sha256"}
RELIABILITY_RESEARCH_FIELDS = REVIEWED_RESEARCH_FIELDS | RELIABILITY_DIGESTS
MACOS_DIGESTS = {"macos_arm64_installer_sha256", "macos_x86_64_installer_sha256"}
MULTIPLATFORM_RESEARCH_FIELDS = RELIABILITY_RESEARCH_FIELDS | MACOS_DIGESTS | {"macos_validation"}
SCIENTIFIC_RESEARCH_FIELDS = MULTIPLATFORM_RESEARCH_FIELDS | {"scientific_equivalence"}
FIVE_MODULE_RESEARCH_FIELDS = SCIENTIFIC_RESEARCH_FIELDS | {"scientific_analysis_qualification"}
FIVE_MODULE_SOURCE_SCOPE = "reviewed-operative-changes-with-versioned-scientific-models-v1"
ANALYSIS_REFERENCE_COMMIT = "9c2a8be60afcb944153710da6a61cd0559e2b4cf"
ANALYSIS_REFERENCE_ROOT = "tests/reference_r/NEWPAT_20261113"
ANALYSIS_REFERENCE_SHA256 = {
    "CPI_postnatal/Postnatal_CPI.R": "66f260ef0d66b923b763d1115b36e797c6784b37b0b4793964fa53f55dfa658e",
    "CPI_from_cffDNA/cfDNA_CPI_estimator.R": "8c8062b6110af7d957f152bb26539d72b22d7d90a26ebe251b27679c573d14f6",
    "contamination/detect_contamination.R": "e82a71b90dfc73982b350b719bcbeedbb20502b353a9d735c590dc14635d6d1d",
}
CPI_REFERENCE_COMMIT = "c753afc4be62dfc0b81b8cb683a6e850516f5ffd"
CPI_REFERENCE_ROOT = "tests/reference_r/NEWPAT_20261126"
CPI_REFERENCE_SHA256 = {
    "CPI_postnatal/Postnatal_CPI.R": "611fd93c4606298e97174c5c7b55f9a34445b95389537c994b7f41ffa43a05e6",
    "CPI_from_cffDNA/cfDNA_CPI_estimator.R": "b05e2889dbbca00777af1e0b24439f0e211c5c71edf309375c3d7e2e40c7be63",
    "contamination/detect_contamination.R": "afbbf20b937dfef356d0046e18ffff3d6746113ae771dd87745369b3e64081ca"
}
FETAL_SEX_SOURCE = "scientific/vendor/NEWPAT/Fetal_sex/Fetal_sex.R"
CPIN_SOURCE = "scientific/vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R"
ANALYSIS_HELPERS = ("__init__.py", "errors.py", "settings.py", "settings.R", "settings_data.json", "parallel.R", "plots.R")
CALLER_SUPPORTING_SOURCES = tuple("src/nipat_scientific/" + name for name in (
    "dnp_blocks.R", "dnp_pileup.py", "scratch.py", "progress.py", "progress.R", "parallel.R", "parallel.py",
    "plots.R", "settings.py", "settings.R", "settings_data.json",
))
REVISED_R_SOURCE_SCOPE = "reviewed-operative-changes-with-tested-r-equivalence-v1"
R_REFERENCE_COMMIT = "eafadf7002a9c7d7c1b9af9ccafc47d698a059e5"
R_REFERENCE_ROOT = "tests/reference_r/0.8.5"
SNP2_REFERENCE = {
    "repository": "lpistacchia/NEWPAT",
    "source_commit": "ce59f4beeeec710b1b42d425cb87d7aad729f71d",
    "path": "SNPcall/SNPcall.R",
    "frozen_path": "tests/reference_r/2.0/SNPcall.R",
    # Independently pinned upstream bytes, never supplied by the candidate report.
    "sha256": "855a96c897d1bcb8ce30b725baecfa739d01be323252da07554a63aa66965da4",
}
SNP2_CASES = dict.fromkeys(
    ("snp-varied-qualities", "snp-overlapping-windows", "snp-zero-coverage"), "snp-call")
PRESENTATION_HELPER = "tests/r_optimization/presentation/check_plots.R"
PRESENTATION_SOURCE = "src/nipat_scientific/plots.R"
SNP2_EXAMPLE_OUTPUT = "scientific/vendor/NEWPAT/SNPcall/examples/output.txt"
R_WORKFLOWS = {
    "scientific/vendor/DNPcall/DNPcall.R": "dnp-call",
    "scientific/vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R": "cpi",
    "scientific/vendor/NEWPAT/SNPcall/SNPcall.R": "snp-call",
    "scientific/vendor/NEWPAT/contamination/detect_contamination.R": "contamination",
}
R_CASES = {
    **dict.fromkeys(("dnp-single", "dnp-multi", "dnp-parallel", "dnp-varied-qualities"), "dnp-call"),
    **dict.fromkeys(("snp-edge", "snp-extra-columns"), "snp-call"),
    **dict.fromkeys(("cpi-all", "cpi-panels", "cpi-zero-error", "cpi-shared-parents"), "cpi"),
    **dict.fromkeys(("contamination-batch", "contamination-single", "contamination-panel-only"), "contamination"),
}
R_REQUIRED_PDFS = {
    "dnp-single": 5, "dnp-multi": 10, "dnp-parallel": 10, "dnp-varied-qualities": 5,
    "cpi-all": 4, "cpi-panels": 4, "cpi-zero-error": 4, "cpi-shared-parents": 6,
}
R_HELPERS = {
    "tests/r_optimization/cpi/check_core.R", "tests/r_optimization/dnp/check_blocks.R",
    "tests/r_optimization/snp/check_reads.R", "tests/r_optimization/performance/check_costs.R",
}
R_AUDIT_CASES = {
    **dict.fromkeys(("dnp-blocks-1", "dnp-blocks-2", "dnp-blocks-3", "dnp-numeric-blocks",
                    "dnp-repeated-qname-compatibility", "dnp-multi-blocks-2", "dnp-multi-blocks-3",
                    "dnp-multi-blocks-6"), "dnp-call"),
    **dict.fromkeys(("cpi-single-intervals", "cpi-single-cutoffs"), "cpi"),
}
R_AUDIT_HELPERS = {
    "tests/r_optimization/dnp/check_parallel_samples.R", "tests/r_optimization/dnp/check_parallel_blocks.R",
    "tests/r_optimization/dnp/check_reader.R", "tests/r_optimization/dnp/check_reader_ranges.R",
    "tests/r_optimization/parallel/check_budget.R", "tests/r_optimization/parallel/check_acquisition_budget.R",
    "tests/r_optimization/contamination/check_parallel.R",
}
# Frozen multi-BAM fixtures emit four plots per sample plus two shared plots
# (coverage UpSet and unassigned genotypes), as observed with the 0.8.5 oracle.
R_MULTIBAM_PDFS = {"dnp-multi-blocks-2": 10, "dnp-multi-blocks-3": 14, "dnp-multi-blocks-6": 26}
SOURCE_EQUIVALENCE_SCOPE = "distributed-operative-sources-v1"
REVIEWED_SOURCE_SCOPE = "scientific-runtime-equivalence-with-reviewed-client-changes-v1"
RELIABILITY_SOURCE_SCOPE = "reviewed-operative-changes-with-unchanged-r-v1"
MULTIPLATFORM_SOURCE_SCOPE = "reviewed-operative-changes-with-unchanged-vendored-r-v1"
BASELINE_OBSERVATIONS = {
    "installation_ready", "runtime_diagnostics", "scientific_self_tests", "dnp_sample_analysis",
}
WORKFLOW_BASELINE_OBSERVATIONS = BASELINE_OBSERVATIONS | {"automatic_workflow_sample_analysis"}
REVIEWABLE_CLIENT_PREFIXES = ("src/nipat/", "installer/windows/", "installer/linux/", "scripts/", "tests/")
REVIEWABLE_CLIENT_FILES = {"pyproject.toml", "1_SETUP.cmd", "nipat.cmd"}
NEWPAT_BRANDING_FILES = {
    "assets/branding/build_assets.py", "assets/branding/nipat-logo-dark.svg",
    "assets/branding/nipat-logo.svg", "assets/branding/nipat-symbol.svg", "newpat.cmd",
}
# Apple Silicon 0.9.10 observations and the calling-table oracle used by the
# 0.9.99 mini-suite were recorded in f106f3e. Only these exact bytes qualify.
MAC_TIMING_BASELINE = "docs/validation/0.9.10-apple-silicon-timing.json"
MAC_TIMING_SHA256 = "f025a1a735fc0accc4cf02707678c41360d4e553dc205601b9c573c5167d0d29"
SYNTHETIC_TRIO_FILES = {"examples/newpat-synthetic-trio.zip", "examples/newpat-synthetic-trio.zip.sha256"}
INTRECCIO_BRANDING_FILES = {
    "assets/branding/newpat-app-icon.svg", "assets/branding/newpat-app-icon-small.svg",
    "assets/branding/nipat-icon.ico", "assets/branding/nipat-icon.png",
    "assets/branding/newpat-icon-small.png",
}
REVIEWABLE_OPERATIVE_PREFIXES = (
    "src/", "engine/", "installer/", "scripts/", "tests/", "docker/", "config/",
)
REMOVABLE_SIGNING_HELPERS = {
    "installer/windows/verify-signatures.ps1", "installer/windows/test-signatures.ps1",
}
# These inputs must remain part of the distributed inventory being compared.
REQUIRED_OPERATIVE_PATHS = {
    "pyproject.toml", "compose.yaml", "engine/main.py", "src/nipat/cli.py", "scientific/SHA256SUMS",
    "docker/scientific-runtime/Dockerfile", "docker/scientific-runtime/r-packages.tsv",
    "installer/runtime/Dockerfile", "installer/runtime/nipat-engine", "installer/windows/NIPAT.iss",
    "scripts/build_windows_installer_assets.py", "scripts/build_linux_installer.py",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def gui_contract(version):
    """The reviewed 0.9 desktop line retains the complete 0.8.99 release gates."""
    return bool(isinstance(version, str)
                and re.fullmatch(r"0\.9\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version))


def gui_prerelease_contract(version):
    """The authorized GUI previews cannot replace the stable channel."""
    return bool(isinstance(version, str)
                and re.fullmatch(r"0\.9\.(?:0|1|5)(?:(?:a|b|rc)[0-9]+)?", version))


def fixed_admission_contract(version):
    """NewPat 0.9.5 qualifies unobserved outer work separately from loaded pools."""
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 9, 5))


def measured_sample_contract(version):
    """The 0.9.9 caller and sample qualification requires observed execution."""
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 9, 9))


def reliability_contract(version):
    match = re.fullmatch(r"0\.7\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and int(match[1]) >= 2) or multiplatform_contract(version)


def multiplatform_contract(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and int(match[1]) >= 2) or gui_contract(version)


def revised_r_contract(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and int(match[1]) >= 9) or gui_contract(version)


def audited_r_contract(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 8, 20))


def snp2_contract(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 8, 30))


def revised_cpi_contract(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(?:a|b|rc)\d+)?", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 9, 10))


def downstream_reference(version):
    if revised_cpi_contract(version):
        return CPI_REFERENCE_COMMIT, CPI_REFERENCE_ROOT, CPI_REFERENCE_SHA256
    return ANALYSIS_REFERENCE_COMMIT, ANALYSIS_REFERENCE_ROOT, ANALYSIS_REFERENCE_SHA256


def five_module_contract(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and int(match[1]) >= 50) or gui_contract(version)


def explicit_publication_contract(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and int(match[1]) >= 70) or gui_contract(version)


def publication_fields(version):
    return {"publication_channel"} if explicit_publication_contract(version) else set()


def zip_fields(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return {"windows_zip_sha256"} if (match and int(match[1]) >= 95) or gui_contract(version) else set()


def payload_fields(version):
    match = re.fullmatch(r"0\.8\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return {"windows_payload_sha256"} if (match and int(match[1]) >= 99) or gui_contract(version) else set()


def testing_entrypoint_fields(version):
    return {"windows_testing_sha256"} if gui_prerelease_contract(version) else set()


def verify_presentation_variants(case):
    """Bind corrected plots to serial results and retained parallel renderings."""
    variants = case.get("execution_variants")
    require(isinstance(variants, dict) and "candidate" in variants,
            "Scientific presentation execution variants are missing")
    require(case.get("plots_comparison") == "renderable-and-bounded",
            "Scientific presentation must identify structural serial validation")
    if case["plots"]:
        require(len(variants) >= 2,
                "Scientific PDF evidence lacks a serial-versus-parallel comparison")
    for name, variant in variants.items():
        require(isinstance(name, str) and bool(name) and isinstance(variant, dict)
                and variant.get("status") == "passed"
                and variant.get("unrounded_r_values") == "identical"
                and variant.get("table_sha256") == case["table_sha256"]
                and variant.get("plots") == case["plots"],
                "Scientific presentation variant differs from serial scientific results")
        expected = "renderable-and-bounded" if name == "candidate" else "candidate-serial-exact-pixels"
        require(variant.get("plots_comparison") == expected,
                "Scientific presentation variant has an unsupported PDF comparison claim")
        configuration = variant.get("execution_configuration")
        require(isinstance(configuration, dict)
                and configuration.get("requested_mode") == ("serial" if name == "candidate" else "auto")
                and (configuration.get("requested_max_workers") is None
                     or type(configuration["requested_max_workers"]) is int
                     and configuration["requested_max_workers"] >= 1),
                "Scientific presentation variant has no matching execution configuration")
        if name == "candidate":
            require(configuration.get("requested_max_workers") is None,
                    "Serial scientific presentation has conflicting execution settings")


def verify_multibam_variants(case):
    variants = case.get("execution_variants")
    expected = {"candidate": ("serial", None), "auto": ("auto", None),
                "manual-2": ("auto", 2), "manual-4": ("auto", 4), "manual-4-repeat": ("auto", 4)}
    require(isinstance(variants, dict) and set(variants) == set(expected),
            "Multi-BAM serial/auto/manual/repeat comparisons are missing")
    for name, (mode, cap) in expected.items():
        comparison = variants[name]
        require(isinstance(comparison, dict) and comparison.get("status") == "passed"
                and comparison.get("unrounded_r_values") == "identical"
                and comparison.get("table_sha256") == case["table_sha256"]
                and comparison.get("plots") == case["plots"],
                "Multi-BAM variant does not preserve exact scientific results")
        parallel = comparison.get("parallel_execution")
        require(isinstance(parallel, dict) and parallel.get("requested_mode") == mode
                and parallel.get("requested_max_workers") == cap,
                "Multi-BAM variant has different execution settings")
        planned = parallel.get("maximum_planned_workers")
        observed = parallel.get("maximum_observed_child_workers")
        require(type(planned) is int and planned >= 1 and type(observed) is int and 0 <= observed <= planned
                and (cap is None or planned <= cap), "Multi-BAM observed concurrency exceeds its budget")
        if name == "candidate":
            require(planned == 1 and observed == 0 and parallel.get("simultaneous_child_workers") is False,
                    "Serial Multi-BAM evidence contains child concurrency")
        else:
            require(observed >= 2 and parallel.get("simultaneous_child_workers") is True
                    and parallel.get("overlapping_workers_required") is True,
                    "Parallel Multi-BAM evidence has no observed concurrent workers")
        if name == "manual-4-repeat":
            require(comparison.get("deterministic_repeat_of") == "manual-4",
                    "Multi-BAM deterministic repeat is missing")


def reviewable_path(path, *, reliability=False, multiplatform=False, revised_r=False, version=None,
                    removed=False, after_sha256=None):
    # These records stay in Git. The clean installer no longer bundles the
    # four historical measurements present in the observed source inventory.
    archived_reports = {
        "docs/validation/0.8.12-rootless.json", "docs/validation/0.8.13-rootless.json",
        "docs/validation/0.8.14-microbenchmarks.json", "docs/validation/0.8.14-rootless.json",
    }
    if path in archived_reports:
        return bool(removed and revised_r and version and uses_newpat_layout(version))
    if path == MAC_TIMING_BASELINE:
        return bool(revised_r and version and uses_newpat_layout(version) and not removed
                    and after_sha256 == MAC_TIMING_SHA256)
    if path in {"2_AVVIA.cmd", "2_LAUNCH.cmd"}:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(?:a|b|rc)\d+)?", version or "")
        english_launcher = match and tuple(map(int, match.groups())) >= (0, 9, 10)
        if path == "2_AVVIA.cmd":
            return not english_launcher or removed
        return bool(english_launcher)
    # Permit the listed artwork, examples and scheduling report from their introduction; exact before/after
    # hashes still belong to the reviewed source delta.
    if revised_r and version and path in {
            source_path(name, version) for name in NEWPAT_BRANDING_FILES | INTRECCIO_BRANDING_FILES
            if source_path(name, version) != name}:
        return True
    if revised_r and path in (NEWPAT_BRANDING_FILES | INTRECCIO_BRANDING_FILES | SYNTHETIC_TRIO_FILES
                              | {"docs/validation/0.9.10-desktop-scheduling.json"}):
        match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
        minimum = (0, 9, 5) if path in NEWPAT_BRANDING_FILES else (0, 9, 10)
        if match and tuple(map(int, match.groups())) >= minimum:
            return True
    # This known development report is distributed as readable provenance. It
    # does not qualify the image; schema 7 still requires fresh installed-image
    # evidence. Other reports require their own version-scoped exception.
    if revised_r and five_module_contract(version) and path == "docs/validation/0.8.50-development.json":
        return True
    if revised_r and revised_cpi_contract(version) and path == FETAL_SEX_SOURCE:
        return True
    if revised_r and five_module_contract(version) and path == CPIN_SOURCE:
        return True
    if revised_r and path in set(R_WORKFLOWS) | {"scientific/SHA256SUMS"}:
        return True
    if revised_r and snp2_contract(version) and path == SNP2_EXAMPLE_OUTPUT:
        # SNPcall 2.0 changes the bundled expected result from 9 to 17 columns.
        # Its exact before/after bytes remain subject to the source delta review;
        # input fixtures and all other scientific assets stay protected.
        return True
    if reliability:
        # The Python preparation, orchestration and packaging may evolve, but
        # this research policy never authorizes a change to the R algorithms.
        # Schema 5 also reviews Git's checkout normalization rules: they affect
        # the exact bytes packaged on each host and must not be silently exempt.
        metadata = {".gitattributes"} if multiplatform else set()
        return ((PurePosixPath(path).suffix.casefold() != ".r"
                 or multiplatform and not path.startswith("scientific/vendor/"))
                and (path in REVIEWABLE_CLIENT_FILES | {"compose.yaml", ".gitignore"} | metadata
                     or path.startswith(REVIEWABLE_OPERATIVE_PREFIXES)))
    return path in REVIEWABLE_CLIENT_FILES or path.startswith(REVIEWABLE_CLIENT_PREFIXES)


def acceptance_path(version):
    require(isinstance(version, str) and (re.fullmatch(r"0\.[567]\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version)
                                         or multiplatform_contract(version)),
            "Joint publication supports the 0.5–0.7, 0.8.2+ and 0.9 GUI desktop contracts")
    return f".github/release-acceptance/v{version}.json"


def identity(installer_set):
    result = {
        "version": installer_set["version"],
        "source_commit": installer_set["source_commit"],
        "installer_manifest_sha256": installer_set["installer_manifest_sha256"],
        "scientific_archive_sha256": installer_set["scientific_archive"]["sha256"],
        "windows_installer_sha256": installer_set["windows"]["sha256"],
        "linux_installer_sha256": installer_set["linux"]["sha256"],
    }
    if multiplatform_contract(installer_set["version"]):
        for architecture in ("arm64", "x86_64"):
            require(isinstance(installer_set.get(f"macos_{architecture}"), dict),
                    "Acceptance requires both native macOS packages")
            result[f"macos_{architecture}_installer_sha256"] = installer_set[f"macos_{architecture}"]["sha256"]
    if zip_fields(installer_set["version"]):
        require(isinstance(installer_set.get("windows_zip"), dict), "Acceptance requires the complete Windows ZIP")
        result["windows_zip_sha256"] = installer_set["windows_zip"]["sha256"]
    if payload_fields(installer_set["version"]):
        require(isinstance(installer_set.get("windows_payload"), dict),
                "Acceptance requires the separate Windows desktop payload")
        result["windows_payload_sha256"] = installer_set["windows_payload"]["sha256"]
    if testing_entrypoint_fields(installer_set["version"]):
        require(isinstance(installer_set.get("windows_testing"), dict),
                "Acceptance requires the release-specific Windows testing entrypoint")
        result["windows_testing_sha256"] = installer_set["windows_testing"]["sha256"]
    return result


def linux_evidence_key(version):
    return "linux_clean_install_check" if uses_newpat_layout(version) else "linux_upgrade_check"


def template(installer_set, run_id):
    require(type(run_id) is int and run_id > 0, "Invalid build run ID")
    fields = identity(installer_set)
    acceptance_path(fields["version"])
    require(isinstance(fields["source_commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", fields["source_commit"]), "Invalid source commit")
    for field in DIGESTS | (MACOS_DIGESTS if multiplatform_contract(fields["version"]) else set()) | zip_fields(fields["version"]) | payload_fields(fields["version"]) | testing_entrypoint_fields(fields["version"]):
        require(isinstance(fields[field], str) and re.fullmatch(r"[0-9a-f]{64}", fields[field]),
                f"Invalid digest: {field}")
    if multiplatform_contract(fields["version"]):
        record = {
            "schema_version": 5, **fields, "build_run_id": run_id, "decision": "pending",
            "scope": "pre-1.0-research", "review": {"reviewer": "", "reviewed_at": "", "evidence": []},
            "observed_baseline": {"source_commit": "", "observations": [], "evidence": [],
                                  "role": "historical-platform-evidence",
                                  "source_comparison_scope": MULTIPLATFORM_SOURCE_SCOPE},
            "reviewed_source_changes": [], "deferred_desktop_scenarios": sorted(SCENARIOS),
            "domain_validation": "pending-domain-researchers", "qualification_evidence_sha256": "",
            linux_evidence_key(fields["version"]) + "_sha256": installer_set.get(linux_evidence_key(fields["version"]), {}).get("sha256", ""),
            "macos_validation": {architecture: {"status": "not-performed", "evidence": []}
                                 for architecture in ("arm64", "x86_64")},
        }
        if revised_r_contract(fields["version"]):
            record["schema_version"] = 6
            record["observed_baseline"]["source_comparison_scope"] = REVISED_R_SOURCE_SCOPE
            record["scientific_equivalence"] = {
                "reference_source_commit": R_REFERENCE_COMMIT,
                "report_path": "", "report_sha256": "", "runtime_image": "",
            }
        if five_module_contract(fields["version"]):
            record["schema_version"] = 7
            record["observed_baseline"]["source_comparison_scope"] = FIVE_MODULE_SOURCE_SCOPE
            record["scientific_analysis_qualification"] = {
                "reference_source_commit": downstream_reference(fields["version"])[0],
                "report_path": "", "report_sha256": "", "runtime_image": "",
            }
        if explicit_publication_contract(fields["version"]):
            record["publication_channel"] = None
        return record
    return {
        "schema_version": 1, **fields, "build_run_id": run_id, "decision": "pending",
        "tests": {name: {"result": "pending", "tester": "", "tested_at": "", "evidence": []}
                  for name in sorted(SCENARIOS)},
    }


def validate(record, version, commit, run_id, installer_set=None):
    """Require a committed review under the record's explicit acceptance policy."""
    acceptance_path(version)
    require(not revised_r_contract(version) or isinstance(record, dict)
            and type(record.get("schema_version")) is int
            and record["schema_version"] == (7 if five_module_contract(version) else 6),
            "Releases from 0.8.9 require scientific equivalence acceptance schema 6; from 0.8.50 require five-module schema 7")
    if isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] in (2, 3, 4, 5, 6, 7):
        validate_research(record, version, commit, run_id, installer_set)
        return
    require(not multiplatform_contract(version), "Official 0.8.2+ releases require four-platform acceptance schema 5")
    require(isinstance(record, dict) and set(record) == FIELDS, "Acceptance record fields are invalid")
    require(type(record["schema_version"]) is int and record["schema_version"] == 1,
            "Unsupported acceptance schema")
    require(record["version"] == version and record["source_commit"] == commit
            and type(record["build_run_id"]) is int and record["build_run_id"] == run_id,
            "Acceptance belongs to a different version, source or build run")
    require(record["decision"] == "accepted", "Desktop acceptance is pending or rejected")
    for field in DIGESTS:
        require(isinstance(record[field], str) and re.fullmatch(r"[0-9a-f]{64}", record[field]),
                f"Invalid acceptance digest: {field}")
    tests = record["tests"]
    require(isinstance(tests, dict) and set(tests) == SCENARIOS,
            "A required desktop acceptance scenario is missing")
    for name, test in tests.items():
        require(isinstance(test, dict) and set(test) == {"result", "tester", "tested_at", "evidence"},
                f"Invalid acceptance scenario: {name}")
        require(test["result"] == "passed", f"Desktop acceptance has not passed: {name}")
        require(isinstance(test["tester"], str) and test["tester"].strip(),
                f"Missing tester: {name}")
        timestamp = test["tested_at"]
        require(isinstance(timestamp, str)
                and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", timestamp),
                f"Acceptance timestamp must be a UTC date and time: {name}")
        try:
            tested_at = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError as error:
            raise ValueError(f"Invalid acceptance date: {name}") from error
        require(tested_at <= datetime.now(timezone.utc), f"Acceptance date is in the future: {name}")
        evidence = test["evidence"]
        require(isinstance(evidence, list) and evidence and all(isinstance(link, str) for link in evidence),
                f"Missing acceptance evidence: {name}")
        for link in evidence:
            parsed = urlsplit(link)
            require(parsed.scheme == "https" and parsed.hostname and parsed.path not in ("", "/")
                    and not parsed.username and not parsed.password and not any(c.isspace() for c in link),
                    f"Acceptance evidence must identify an HTTPS resource: {name}")
    if installer_set is not None:
        require(all(record[field] == value for field, value in identity(installer_set).items()),
                "Acceptance hashes do not identify these verified installers")


def review_timestamp(value, label):
    require(isinstance(value, str)
            and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value),
            f"{label} must be a UTC date and time")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"Invalid {label}") from error
    require(parsed <= datetime.now(timezone.utc), f"{label} is in the future")


def review_evidence(value, label):
    require(isinstance(value, list) and value and all(isinstance(link, str) for link in value),
            f"Missing {label}")
    for link in value:
        parsed = urlsplit(link)
        require(parsed.scheme == "https" and parsed.hostname and parsed.path not in ("", "/")
                and not parsed.username and not parsed.password and not any(c.isspace() for c in link),
                f"{label} must identify an HTTPS resource")


def validate_research(record, version, commit, run_id, installer_set=None):
    """A limited research decision records deferred qualification, never fictitious passes."""
    five_modules = isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] == 7
    revised_r = isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] in (6, 7)
    multiplatform = isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] in (5, 6, 7)
    reliability = isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] in (4, 5, 6, 7)
    reviewed_delta = isinstance(record, dict) and type(record.get("schema_version")) is int and record["schema_version"] in (3, 4, 5, 6, 7)
    schema = 7 if five_modules else 6 if revised_r else 5 if multiplatform else (4 if reliability else (3 if reviewed_delta else 2))
    require(not five_modules or five_module_contract(version), "Five-module acceptance is available from 0.8.50 only")
    require(not revised_r or revised_r_contract(version), "Revised R acceptance is available from 0.8.9 only")
    minor = "7" if reviewed_delta else "6"
    require(multiplatform_contract(version) if multiplatform else
            isinstance(version, str) and re.fullmatch(rf"0\.{minor}\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version),
            f"Research acceptance schema {schema} does not support this release version")
    if reliability:
        require(reliability_contract(version), "Reliability acceptance is available from 0.7.2 only")
    elif reviewed_delta:
        require(not reliability_contract(version),
                "Research releases from 0.7.2 require reliability acceptance schema 4")
    expected_fields = (FIVE_MODULE_RESEARCH_FIELDS if five_modules else SCIENTIFIC_RESEARCH_FIELDS if revised_r else MULTIPLATFORM_RESEARCH_FIELDS if multiplatform else RELIABILITY_RESEARCH_FIELDS if reliability else
                       REVIEWED_RESEARCH_FIELDS if reviewed_delta else RESEARCH_FIELDS)
    reliability_digests = RELIABILITY_DIGESTS
    if reliability and uses_newpat_layout(version):
        clean_digest = linux_evidence_key(version) + "_sha256"
        expected_fields = (expected_fields - {"linux_upgrade_check_sha256"}) | {clean_digest}
        reliability_digests = (reliability_digests - {"linux_upgrade_check_sha256"}) | {clean_digest}
    require(isinstance(record, dict) and set(record) == expected_fields | publication_fields(version) | zip_fields(version) | payload_fields(version) | testing_entrypoint_fields(version)
            and type(record["schema_version"]) is int and record["schema_version"] == schema,
            "Research acceptance record fields are invalid")
    require(record["version"] == version and record["source_commit"] == commit
            and isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)
            and type(record["build_run_id"]) is int and type(run_id) is int
            and run_id > 0 and record["build_run_id"] == run_id,
            "Acceptance belongs to a different version, source or build run")
    for field in DIGESTS | (reliability_digests if reliability else set()) | (MACOS_DIGESTS if multiplatform else set()) | zip_fields(version) | payload_fields(version) | testing_entrypoint_fields(version):
        require(isinstance(record[field], str) and re.fullmatch(r"[0-9a-f]{64}", record[field]),
                f"Invalid acceptance digest: {field}")
    require(record["decision"] == "accepted-for-research" and record["scope"] == "pre-1.0-research",
            "Research acceptance is pending, rejected or outside its stated scope")
    if explicit_publication_contract(version):
        channel = record["publication_channel"]
        require(not gui_prerelease_contract(version) or channel == "testing",
                "NewPat GUI previews must use the testing publication channel")
        require(channel == "testing" or (channel == "stable" and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)),
                "Acceptance must authorize an explicit compatible publication channel")
    review = record["review"]
    require(isinstance(review, dict) and set(review) == {"reviewer", "reviewed_at", "evidence"},
            "Invalid research review fields")
    require(isinstance(review["reviewer"], str) and review["reviewer"].strip(), "Missing research reviewer")
    review_timestamp(review["reviewed_at"], "Research review date")
    review_evidence(review["evidence"], "Research review evidence")
    baseline = record["observed_baseline"]
    scope_field = "source_comparison_scope" if reliability else "source_equivalence_scope"
    baseline_fields = {"source_commit", "observations", "evidence", scope_field}
    if reliability:
        baseline_fields.add("role")
    require(isinstance(baseline, dict) and set(baseline) == baseline_fields,
            "Invalid observed baseline fields")
    if reliability:
        require(baseline["role"] == "historical-platform-evidence",
                "The baseline cannot attest installation of the changed candidate")
    require(isinstance(baseline["source_commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", baseline["source_commit"]), "Invalid observed baseline commit")
    observations = baseline["observations"]
    allowed_observations = WORKFLOW_BASELINE_OBSERVATIONS if reviewed_delta else BASELINE_OBSERVATIONS
    require(isinstance(observations, list) and all(isinstance(item, str) for item in observations)
            and len(observations) == len(set(observations)) and set(observations) <= allowed_observations
            and "installation_ready" in observations
            and bool(set(observations) & ({"scientific_self_tests", "dnp_sample_analysis"}
                                         | ({"automatic_workflow_sample_analysis"} if reviewed_delta else set()))),
            "Baseline must identify observed installation and scientific execution")
    expected_scope = (FIVE_MODULE_SOURCE_SCOPE if five_modules else REVISED_R_SOURCE_SCOPE if revised_r else MULTIPLATFORM_SOURCE_SCOPE if multiplatform else RELIABILITY_SOURCE_SCOPE if reliability else
                      REVIEWED_SOURCE_SCOPE if reviewed_delta else SOURCE_EQUIVALENCE_SCOPE)
    require(baseline[scope_field] == expected_scope,
            "Unsupported baseline source equivalence scope")
    review_evidence(baseline["evidence"], "Observed baseline evidence")
    deferred = record["deferred_desktop_scenarios"]
    require(isinstance(deferred, list) and all(isinstance(item, str) for item in deferred)
            and len(deferred) == len(SCENARIOS) and set(deferred) == SCENARIOS,
            "Research acceptance must explicitly defer all six desktop scenarios")
    require(record["domain_validation"] == ("pending-domain-researchers" if reviewed_delta else "planned-for-0.7"),
            "Research acceptance cannot claim completed domain validation")
    if multiplatform:
        platforms = record["macos_validation"]
        require(isinstance(platforms, dict) and set(platforms) == {"arm64", "x86_64"},
                "Both macOS runtime validation statuses must be explicit")
        for architecture, observation in platforms.items():
            require(isinstance(observation, dict) and set(observation) == {"status", "evidence"},
                    f"Invalid macOS {architecture} runtime validation record")
            if observation["status"] == "passed":
                review_evidence(observation["evidence"], f"macOS {architecture} runtime evidence")
            else:
                require(observation["status"] == "not-performed" and observation["evidence"] == [],
                        "Unperformed macOS validation cannot imply a successful runtime test")
    if revised_r:
        validate_scientific_record(record["scientific_equivalence"])
    if five_modules:
        validate_analysis_record(record["scientific_analysis_qualification"], version)
        require(record["scientific_equivalence"]["runtime_image"] ==
                record["scientific_analysis_qualification"]["runtime_image"],
                "All five modules must be qualified in the same packaged image")
    if reviewed_delta:
        changes = record["reviewed_source_changes"]
        require(isinstance(changes, list), "Reviewed source changes must be an explicit list")
        paths = []
        for item in changes:
            require(isinstance(item, dict) and set(item) == {"path", "before_sha256", "after_sha256"},
                    "Invalid reviewed source change fields")
            path = item["path"]
            require(isinstance(path, str) and path and PurePosixPath(path).as_posix() == path
                    and not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts
                    and "\\" not in path and not any(character.isspace() for character in path)
                    and PurePosixPath(path).suffix.casefold() != ".md"
                    and reviewable_path(path, reliability=reliability, multiplatform=multiplatform,
                                        revised_r=revised_r, version=version, removed=item["after_sha256"] is None,
                                        after_sha256=item["after_sha256"]),
                    ("Only known scientific scripts and explicit operative sources can be reviewed" if revised_r
                     else "Only operative source changes outside protected vendored R can be reviewed" if multiplatform
                     else "Only explicit non-R operative source changes can be reviewed" if reliability
                     else "Only explicit client, installer and test source changes can be reviewed"))
            for field in ("before_sha256", "after_sha256"):
                digest = item[field]
                require(digest is None or isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                        "Invalid reviewed source digest")
            require(item["before_sha256"] != item["after_sha256"], "Reviewed source change must identify different bytes")
            paths.append(path)
        require(paths == sorted(set(paths)), "Reviewed source changes must be sorted and unique")
    if installer_set is not None:
        require(all(record[field] == value for field, value in identity(installer_set).items()),
                "Acceptance hashes do not identify these verified installers")
        if reliability:
            key = linux_evidence_key(version)
            require(installer_set.get(key, {}).get("sha256") == record[key + "_sha256"],
                    "Acceptance does not identify the verified Linux installation report")



def valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def safe_evidence_path(value):
    return (isinstance(value, str) and bool(value) and PurePosixPath(value).as_posix() == value
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
            and "\\" not in value and ":" not in value and not any(c.isspace() for c in value))


def validate_scientific_record(evidence):
    require(isinstance(evidence, dict) and set(evidence) == {
        "reference_source_commit", "report_path", "report_sha256", "runtime_image",
    }, "Invalid scientific equivalence record fields")
    require(evidence["reference_source_commit"] == R_REFERENCE_COMMIT,
            "Scientific equivalence requires the frozen 0.8.5 reference")
    require(safe_evidence_path(evidence["report_path"])
            and evidence["report_path"].startswith("scientific/")
            and PurePosixPath(evidence["report_path"]).name == "r-equivalence.json",
            "Scientific equivalence must identify its retained qualification report")
    require(valid_digest(evidence["report_sha256"]), "Invalid scientific equivalence report digest")
    require(isinstance(evidence["runtime_image"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", evidence["runtime_image"]),
            "Scientific equivalence requires an immutable runtime image ID")


def validate_analysis_record(evidence, version):
    require(isinstance(evidence, dict) and set(evidence) == {
        "reference_source_commit", "report_path", "report_sha256", "runtime_image",
    }, "Invalid downstream scientific qualification record fields")
    require(evidence["reference_source_commit"] == downstream_reference(version)[0],
            "Downstream analyses require the frozen NEWPAT reference for this release")
    require(safe_evidence_path(evidence["report_path"])
            and evidence["report_path"].startswith("scientific/")
            and PurePosixPath(evidence["report_path"]).name == "five-module-qualification.json",
            "Updated analyses must identify their retained qualification report")
    require(valid_digest(evidence["report_sha256"]), "Invalid downstream qualification report digest")
    require(isinstance(evidence["runtime_image"], str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", evidence["runtime_image"]),
            "Updated analyses require an immutable runtime image ID")


def analysis_expected_cases():
    expected = {}
    for marker in ("SNP", "DNP"):
        for workflow, variants in (("cpin", ({},)),
                ("cpi", ({}, {"minimum": 1}, {"minimum": 5}, {"metadata": True}, {"mismatch": True})),
                ("contamination", ({}, {"include_zero": False}))):
            for index, values in enumerate(variants):
                variant = {"minimum": 2, "include_zero": True, "metadata": False, "mismatch": False, **values}
                for candidate in (False, True):
                    name = f"{marker}-{workflow}-{index}-{'candidate' if candidate else 'reference'}"
                    expected[name] = (workflow, marker, candidate, 1, "serial", None, variant)
        for workflow in ("cpin", "cpi", "contamination"):
            for count in (2, 3, 5):
                for mode, cap in (("serial", None), ("auto", None), ("auto", 2)):
                    name = f"{marker}-{workflow}-batch{count}-{mode}-cap{cap}"
                    expected[name] = (workflow, marker, True, count, mode, cap,
                                     {"minimum": 2, "include_zero": True, "metadata": False, "mismatch": False})
    return expected


def same_scientific_values(actual, expected):
    """JSON numbers can differ in representation, but true is never the number 1."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and set(actual) == set(expected)
                and all(same_scientific_values(actual[key], value) for key, value in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(same_scientific_values(a, b) for a, b in zip(actual, expected)))
    return actual == expected


def compare_analysis_rows(actual, expected):
    require(isinstance(actual, list) and isinstance(expected, list) and len(actual) == len(expected),
            "Downstream scientific summary row counts differ")
    for row, reference in zip(actual, expected):
        require(isinstance(row, dict) and isinstance(reference, dict) and set(reference) <= set(row),
                "Downstream scientific summary fields are incomplete")
        for key, wanted in reference.items():
            value = row[key]
            require(isinstance(value, str) and isinstance(wanted, str), "Scientific table values must be strings")
            if wanted in {"NA", "NaN"}:
                require(value in {"NA", "NaN", "nan"}, "Downstream missing scientific value differs")
                continue
            try:
                numeric = float(wanted)
            except ValueError:
                require(value == wanted, "Downstream scientific sample/selection identity differs")
            else:
                try:
                    observed = float(value)
                except ValueError as error:
                    raise ValueError("Downstream scientific numeric value is missing") from error
                require(math.isfinite(observed) and math.isfinite(numeric)
                        and math.isclose(observed, numeric, rel_tol=1e-11, abs_tol=1e-11),
                        "Downstream scientific numerical results differ")


def verify_analysis_summary(archive, report_path, case, revised_cpi):
    workflow, marker, size = case["workflow"], case["marker"], case["batch_size"]
    filename = {"cpin": "Summary_Postnatal_CPI.txt", "cpi": "Summary_FetalFraction_CPI.csv",
                "contamination": "contamination_summary.txt"}[workflow]
    require(case["output_sha256"].get(filename) == case["summary_sha256"],
            "Downstream summary digest does not identify the scientific output")
    member = (PurePosixPath(report_path).parent / case["name"] / "output" / filename).as_posix()
    try:
        with zipfile.ZipFile(archive) as handle:
            entries = [entry for entry in handle.infolist() if entry.filename == member]
            require(len(entries) == 1 and 0 < entries[0].file_size <= 8 * 1024 * 1024,
                    "Missing, duplicate or oversized retained downstream summary")
            raw = handle.read(entries[0])
        require(hashlib.sha256(raw).hexdigest() == case["summary_sha256"],
                "Retained downstream summary bytes differ from the qualified result")
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="," if workflow == "cpi" else "\t"))
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeError, csv.Error) as error:
        raise ValueError("Cannot read retained downstream scientific summary") from error
    require(rows == case["rows"], "Reported downstream rows differ from retained summary bytes")
    required_columns = {
        "cpin": {"Trio", "Marker_type", "Analysis", "N_sites", "N_heterozygous_child_sites",
                 "N_homozygous_child", "Matching_sites", "Mismatching_sites", "Log10_CPI", "CPI",
                 "Error_constant", "Min_child_reads"},
        "cpi": {"Pair", "N_sites_mother", "N_sites_father", "Median_fetal_fraction_raw",
                "Median_fetal_fraction_percent", "Max_logCPI", "Min_logCPI", "Median_logCPI",
                "Mean_logCPI", "CPI_medianFF", "Error_constant"},
        "contamination": {"individuo", "informative_sites", "mean_contamination", "sd_contamination"},
    }[workflow]
    if revised_cpi and workflow == "cpin":
        required_columns = {
            "Trio", "Marker_type", "N_sites", "N_hom_hom", "N_hom_het", "N_het_hom", "N_het_het",
            "Matching_sites", "Mismatching_sites", "No_obligatory_allele_sites", "Maternal_incompatible_sites",
            "Log10_CPI", "CPI", "Mismatch_probability", "Min_coverage",
            "Include_hom_hom", "Include_hom_het", "Include_het_hom", "Include_het_het",
        }
    if revised_cpi and workflow == "cpi":
        required_columns |= {"Min_fetal_reads", "Min_fetal_percent", "Include_homozygous_child", "Min_coverage",
                             "Max_other_fraction", "N_sites_HET_child", "N_sites_HOM_child", "Matching_HET_child",
                             "Mismatching_HET_child", "Matching_HOM_child", "Mismatching_HOM_child",
                             "Log10_CPI_HET_child", "Log10_CPI_HOM_child"}
    require(all(required_columns <= set(row) for row in rows), "Downstream scientific summary columns are incomplete")
    if workflow == "cpin":
        selections = {"heterozygous_child_sites", "all_compatible_sites"}
        trios = ([f"MotherM-FatherF-ChildC_{marker}s"] if size == 1 else
                 [f"MotherM{i}-FatherF{i}-ChildC{i}_{marker}s" for i in range(1, size + 1)])
        if revised_cpi:
            require(len(rows) == size and {row.get("Trio") for row in rows} == set(trios)
                    and all(row.get("Marker_type") == marker for row in rows),
                    "Postnatal summary must contain one row per expected trio")
        else:
            identities = {(row.get("Trio"), row.get("Analysis")) for row in rows}
            require(len(rows) == 2 * size and identities == {(trio, selection) for trio in trios for selection in selections}
                    and all(row.get("Marker_type") == marker for row in rows),
                    "CPIN summary must contain each expected trio and selection exactly once")
    elif workflow == "cpi":
        pairs = ([f"MotherM-FatherF_{marker}s", f"MotherN-FatherN_{marker}s"] if size == 1 else
                 [f"MotherM{i}-FatherF{i}_{marker}s" for i in range(1, size + 1)])
        require(len(rows) == len(pairs) and {row.get("Pair") for row in rows} == set(pairs),
                "CPI summary must contain every expected pair exactly once")
    else:
        require(len(rows) == size and {row.get("individuo") for row in rows} == {f"Sample{i}" for i in range(1, size + 1)},
                "Contamination summary must contain every expected sample exactly once")


def verify_analysis_qualification(record, evidence_directory, read_source):
    """Validate updated models separately; never relabel changed science as old equivalence."""
    evidence = record["scientific_analysis_qualification"]
    version = record["version"]
    validate_analysis_record(evidence, version)
    reference_commit, reference_root, source_hashes = downstream_reference(version)
    revised_cpi = revised_cpi_contract(version)
    archive = Path(evidence_directory) / "qualification-evidence.zip"
    require(archive.is_file() and not archive.is_symlink()
            and hashlib.sha256(archive.read_bytes()).hexdigest() == record["qualification_evidence_sha256"],
            "Downstream qualification archive differs from the accepted build")
    try:
        with zipfile.ZipFile(archive) as handle:
            entries = [entry for entry in handle.infolist() if entry.filename == evidence["report_path"]]
            require(len(entries) == 1 and 0 < entries[0].file_size <= 8 * 1024 * 1024,
                    "Missing, duplicate or oversized downstream qualification report")
            raw = handle.read(entries[0])
        require(hashlib.sha256(raw).hexdigest() == evidence["report_sha256"],
                "Downstream qualification report differs from the accepted bytes")
        report = json.loads(raw)
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeError) as error:
        raise ValueError("Cannot read retained downstream qualification report") from error
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] == 2 and report.get("status") == "passed"
            and report.get("full_batch_matrix") is True and report.get("inputs_unchanged") is True
            and report.get("source_unchanged") is True,
            "Updated analyses require the complete unchanged-input/source qualification matrix")

    def source(path):
        require(safe_evidence_path(path), "Invalid downstream source path")
        try:
            data = read_source(record["source_commit"], path)
        except (OSError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise ValueError(f"Cannot read downstream qualification source: {path}") from error
        require(isinstance(data, bytes), "Downstream qualification requires exact source bytes")
        return data

    def hashes(value, label):
        require(isinstance(value, dict) and bool(value)
                and all(safe_evidence_path(path) and valid_digest(digest) for path, digest in value.items()),
                f"Missing or invalid downstream {label} hashes")

    runtime = report.get("runtime")
    require(isinstance(runtime, dict) and runtime.get("kind") == "installed-image"
            and runtime.get("image_id") == evidence["runtime_image"],
            "Local R evidence cannot qualify the packaged scientific image")
    installed = {"scientific/vendor/NEWPAT/" + name: "scientific/vendor/NEWPAT/" + name
                 for name in source_hashes}
    installed.update({source_path("lib/nipat_scientific/" + name, version): source_path("src/nipat_scientific/" + name, version)
                      for name in ANALYSIS_HELPERS})
    require(runtime.get("candidate_and_helper_sha256") == {
        installed_path: hashlib.sha256(source(git_path)).hexdigest()
        for installed_path, git_path in installed.items()},
        "Downstream qualification used different installed R or helper sources")
    require(report.get("verification_script_sha256") ==
            hashlib.sha256(source("scripts/verify_five_modules.py")).hexdigest(),
            "Downstream qualification used a different verifier")
    reference = {"repository": "https://github.com/lpistacchia/NEWPAT",
                 "upstream_commit": reference_commit, "sha256": source_hashes}
    require(report.get("upstream_reference") == reference
            and json.loads(source(reference_root + "/manifest.json")) == reference,
            "Downstream qualification uses a different immutable upstream reference")
    for path, digest in source_hashes.items():
        require(hashlib.sha256(source(reference_root + "/" + path)).hexdigest() == digest,
                "Frozen downstream reference bytes were modified")
    fixtures = report.get("fixture_sha256")
    hashes(fixtures, "fixture")
    required_fixtures = {f"{marker}/{workflow}/{filename}"
        for marker in ("SNP", "DNP") for workflow, filenames in {
            "cpin": ("MotherM.txt", "FatherF.txt", "ChildC.txt", "population.tsv"),
            "cpi": ("MotherM.txt", "FatherF.txt", "MotherN.txt", "FatherN.txt", "population.tsv"),
            "contamination": ("Calls.txt", "panel.tsv"),
        }.items() for filename in filenames}
    require(required_fixtures <= set(fixtures), "Downstream qualification fixture coverage is incomplete")
    for path, digest in fixtures.items():
        require(hashlib.sha256(source("tests/fixtures/five_modules/" + path)).hexdigest() == digest,
                "Downstream fixture differs from the reviewed source")
    registry = json.loads(source(source_path("src/nipat_scientific/settings_data.json", version)))["workflows"]
    expected = analysis_expected_cases()
    results = report.get("results")
    require(isinstance(results, list) and all(isinstance(row, dict) for row in results)
            and len(results) == len(expected)
            and {row.get("name") for row in results} == set(expected),
            "Updated analyses require all 86 unique reference and batch executions")
    by_name = {row["name"]: row for row in results}
    for name, (workflow, marker, candidate, size, mode, cap, variant) in expected.items():
        case = by_name[name]
        require(case.get("status") == "passed" and case.get("inputs_unchanged") is True
                and case.get("workflow") == workflow and case.get("marker") == marker
                and case.get("candidate") is candidate and type(case.get("batch_size")) is int and case["batch_size"] == size
                and case.get("mode") == mode and same_scientific_values(case.get("max_workers"), cap)
                and same_scientific_values(case.get("variant"), variant) and isinstance(case.get("rows"), list) and case["rows"],
                "A downstream execution failed or used different scientific settings")
        for field in ("input_sha256", "output_sha256", "log_sha256"):
            hashes(case.get(field), field)
        require(valid_digest(case.get("summary_sha256")), "Missing downstream summary digest")
        verify_analysis_summary(archive, evidence["report_path"], case, revised_cpi)
        if not candidate:
            require(case.get("worker_evidence") is None and case.get("scientific_settings") is None,
                    "The independent reference cannot use candidate settings or worker helpers")
            continue
        parameters = {key: value["default"] for key, value in registry[workflow]["parameters"].items()}
        if workflow == "cpi":
            parameters["min_fetal_reads"] = variant["minimum"]
        elif workflow == "contamination":
            parameters["include_zero"] = variant["include_zero"]
        elif not revised_cpi:
            parameters["min_child_reads"] = variant["minimum"]
        settings = {"schema_version": 1, "workflow": workflow, "parameters": parameters,
                    "constants": registry[workflow]["constants"]}
        require(case.get("settings_match") is True and same_scientific_values(case.get("scientific_settings"), settings),
                "Downstream native effective parameters/constants differ from the reviewed model")
        worker = case.get("worker_evidence")
        require(isinstance(worker, dict), "Downstream execution lacks worker evidence")
        planned, observed = worker.get("max_planned_workers"), worker.get("observed_peak_workers")
        require(type(planned) is int and type(observed) is int and 1 <= observed <= planned
                and (cap is None or planned <= cap) and (mode != "serial" or planned == observed == 1)
                and type(worker.get("completed_worker_tasks")) is int and worker["completed_worker_tasks"] > 0,
                "Downstream workers exceed their execution budget or did not finish")
        auto_contamination = workflow == "contamination" and mode == "auto"
        measured_batch = auto_contamination and size > 1 and measured_sample_contract(record["version"])
        if auto_contamination and not measured_batch and fixed_admission_contract(record["version"]):
            # Tiny fixture tables are deliberately admitted one at a time until
            # their memory use is observed. Loaded-table parallelism has a
            # separate mandatory exact-image helper; this is not a waiver for
            # missing worker evidence in callers, CPI or CPIN.
            phases = worker.get("phase_plans")
            require(isinstance(phases, list) and len(phases) == 1 and isinstance(phases[0], dict),
                    "Contamination serial admission lacks its explicit resource plan")
            phase = phases[0]
            ceiling = phase.get("worker_ceiling")
            require(planned == observed == 1 and worker.get("observed_child_pids") == []
                    and worker["completed_worker_tasks"] == size
                    and phase.get("label") == "contamination-samples"
                    and type(phase.get("workers")) is int and phase["workers"] == 1
                    and type(phase.get("tasks")) is int and phase["tasks"] == size
                    and phase.get("reason") == "workload-not-observed"
                    and type(ceiling) is int and ceiling >= 1 and (cap is None or ceiling <= cap),
                    "Contamination serial admission differs from its observed tasks or fixed budget")
        elif size > 1 and mode == "auto":
            children = worker.get("observed_child_pids")
            require(planned > 1 and isinstance(children, list)
                    and all(type(pid) is int and pid > 0 for pid in children) and len(set(children)) > 1,
                    "Parallel downstream batches did not execute in distinct child workers")
            if measured_batch:
                phases = worker.get("phase_plans")
                require(isinstance(phases, list) and len(phases) == 1 and isinstance(phases[0], dict),
                        "Contamination batch lacks its sample resource plan")
                phase = phases[0]
                ceiling, memory = phase.get("worker_ceiling"), phase.get("memory_worker_limit")
                require(phase.get("label") == "contamination-samples" and phase.get("tasks") == size
                        and phase.get("workload_model") == "max-loaded-coordinator-rss-x2-and-module-estimate"
                        and type(ceiling) is int and type(memory) is int and min(ceiling, memory) >= 1
                        and (cap is None or ceiling <= cap)
                        and planned == phase.get("workers") == min(size, ceiling, memory)
                        and worker["completed_worker_tasks"] == size,
                        "Contamination sample workers differ from measured workload or shared budget")
    comparisons = {name.removesuffix("-candidate") for name in expected
                   if name.endswith("-candidate")}
    names = report.get("reference_comparisons")
    pairs = report.get("reference_comparison_evidence")
    require(isinstance(names, list) and len(names) == len(comparisons) and set(names) == comparisons
            and isinstance(pairs, dict) and set(pairs) == comparisons,
            "Updated analyses require all 16 independent reference comparisons")
    for name, pair in pairs.items():
        require(isinstance(pair, dict) and pair.get("equal") is True
                and pair.get("candidate_sha256") == by_name[name + "-candidate"]["summary_sha256"]
                and pair.get("reference_sha256") == by_name[name + "-reference"]["summary_sha256"],
                "Downstream reference comparison failed or refers to different scientific outputs")
        compare_analysis_rows(by_name[name + "-candidate"]["rows"], by_name[name + "-reference"]["rows"])
    for marker in ("SNP", "DNP"):
        for workflow in ("cpin", "cpi", "contamination"):
            for count in (2, 3, 5):
                prefix = f"{marker}-{workflow}-batch{count}"
                for cap in (None, 2):
                    compare_analysis_rows(by_name[f"{prefix}-auto-cap{cap}"]["rows"],
                                          by_name[f"{prefix}-serial-capNone"]["rows"])
    return {"report_sha256": evidence["report_sha256"], "runtime_image": evidence["runtime_image"],
            "reference_source_commit": reference_commit,
            "executions_verified": len(results), "reference_comparisons_verified": len(comparisons),
            "batch_executions_verified": sum("-batch" in name for name in expected),
            "scope": "synthetic-independent-oracles-and-upstream-models", "domain_validation_claimed": False}


def verify_fetal_sex_examples(report, source):
    """Compare the two source-free client results with the exact candidate's reference tables."""
    examples = report.get("fetal_sex_examples")
    cases = {"Female_fetus": "F", "Male_fetus": "M"}
    require(isinstance(examples, dict) and set(examples) == set(cases),
            "Both source-free fetal-sex examples must be present")
    root = "tests/fixtures/fetal_sex"
    outputs = ("Fetal_sex_summary.txt", "Autosomal_informative_sites.txt", "X_informative_sites.txt", "Y_sites.txt")
    for name, sex in cases.items():
        case = examples[name]
        require(isinstance(case, dict) and case.get("sample") == name + "_autosomes" and case.get("call") == sex,
                "Fetal-sex example has the wrong call or maternal sample")
        names = [f"{name}_{suffix}.txt" for suffix in ("autosomes", "X", "Y")]
        for field, directory, required in (("input_sha256", f"{root}/inputs", names),
                                           ("output_sha256", f"{root}/outputs/{name}", outputs)):
            require(case.get(field) == {filename: hashlib.sha256(source(f"{directory}/{filename}")).hexdigest()
                                        for filename in required},
                    f"Fetal-sex example {name} {field} differs from the Git fixture")


def verify_prenatal_examples(report, source):
    examples = report.get("prenatal_examples")
    require(isinstance(examples, dict) and set(examples) == {"DNP", "SNP"},
            "Both published prenatal examples must be present")
    for marker, tables in examples.items():
        prefix = f"MotherA1-FatherA1_{marker}s"
        names = {"Summary_FetalFraction_CPI.csv", f"{prefix}_CPI_iterations.csv", f"{prefix}_HOM_child_sites.txt"}
        require(isinstance(tables, dict) and names == set(tables), "Missing prenatal example tables")
        for name in names:
            actual = tables[name]
            require(isinstance(actual, str) and actual, "Empty prenatal example evidence")
            expected = source(f"tests/fixtures/prenatal_cpi/outputs/{marker}/{name}").decode("utf-8")
            separator = "," if name.endswith(".csv") else "\t"
            wanted = csv.DictReader(io.StringIO(expected), delimiter=separator)
            result = csv.DictReader(io.StringIO(actual), delimiter=separator)
            observed_fields = result.fieldnames or []
            require(set(wanted.fieldnames) <= set(observed_fields) and len(set(observed_fields)) == len(observed_fields),
                    "Missing or duplicate prenatal example columns")
            compare_analysis_rows(list(result), list(wanted))


def verify_caller_parallel_qualification(archive, image, *, version, source):
    """Recheck the exact-image acquisition and composed SNP proofs from 0.9.9."""
    filename = "caller-parallel-qualification.json"
    with zipfile.ZipFile(archive) as handle:
        matches = [item for item in handle.infolist() if item.filename.startswith("scientific/")
                   and item.filename.endswith("/newpat-engine-check/" + filename)]
        require(len(matches) == 1 and 0 < matches[0].file_size <= 8 * 1024 * 1024,
                "Missing, duplicate or oversized caller parallel qualification")
        report = json.loads(handle.read(matches[0]))
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] == 1 and report.get("status") == "passed"
            and report.get("runtime_image") == image, "Caller parallel qualification has a different image or status")
    acquisitions = report.get("acquisitions")
    require(isinstance(acquisitions, dict) and set(acquisitions) == {"dnp-call", "snp-call"},
            "Both DNP and SNP acquisition evidence are required")
    for name, count in (("dnp-call", 2), ("snp-call", 1)):
        run = acquisitions[name]
        require(isinstance(run, dict) and type(run.get("bam_count")) is int and run["bam_count"] == count
                and run.get("contigs") == ["chr2", "chr10"] and run.get("strategy") == "indexed-chromosomes"
                and type(run.get("workers")) is int and run["workers"] == 2
                and type(run.get("observed_max_processes")) is int and 0 <= run["observed_max_processes"] <= 2,
                "Missing multi-contig indexed caller qualification")
        children = run.get("child_pids")
        require(isinstance(children, list) and all(type(pid) is int and pid > 0 for pid in children)
                and len(children) == len(set(children)) == 2, "Caller acquisition did not use distinct samtools processes")
        pileup, tables = run.get("pileup_sha256"), run.get("scientific_tables_sha256")
        require(isinstance(pileup, dict) and valid_digest(pileup.get("serial"))
                and pileup.get("auto") == pileup["serial"]
                and isinstance(tables, dict) and isinstance(tables.get("serial"), dict) and tables["serial"]
                and all(isinstance(path, str) and path and valid_digest(value) for path, value in tables["serial"].items())
                and tables.get("auto") == tables["serial"],
                "Serial and parallel acquisition pileup or scientific tables are missing or differ")
    workflow = report.get("five_module_workflow")
    require(isinstance(workflow, dict) and workflow.get("status") == "passed" and workflow.get("image") == image
            and workflow.get("bam_count") == 3 and type(workflow.get("identical_scientific_tables")) is int
            and workflow["identical_scientific_tables"] > 0 and isinstance(workflow.get("runs"), dict),
            "Missing source-free five-module caller qualification")
    for mode in ("serial", "capped"):
        run = workflow["runs"].get(mode)
        require(isinstance(run, dict) and run.get("status") == "succeeded" and run.get("steps") == 10
                and isinstance(run.get("snp_execution_evidence"), dict), "Incomplete SNP workflow qualification")
        policy = run["snp_execution_evidence"]
        admission, execution = policy.get("outer_admission"), policy.get("outer_execution")
        if mode == "serial":
            require(admission is None and execution is None, "Serial SNP workflow launched outer workers")
        else:
            require(isinstance(admission, dict) and admission.get("workers") == 2 and admission.get("tasks") == 3
                    and admission.get("workload_model") == "max-loaded-coordinator-rss-x2-and-module-estimate"
                    and isinstance(execution, dict) and execution.get("maximum_observed_child_workers") == 2
                    and execution.get("simultaneous_child_workers") is True and execution.get("maximum_planned_workers") == 2,
                    "Capped SNP workflow lacks measured two-worker overlap")
            children = execution.get("observed_child_pids")
            require(isinstance(children, list) and all(type(pid) is int and pid > 0 for pid in children)
                    and len(set(children)) >= 2, "Capped SNP workflow lacks distinct child processes")
        inner = policy.get("loaded_r_execution")
        require(isinstance(inner, dict) and len(inner) == 3
                and all(isinstance(worker, dict) and worker.get("maximum_planned_workers") == 1
                        and worker.get("observed_child_pids") == [] for worker in inner.values()),
                "SNP workflow multiplied its shared parallel budget inside a sample")
    fetal_sex_checked = revised_cpi_contract(version)
    if fetal_sex_checked:
        verify_fetal_sex_examples(report, source)
        verify_prenatal_examples(report, source)
    return {**({"fetal_sex_examples_verified": sorted(report["fetal_sex_examples"]),
                "prenatal_examples_verified": sorted(report["prenatal_examples"])} if fetal_sex_checked else {}),
            "acquisitions_verified": sorted(acquisitions),
            "workflow_identical_tables": workflow["identical_scientific_tables"]}


def verify_scientific_equivalence(record, evidence_directory, manifest, read_source):
    """Bind reviewed R results to Git, the retained build evidence and packaged image.

    The caller must first verify the qualification archive and installer set.
    This check adds scientific content validation; it does not turn synthetic
    equivalence into domain validation or claim execution on users' desktops.
    """
    require(record.get("schema_version") in (6, 7), "Scientific evidence requires acceptance schema 6 or 7")
    validate(record, record["version"], record["source_commit"], record["build_run_id"])
    evidence = record["scientific_equivalence"]
    require(manifest.get("source_commit") == record["source_commit"]
            and manifest.get("version") == record["version"]
            and manifest.get("runtime_image") == evidence["runtime_image"],
            "Scientific equivalence does not identify the packaged source and image")
    archive = Path(evidence_directory) / "qualification-evidence.zip"
    require(archive.is_file() and not archive.is_symlink()
            and hashlib.sha256(archive.read_bytes()).hexdigest() == record["qualification_evidence_sha256"],
            "Scientific qualification archive differs from the accepted build")
    commit = record["source_commit"]
    native = None
    try:
        with zipfile.ZipFile(archive) as handle:
            matching = [entry for entry in handle.infolist() if entry.filename == evidence["report_path"]]
            require(len(matching) == 1 and 0 < matching[0].file_size <= 8 * 1024 * 1024,
                    "Missing, duplicate or oversized scientific equivalence report")
            raw = handle.read(matching[0])
            if revised_cpi_contract(record["version"]):
                members = [entry for entry in handle.infolist() if entry.filename.startswith("scientific/")
                           and entry.filename.endswith("/" + native_evidence.REPORT_PATH)]
                require(len(members) == 1 and 0 < members[0].file_size <= 8 * 1024 * 1024,
                        "Missing, duplicate or oversized native R qualification report")
                native_raw = handle.read(members[0])
                native = native_evidence.verify_report(
                    native_raw, commit, read_source=lambda path: read_source(commit, path))
                native["report_sha256"] = hashlib.sha256(native_raw).hexdigest()
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValueError("Cannot read retained scientific equivalence report") from error
    require(hashlib.sha256(raw).hexdigest() == evidence["report_sha256"],
            "Scientific equivalence report bytes differ from the review")
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid scientific equivalence report JSON") from error
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] == 1 and report.get("status") == "passed"
            and report.get("inputs_unchanged") is True
            and report.get("runtime_image") == evidence["runtime_image"],
            "Scientific equivalence did not pass in the packaged image with unchanged inputs")
    five_modules = five_module_contract(record["version"])
    snp2 = snp2_contract(record["version"])
    audited = audited_r_contract(record["version"]) or snp2
    comparison_policy = {"table_bytes": "exact", "unrounded_r": "identical",
                         "pdf_pixels": "exact", "pdf_metadata": "excluded"}
    if snp2:
        comparison_policy.update(pdf_pixels="candidate-serial-vs-parallel",
                                 pdf_reference="structural-and-reviewed-presentation")
    require(report.get("comparison") == comparison_policy,
            "Scientific equivalence must include exact tables, unrounded R values and PDF pixels")

    def source(commit, path):
        try:
            data = read_source(commit, path)
        except (OSError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise ValueError(f"Cannot read scientific equivalence source: {commit}:{path}") from error
        require(isinstance(data, bytes), "Scientific equivalence requires exact source bytes")
        return data

    reference = report.get("reference")
    require(isinstance(reference, dict) and set(reference) == {
        "schema_version", "version", "source_commit", "source_tag", "files",
    } and type(reference["schema_version"]) is int and reference["schema_version"] == 1
            and reference["version"] == "0.8.5" and reference["source_tag"] == "v0.8.5"
            and reference["source_commit"] == R_REFERENCE_COMMIT,
            "Scientific report does not identify the immutable 0.8.5 source")
    expected_paths = set(R_WORKFLOWS) | {
        "docker/scientific-runtime/verify-packages.R", "src/nipat_scientific/presentation.R",
    }
    files = reference["files"]
    require(isinstance(files, list) and len(files) == len(expected_paths)
            and all(isinstance(item, dict) and set(item) == {"path", "sha256"}
                    and isinstance(item["path"], str) and valid_digest(item["sha256"]) for item in files)
            and {item["path"] for item in files} == expected_paths,
            "Scientific reference inventory is incomplete")
    for item in files:
        original = source(R_REFERENCE_COMMIT, item["path"])
        require(hashlib.sha256(original).hexdigest() == item["sha256"]
                and source(commit, R_REFERENCE_ROOT + "/" + item["path"]) == original,
                "Frozen scientific reference differs from the released 0.8.5 source")
    try:
        frozen_manifest = json.loads(source(commit, R_REFERENCE_ROOT + "/manifest.json"))
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid frozen scientific reference manifest") from error
    require(frozen_manifest == reference, "Scientific report differs from the candidate's frozen reference manifest")
    if snp2:
        require(report.get("snp_reference") == SNP2_REFERENCE,
                "Scientific report does not identify the immutable SNPcall 2.0 source")
        require(hashlib.sha256(source(commit, SNP2_REFERENCE["frozen_path"])).hexdigest()
                == SNP2_REFERENCE["sha256"],
                "Frozen SNPcall 2.0 reference differs from the pinned upstream bytes")
        supporting = report.get("supporting_source_sha256")
        presentation = source_path(PRESENTATION_SOURCE, record["version"])
        require(isinstance(supporting, dict) and supporting.get(presentation)
                == hashlib.sha256(source(commit, presentation)).hexdigest(),
                "Scientific presentation evidence used different plotting sources")
    if five_modules:
        require(report.get("supporting_source_sha256") == {
            path: hashlib.sha256(source(commit, path)).hexdigest()
            for path in (source_path(name, record["version"]) for name in CALLER_SUPPORTING_SOURCES)},
            "Caller qualification used different installed scientific helpers")
    workflows = {path: workflow for path, workflow in R_WORKFLOWS.items()
                 if not five_modules or workflow in {"dnp-call", "snp-call"}}
    candidate_hashes = {path: hashlib.sha256(source(commit, path)).hexdigest() for path in workflows}
    all_hashes = {path: hashlib.sha256(source(commit, path)).hexdigest()
                  for path in set(R_WORKFLOWS) | ({CPIN_SOURCE} if five_modules else set())}
    if revised_cpi_contract(record["version"]):
        all_hashes[FETAL_SEX_SOURCE] = hashlib.sha256(source(commit, FETAL_SEX_SOURCE)).hexdigest()
    require(report.get("candidate_r_sha256") == candidate_hashes,
            "Scientific equivalence was performed on different candidate R sources")
    try:
        manifest_rows = [line.split() for line in source(commit, "scientific/SHA256SUMS").decode("ascii").splitlines()
                         if line.strip()]
    except UnicodeError as error:
        raise ValueError("Invalid scientific source hash manifest") from error
    require(len(manifest_rows) == len(all_hashes)
            and all(len(row) == 2 for row in manifest_rows)
            and {"scientific/" + row[1]: row[0] for row in manifest_rows} == all_hashes,
            "Scientific source hash manifest differs from the tested candidate R sources")

    cases = report.get("cases")
    require(isinstance(cases, list) and all(isinstance(case, dict) for case in cases),
            "Scientific differential cases are missing")
    names = [case.get("case") for case in cases]
    required_cases = {**R_CASES, **(R_AUDIT_CASES if audited else {}), **(SNP2_CASES if snp2 else {})}
    if five_modules:
        required_cases = {name: workflow for name, workflow in required_cases.items()
                          if workflow in {"dnp-call", "snp-call"}}
    require(all(isinstance(name, str) and name for name in names) and len(set(names)) == len(names)
            and set(required_cases) <= set(names), "Required scientific differential cases are missing or duplicated")
    plots_verified = 0
    for case in cases:
        require(case.get("status") == "passed" and case.get("unrounded_r_values") == "identical"
                and case.get("workflow") in set(workflows.values())
                and (case["case"] not in required_cases or case["workflow"] == required_cases[case["case"]]),
                "A scientific differential case failed or has a different workflow")
        if snp2:
            expected_reference = "SNPcall 2.0" if case["workflow"] == "snp-call" else "v0.8.5"
            require(case.get("scientific_reference") == expected_reference,
                    "Scientific differential case used the wrong algorithm reference")
        tables = case.get("table_sha256")
        require(isinstance(tables, dict) and tables
                and all(safe_evidence_path(name) and valid_digest(value) for name, value in tables.items()),
                "Scientific differential table evidence is incomplete")
        plots = case.get("plots")
        require(isinstance(plots, dict)
                and len(plots) >= R_REQUIRED_PDFS.get(case["case"], 0),
                "Scientific PDF comparison evidence is missing or incomplete for a required case")
        for name, plot in plots.items():
            require(safe_evidence_path(name) and isinstance(plot, dict)
                    and type(plot.get("pages")) is int and plot["pages"] > 0
                    and type(plot.get("raster_dpi")) is int and plot["raster_dpi"] >= 36
                    and isinstance(plot.get("page_sha256"), dict)
                    and len(plot["page_sha256"]) == plot["pages"]
                    and all(safe_evidence_path(page) and valid_digest(value)
                            for page, value in plot["page_sha256"].items()),
                    "Scientific PDF pixel comparison evidence is incomplete")
            if snp2:
                dimensions = plot.get("page_size_points")
                require(isinstance(dimensions, list) and len(dimensions) == 2
                        and all(type(value) in (int, float) and 0 < value <= 1440 for value in dimensions),
                        "Scientific PDF dimensions are missing or exceed the reviewed presentation bounds")
            plots_verified += 1
        if snp2:
            verify_presentation_variants(case)
        if audited and case["case"] in R_MULTIBAM_PDFS:
            require(len(plots) >= R_MULTIBAM_PDFS[case["case"]],
                    "Multi-BAM PDF comparisons are incomplete")
            verify_multibam_variants(case)
    require(plots_verified > 0, "Scientific equivalence contains no rendered PDF comparisons")
    helpers = report.get("helpers")
    require(isinstance(helpers, list) and all(isinstance(item, dict) for item in helpers),
            "Scientific focused comparisons are missing")
    paths = [item.get("path") for item in helpers]
    required_helpers = (R_HELPERS | (R_AUDIT_HELPERS if audited else set())
                        | ({PRESENTATION_HELPER} if snp2 else set()))
    if five_modules:
        required_helpers = {path for path in required_helpers
                            if not path.startswith(("tests/r_optimization/cpi/", "tests/r_optimization/contamination/"))}
        if fixed_admission_contract(record["version"]):
            required_helpers.add("tests/r_optimization/contamination/check_parallel.R")
    require(all(safe_evidence_path(path) and path.startswith("tests/r_optimization/") for path in paths)
            and len(set(paths)) == len(paths) and required_helpers <= set(paths),
            "Required scientific focused comparisons are missing or duplicated")
    for helper in helpers:
        require(helper.get("status") == "passed" and helper.get("sha256") ==
                hashlib.sha256(source(commit, helper["path"])).hexdigest(),
                "Scientific focused comparison failed or used different test sources")
    analysis = verify_analysis_qualification(record, evidence_directory, read_source) if five_modules else None
    callers = (verify_caller_parallel_qualification(archive, evidence["runtime_image"],
                                                   version=record["version"], source=lambda path: source(commit, path))
               if measured_sample_contract(record["version"]) else None)
    return {"source_commit": commit, "reference_source_commit": R_REFERENCE_COMMIT,
            **({"native_r_qualification": native} if native is not None else {}),
            **({"scientific_analysis_qualification": analysis} if analysis else {}),
            **({"caller_parallel_qualification": callers} if callers else {}),
            **({"snp_reference": SNP2_REFERENCE} if snp2 else {}),
            "runtime_image": evidence["runtime_image"], "report_sha256": evidence["report_sha256"],
            "candidate_r_sha256": candidate_hashes, "cases_verified": len(cases),
            "focused_scripts_verified": len(helpers), "pdfs_verified": plots_verified,
            "scope": "synthetic-equivalence-only", "domain_validation_claimed": False}


def operative_inventory(data, *, version=None):
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ValueError("Invalid source inventory encoding") from error
    paths = set()
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        path = PurePosixPath(value)
        require(not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
                and "\\" not in value and value not in paths, "Invalid or duplicate source inventory path")
        paths.add(value)
    # The baseline can predate the package rename. A candidate must satisfy the
    # exact contract for its own version, including both CLI and Inno sources.
    layouts = (version,) if version is not None else ("0.9.10", "0.9.99")
    require("distribution-files.txt" in paths and any(
        {source_path(path, layout) for path in REQUIRED_OPERATIVE_PATHS} <= paths for layout in layouts),
            "Source inventory omits required operative inputs")
    return {path for path in paths if path != "distribution-files.txt"
            and not path.startswith(".github/") and PurePosixPath(path).suffix.casefold() != ".md"}


def verify_baseline(record, read_source):
    """Compare operative source bytes; this does not assert installer or image identity.

    Markdown documentation and .github maintenance/CI/release procedures are not
    executable inputs of the installed application. The allowlist is compared as
    a normalized inventory. Schema 2 only exempts removal of two obsolete signing
    helpers. Schema 3 requires an exact hash review for permitted client changes
    and keeps scientific, engine and runtime sources immutable. Schema 4 reviews
    non-R operative changes without claiming operational equivalence to the
    historical manual observation. Schema 5 permits reviewed presentation adapters
    while preserving the vendored scientific R sources byte for byte. Schema 6
    allows the four known scientific scripts and their hash manifest to be
    reviewed, plus the bundled SNP example output from 0.8.30. Separate
    evidence verification is mandatory before publication.
    """
    require(isinstance(record, dict) and type(record.get("schema_version")) is int
            and record["schema_version"] in (1, 2, 3, 4, 5, 6, 7), "Unsupported acceptance schema")
    if record["schema_version"] == 1:
        return None
    five_modules = record["schema_version"] == 7
    revised_r = record["schema_version"] in (6, 7)
    multiplatform = record["schema_version"] in (5, 6, 7)
    reliability = record["schema_version"] in (4, 5, 6, 7)
    reviewed_delta = record["schema_version"] in (3, 4, 5, 6, 7)
    expected_fields = (FIVE_MODULE_RESEARCH_FIELDS if five_modules else SCIENTIFIC_RESEARCH_FIELDS if revised_r else MULTIPLATFORM_RESEARCH_FIELDS if multiplatform else RELIABILITY_RESEARCH_FIELDS if reliability else
                       REVIEWED_RESEARCH_FIELDS if reviewed_delta else RESEARCH_FIELDS)
    require(set(record) == expected_fields | publication_fields(record["version"]) | zip_fields(record["version"]) | payload_fields(record["version"]) | testing_entrypoint_fields(record["version"]),
            "Research acceptance record fields are invalid")
    validate_research(record, record["version"], record["source_commit"], record["build_run_id"])
    baseline = record["observed_baseline"]["source_commit"]
    candidate = record["source_commit"]

    def read(commit, path):
        try:
            result = read_source(commit, path)
        except (OSError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise ValueError(f"Cannot read baseline equivalence input: {commit}:{path}") from error
        require(isinstance(result, bytes), "Source equivalence requires exact file bytes")
        return result

    before = operative_inventory(read(baseline, "distribution-files.txt"))
    after = operative_inventory(read(candidate, "distribution-files.txt"), version=record["version"])
    if reviewed_delta:
        changes = []
        unchanged = 0
        for path in sorted(before | after):
            old = read(baseline, path) if path in before else None
            new = read(candidate, path) if path in after else None
            if old == new:
                unchanged += 1
                continue
            after_sha256 = hashlib.sha256(new).hexdigest() if new is not None else None
            require(reviewable_path(path, reliability=reliability, multiplatform=multiplatform,
                                    revised_r=revised_r, version=record["version"], removed=new is None,
                                    after_sha256=after_sha256),
                    f"Protected scientific or runtime source differs: {path}")
            changes.append({"path": path,
                            "before_sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
                            "after_sha256": after_sha256})
        require(record["reviewed_source_changes"] == changes,
                "Reviewed source changes do not match the exact baseline-to-candidate delta")
        return {"baseline_source_commit": baseline, "source_commit": candidate,
                "scope": FIVE_MODULE_SOURCE_SCOPE if five_modules else REVISED_R_SOURCE_SCOPE if revised_r else MULTIPLATFORM_SOURCE_SCOPE if multiplatform else RELIABILITY_SOURCE_SCOPE if reliability else REVIEWED_SOURCE_SCOPE,
                "unchanged_files_verified": unchanged,
                "reviewed_source_changes": changes, "candidate_windows_installation_claimed": False,
                **({"operational_equivalence_claimed": False,
                    "vendored_r_sources_unchanged" if multiplatform else "r_sources_unchanged": not revised_r}
                   if reliability else {})}
    before -= REMOVABLE_SIGNING_HELPERS & (before - after)
    require(before == after, "Baseline operative inventory differs from candidate")
    for path in sorted(after):
        require(read(baseline, path) == read(candidate, path), f"Baseline operative source differs: {path}")
    return {"baseline_source_commit": baseline, "source_commit": candidate,
            "scope": SOURCE_EQUIVALENCE_SCOPE, "files_verified": len(after)}


def load(version, commit, run_id, publication_commit, read_source):
    path = acceptance_path(version)
    try:
        raw = read_source(publication_commit, path)
    except (OSError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        raise ValueError(f"Missing committed desktop acceptance: {path}") from error
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Invalid committed desktop acceptance: {path}") from error
    validate(record, version, commit, run_id)
    return record, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-set", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = template(json.loads(args.installer_set.read_text(encoding="utf-8")), args.run_id)
    # Never replace an existing acceptance record or represent this template as approval.
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
    print("Pending acceptance template written; no publication is authorized.")


if __name__ == "__main__":
    main()
