"""Run mandatory native R regressions using only the installed scientific payload."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = Path("/opt/nipat")


# These suites exercise reads and mathematical expectations independently of the frozen R versions.
ORACLE_MODULES = {
    "test_native_r_caller_oracle",
    "test_native_r_contamination_oracle",
    "test_native_r_prenatal_oracle",
    "test_native_r_postnatal_contract",
    "test_native_r_family_oracle",
    "test_native_r_reference_oracles",
}


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.methods = []
        self.subcases = []

    def startTest(self, test):
        super().startTest(test)
        self.started = time.monotonic()

    def stopTest(self, test):
        self.methods.append({"id": test.id(), "seconds": round(time.monotonic() - self.started, 3)})
        super().stopTest(test)

    def addSubTest(self, test, subtest, err):
        self.subcases.append({"test": test.id(), "case": subtest.id(),
                              "status": "passed" if err is None else "failed"})
        super().addSubTest(test, subtest, err)

    def report(self, required_modules):
        observed = {item["id"].split(".", 1)[0] for item in self.methods}
        missing = sorted(required_modules - observed)
        return {
            "schema_version": 1,
            "passed": bool(self.testsRun and self.wasSuccessful() and not self.skipped
                           and not self.expectedFailures and not missing),
            "tests_run": self.testsRun,
            "methods": self.methods,
            "subcases": self.subcases,
            "missing_oracle_modules": missing,
            "failures": [{"id": test.id(), "detail": detail} for test, detail in self.failures],
            "errors": [{"id": test.id(), "detail": detail} for test, detail in self.errors],
            "skipped": [{"id": test.id(), "reason": reason} for test, reason in self.skipped],
            "expected_failures": [{"id": test.id(), "detail": detail} for test, detail in self.expectedFailures],
            "unexpected_successes": [test.id() for test in self.unexpectedSuccesses],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write a JSON report for the executed suite.")
    args = parser.parse_args()
    if args.report:
        # A failed prerequisite check must not leave a previous passing report in place.
        args.report.write_text(json.dumps({"schema_version": 1, "passed": False,
                                           "status": "incomplete"}) + "\n", encoding="utf-8")
    # Host R can be incomplete and native unit tests then explicitly skip.
    # The packaged-image gate must instead fail missing tools/dependencies.
    from nipat_scientific.settings import REGISTRY
    if REGISTRY.resolve() != PAYLOAD / "lib/nipat_scientific/settings_data.json":
        raise RuntimeError("Native regressions must use the installed scientific settings")
    sys.path.insert(0, str(ROOT / "tests"))
    from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
    if not NATIVE_R_AVAILABLE:
        raise RuntimeError("Packaged R prerequisites are incomplete: " + NATIVE_R_REASON)
    os.environ["NIPAT_NATIVE_TEST_PAYLOAD_ROOT"] = str(PAYLOAD)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.discover(str(ROOT / "tests"), pattern=pattern)
                              for pattern in ("test_native_r_*.py", "test_scientific_settings.py"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    for name, module in tuple(sys.modules.items()):
        if name == "nipat_scientific" or name.startswith("nipat_scientific."):
            source = getattr(module, "__file__", None)
            if source is not None and not Path(source).resolve().is_relative_to(PAYLOAD / "lib/nipat_scientific"):
                raise RuntimeError(f"Native regressions imported a checkout replacement: {name}")
    report = result.report(ORACLE_MODULES)
    if args.report:
        tests = ROOT / "tests"
        sources = sorted({Path(__file__), *tests.glob("test_native_r_*.py"),
                          *(tests / name for name in ("test_scientific_settings.py", "native_r_helpers.py",
                                                      "native_engine_helpers.py", "downstream_oracle_tables.py"))})
        report.update(
            status="completed",
            suite_source_sha256={path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sources},
            scientific_manifest_sha256=hashlib.sha256((PAYLOAD / "scientific/SHA256SUMS").read_bytes()).hexdigest(),
            r_version=subprocess.check_output(["Rscript", "--version"], text=True, stderr=subprocess.STDOUT).strip(),
            samtools_version=subprocess.check_output(["samtools", "--version-only"], text=True).strip(),
        )
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["missing_oracle_modules"]:
        print("No tests executed for: " + ", ".join(report["missing_oracle_modules"]), file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
