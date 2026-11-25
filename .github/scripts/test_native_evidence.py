"""Retained native R reports must match what the reviewed candidate actually tested."""

import hashlib
import json
import unittest
from unittest.mock import Mock, patch

import native_evidence as native


COMMIT = "a" * 40


def native_fixture():
    test_path = "tests/test_native_r_sample.py"
    code = b"class SampleTests(unittest.TestCase):\n    def test_first(self): pass\n    def test_second(self): pass\n"
    sources = {path: b"# support file\n" for path in native.SUPPORT}
    sources.update({test_path: code.replace(b": pass", b":\n        with self.subTest(depth=0): pass"), native.SETTINGS_TEST: code, native.MANIFEST: b"R manifest\n",
                    native.RUNNER: b"REPORT_SCHEMA_VERSION = 2\nORACLE_MODULES = {'test_native_r_sample'}\n"})
    ids = [f"{module}.SampleTests.test_{name}" for module in ("test_native_r_sample", "test_scientific_settings")
           for name in ("first", "second")]
    report = {"schema_version": 2, "subcases_run": 2, "passed": True, "status": "completed", "tests_run": len(ids),
              "methods": [{"id": member, "seconds": 0.01} for member in ids],
              "subcases": [{"test": method, "case": method + " (depth=0)", "status": "passed"} for method in ids[:2]],
              "suite_source_sha256": {path: hashlib.sha256(data).hexdigest() for path, data in sources.items()
                                      if path != native.MANIFEST},
              "scientific_manifest_sha256": hashlib.sha256(sources[native.MANIFEST]).hexdigest(),
              "r_version": "Rscript 4", "samtools_version": "1.0"}
    report.update({field: [] for field in ("missing_oracle_modules", "failures", "errors", "skipped",
                                            "expected_failures", "unexpected_successes")})
    return {test_path}, sources, report


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.paths, self.sources, self.report = native_fixture()

    def verify(self):
        return native.verify_report(json.dumps(self.report).encode(), COMMIT, test_paths=self.paths,
                                    read_source=self.sources.__getitem__)

    def test_complete_candidate_is_verified_without_fixed_test_counts(self):
        self.assertEqual(self.verify(), {"tests_run": 4, "subcases": 2})
        source = Mock(side_effect=lambda commit, path: self.sources[path])
        with patch.object(native, "git_native_test_paths", return_value=self.paths) as paths, \
                patch.object(native, "git_source", source):
            native.verify_report(json.dumps(self.report).encode(), COMMIT)
        paths.assert_called_once_with(COMMIT)
        self.assertEqual({call.args for call in source.call_args_list}, {(COMMIT, path) for path in self.sources})

    def test_source_version_requires_the_original_number_of_subcases(self):
        # Another passing case for a method that already appears in the report.
        first = self.report["subcases"][0]
        self.report["subcases"].append({**first, "case": first["test"] + " (depth=1)"})
        self.report["subcases_run"] = 3
        self.assertEqual(self.verify()["subcases"], 3)
        self.report["subcases"].pop()
        with self.assertRaisesRegex(ValueError, "subcase count"):
            self.verify()
        self.report.pop("subcases_run")
        with self.assertRaisesRegex(ValueError, "subcase count"):
            self.verify()
        self.report["schema_version"] = 1
        with self.assertRaisesRegex(ValueError, "schema differs"):
            self.verify()
        # A historical runner genuinely emitted schema 1 without subcases_run.
        self.sources[native.RUNNER] = self.sources[native.RUNNER].split(b"\n", 1)[1]
        self.report["suite_source_sha256"][native.RUNNER] = hashlib.sha256(self.sources[native.RUNNER]).hexdigest()
        self.assertEqual(self.verify()["subcases"], 2)

    def test_method_removal_even_with_consistent_count_is_rejected(self):
        self.report["methods"].pop()
        self.report["tests_run"] -= 1
        with self.assertRaisesRegex(ValueError, "method coverage"):
            self.verify()

    def test_oracle_named_in_the_runner_must_be_in_the_candidate_inventory(self):
        data = b"ORACLE_MODULES = {'test_native_r_sample', 'test_native_r_absent'}\n"
        self.sources[native.RUNNER] = data
        self.report["suite_source_sha256"][native.RUNNER] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError, "oracle suite is incomplete"):
            self.verify()

    def test_partial_failed_duplicate_or_untraceable_results_are_rejected(self):
        for edit in (lambda: self.report.update(tests_run=0), lambda: self.report.update(passed=False),
                     lambda: self.report.update(status="incomplete"), lambda: self.report.pop("errors"),
                     lambda: self.report.update(skipped=["test_first"]), lambda: self.report.update(subcases=[]),
                     lambda: self.report["methods"].__setitem__(1, self.report["methods"][0]),
                     lambda: self.report["subcases"][0].update(status="failed"),
                     lambda: self.report["subcases"].pop(),
                     lambda: self.report["subcases"].append(self.report["subcases"][0]),
                     lambda: self.report["subcases"][0].update(test="unrelated.test"),
                     lambda: self.report["suite_source_sha256"].pop(native.SETTINGS_TEST),
                     lambda: self.report["suite_source_sha256"].update({native.SETTINGS_TEST: "b" * 64}),
                     lambda: self.report.update(scientific_manifest_sha256="c" * 64),
                     lambda: self.paths.add("tests/test_native_r_new.py")):
            with self.subTest(edit=edit.__code__.co_firstlineno):
                self.paths, self.sources, self.report = native_fixture()
                edit()
                with self.assertRaises(ValueError):
                    self.verify()
