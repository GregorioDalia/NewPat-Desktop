"""Native architectures must pass the same cases on the same candidate."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compare_native_oracles import compare_reports
from test_native_evidence import COMMIT, native_fixture


class CompareNativeOraclesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        paths, sources, self.report = native_fixture()
        self.enterContext(patch("native_evidence.git_native_test_paths", return_value=paths))
        self.enterContext(patch("native_evidence.git_source", side_effect=lambda commit, path: sources[path]))
        for arch, machine in (("arm64", "aarch64"), ("amd64", "x86_64")):
            evidence = self.root / f"scientific-oracles-{arch}"
            evidence.mkdir()
            (evidence / "native-r.json").write_text(json.dumps(self.report))
            (evidence / "source-commit").write_text(COMMIT)
            (evidence / "architecture.txt").write_text(f"runner={machine}\nimage=linux/{arch}\nR={machine}\n")
        self.arm = self.root / "scientific-oracles-arm64"

    def test_equal_cases_in_a_different_order_pass(self):
        self.report["subcases"].reverse()
        self.report["methods"][0]["seconds"] = 5
        (self.arm / "native-r.json").write_text(json.dumps(self.report))
        self.assertIn("4 tests with the same 2 subcases", compare_reports(self.root, COMMIT))

    def test_same_number_of_successful_cases_is_insufficient(self):
        self.report["subcases"][0]["case"] += " (different input)"
        (self.arm / "native-r.json").write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError, "different scientific oracle subcases"):
            compare_reports(self.root, COMMIT)

    def test_missing_native_execution_wrong_checkout_and_tool_mismatch_fail(self):
        for file, content, reason in (
            ("architecture.txt", "runner=aarch64\nimage=linux/amd64\nR=x86_64", "native environment"),
            ("source-commit", "b" * 40, "different checkout"),
            ("native-r.json", json.dumps(dict(self.report, passed=False)), "successfully"),
            ("native-r.json", json.dumps(dict(self.report, samtools_version="2.0")), "samtools_version"),
        ):
            path = self.arm / file
            original = path.read_bytes()
            with self.subTest(file=file, reason=reason):
                path.write_text(content)
                with self.assertRaisesRegex(ValueError, reason):
                    compare_reports(self.root, COMMIT)
                path.write_bytes(original)
