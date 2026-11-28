"""Validate native R evidence against the exact Git checkout used for qualification."""

import ast
import hashlib
import json
from pathlib import PurePosixPath
import re
import subprocess


REPORT_PATH = "newpat-native-r-check/native-r.json"
RUNNER = ".github/scripts/check_native_r.py"
SETTINGS_TEST = "tests/test_scientific_settings.py"
SUPPORT = {RUNNER, SETTINGS_TEST, "tests/native_r_helpers.py", "tests/native_engine_helpers.py",
           "tests/downstream_oracle_tables.py"}
MANIFEST = "scientific/SHA256SUMS"


class NativeEvidenceError(ValueError):
    """A native qualification check failed with a safe diagnostic."""


def require(condition, message):
    if not condition:
        raise NativeEvidenceError(message)


def git_native_test_paths(commit):
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "-z", commit, "--", "tests"], stderr=subprocess.PIPE
    ).decode().split("\0")
    return {path for path in paths if re.fullmatch(r"tests/test_native_r_[^/]+\.py", path)}


def git_source(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], stderr=subprocess.PIPE)


def declared_test_methods(path, data):
    # These unittest suites declare test methods on top-level TestCase classes.
    # Read pinned source as data; never import tests or run candidate code to validate evidence.
    module = PurePosixPath(path).stem
    methods = {}
    for cls in ast.parse(data).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for method in cls.body:
            if isinstance(method, ast.FunctionDef) and method.name.startswith("test_"):
                uses_subtests = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                                    and node.func.attr == "subTest" for node in ast.walk(method))
                methods[f"{module}.{cls.name}.{method.name}"] = uses_subtests
    return methods


def verify_native_report(report, read_source, test_paths):
    require(isinstance(report, dict) and type(report.get("schema_version")) is int
            and report["schema_version"] in {1, 2} and report.get("status") == "completed"
            and report.get("passed") is True, "Native R qualification did not complete successfully")
    require(all(report.get(field) == [] for field in ("missing_oracle_modules", "failures", "errors", "skipped",
                                                       "expected_failures", "unexpected_successes")),
            "Native R qualification has incomplete or unsuccessful outcomes")
    methods = report.get("methods")
    require(type(report.get("tests_run")) is int and isinstance(methods, list)
            and report["tests_run"] == len(methods) > 0, "Native R test count is missing or inconsistent")
    require(all(isinstance(row, dict) and isinstance(row.get("id"), str)
                and type(row.get("seconds")) in (int, float) and 0 <= row["seconds"] < float("inf") for row in methods),
            "Native R test method entries are invalid")
    method_ids = {row["id"] for row in methods}
    require(len(method_ids) == len(methods), "Duplicate native R test methods")
    subcases = report.get("subcases")
    require(isinstance(subcases, list) and bool(subcases)
            and all(isinstance(row, dict) and row.get("status") == "passed" and isinstance(row.get("test"), str)
                    and row["test"] in method_ids and isinstance(row.get("case"), str)
                    and row["case"].startswith(row["test"] + " ") for row in subcases),
            "Native R subcase outcomes are incomplete or inconsistent")
    require(len({row["case"] for row in subcases}) == len(subcases), "Native R subcase identifiers are duplicated")
    observed_subtests = {row["test"] for row in subcases}
    require(all(isinstance(report.get(key), str) and report[key].strip() for key in ("r_version", "samtools_version")),
            "Native R runtime versions are missing")

    tests = set(test_paths)
    suite_paths = SUPPORT | tests
    digests = report.get("suite_source_sha256")
    require(tests and isinstance(digests, dict) and set(digests) == suite_paths,
            "Native R suite source inventory differs from the candidate")
    expected_methods = {}
    modules = {PurePosixPath(path).stem for path in tests}
    for path in sorted(suite_paths):
        data = read_source(path)
        require(digests[path] == hashlib.sha256(data).hexdigest(), "Native R suite source digest differs from candidate")
        if path == RUNNER:
            # The runner's pinned oracle list is part of the candidate, including during historical reviews.
            constants = {target.id: node.value for node in ast.parse(data).body if isinstance(node, ast.Assign)
                         for target in node.targets if isinstance(target, ast.Name)}
            oracles = constants.get("ORACLE_MODULES")
            require(isinstance(oracles, ast.Set) and oracles.elts
                    and all(isinstance(item, ast.Constant) and item.value in modules for item in oracles.elts),
                    "Native R candidate oracle suite is incomplete")
            # The first runner emitted schema 1 before it declared a version or a subcase count.
            version = constants.get("REPORT_SCHEMA_VERSION", ast.Constant(value=1))
            require(isinstance(version, ast.Constant) and type(version.value) is int
                    and version.value == report["schema_version"], "Native R report schema differs from its runner")
            if version.value >= 2:
                require(type(report.get("subcases_run")) is int and report["subcases_run"] == len(subcases),
                        "Native R subcase count is missing or inconsistent")
        if path in tests or path == SETTINGS_TEST:
            declared = declared_test_methods(path, data)
            require(bool(declared), "Native R test module has no declared methods")
            expected_methods.update(declared)
    require(expected_methods.keys() == method_ids, "Native R test method coverage differs from the candidate suite")
    require(all(method in observed_subtests for method, uses_subtests in expected_methods.items() if uses_subtests),
            "Native R subcase coverage differs from the candidate test methods")
    require(report.get("scientific_manifest_sha256") == hashlib.sha256(read_source(MANIFEST)).hexdigest(),
            "Native R scientific manifest differs from the candidate")
    return {"tests_run": len(methods), "subcases": len(subcases)}


def verify_report(raw, commit, *, read_source=None, test_paths=None):
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
            "Native R source commit is invalid")
    require(isinstance(raw, bytes), "Native R qualification report is missing")
    try:
        paths = git_native_test_paths(commit) if test_paths is None else test_paths
        return verify_native_report(json.loads(raw), read_source or (lambda path: git_source(commit, path)), paths)
    except (OSError, KeyError, SyntaxError, subprocess.SubprocessError) as error:
        raise NativeEvidenceError("Unable to verify native R qualification against the candidate sources") from error
