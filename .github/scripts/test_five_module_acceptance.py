"""Publication requires both versioned science gates for the exact five-module build."""

import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest import mock
import zipfile

import test_revised_r_acceptance as legacy_tests
from test_revised_r_acceptance import acceptance, COMMIT, IMAGE, digest

ROOT = Path(__file__).resolve().parents[2]


class RevisedCpiReleaseTests(unittest.TestCase):
    # Native output for two synthetic SNP trios in the serial qualification matrix.
    header = ("Trio\tMarker_type\tN_sites\tN_hom_hom\tN_hom_het\tN_het_hom\tN_het_het"
              "\tMatching_sites\tMismatching_sites\tNo_obligatory_allele_sites\tMaternal_incompatible_sites"
              "\tLog10_CPI\tCPI\tMismatch_probability\tMin_coverage"
              "\tInclude_hom_hom\tInclude_hom_het\tInclude_het_hom\tInclude_het_het\n")
    values = ("\tSNP\t5\t1\t3\t0\t1\t2\t2\t1\t1\t-4.88536122003151\t1.30208333333333e-05"
              "\t0.001\tNA\tTRUE\tTRUE\tTRUE\tTRUE\n")
    first = "MotherM1-FatherF1-ChildC1_SNPs" + values
    second = "MotherM2-FatherF2-ChildC2_SNPs" + values

    def verify_postnatal(self, summary, *, reported=None):
        raw = summary.encode()
        name = "SNP-cpin-batch2-serial-capNone"
        filename = "Summary_Postnatal_CPI.txt"
        rows = list(csv.DictReader(io.StringIO(summary), delimiter="\t"))
        case = {"name": name, "workflow": "cpin", "marker": "SNP", "batch_size": 2,
                "rows": rows if reported is None else reported,
                "output_sha256": {filename: digest(raw)}, "summary_sha256": digest(raw)}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr(f"reports/{name}/output/{filename}", raw)
        acceptance.verify_analysis_summary(archive, "reports/five-module-qualification.json", case,
                                           revised_cpi=acceptance.revised_cpi_contract("0.9.10"))

    def test_accepts_native_scalar_bytes_and_rejects_misreported_rows(self):
        summary = self.header + self.first + self.second
        self.verify_postnatal(summary)
        reported = list(csv.DictReader(io.StringIO(summary), delimiter="\t"))
        reported[1]["CPI"] = "1"
        with self.assertRaisesRegex(ValueError, "retained summary bytes"):
            self.verify_postnatal(summary, reported=reported)

    def test_retained_rows_require_each_requested_trio_once(self):
        for data in (self.first, self.first + self.first, self.first + self.first + self.second + self.second):
            with self.subTest(row_count=len(data.splitlines())), self.assertRaisesRegex(ValueError, "one row per"):
                self.verify_postnatal(self.header + data)

    def test_rejects_scalar_with_missing_scientific_fields_even_with_matching_digests(self):
        for column in ("CPI", "Log10_CPI", "N_het_het", "No_obligatory_allele_sites",
                       "Mismatch_probability", "Min_coverage", "Include_het_hom"):
            rows = csv.DictReader(io.StringIO(self.header + self.first + self.second), delimiter="\t")
            stream = io.StringIO()
            writer = csv.DictWriter(stream, [key for key in rows.fieldnames if key != column],
                                    delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, "columns are incomplete"):
                self.verify_postnatal(stream.getvalue())

    def test_releases_pin_the_correct_frozen_model_bytes(self):
        versions = {"0.9.9": "9c2a8be60afcb944153710da6a61cd0559e2b4cf",
                    "0.9.10": "c753afc4be62dfc0b81b8cb683a6e850516f5ffd"}
        for version, expected in versions.items():
            with self.subTest(version=version):
                commit, directory, hashes = acceptance.downstream_reference(version)
                self.assertEqual(commit, expected)
                manifest = json.loads((ROOT / directory / "manifest.json").read_bytes())
                self.assertEqual((manifest["upstream_commit"], manifest["sha256"]), (expected, hashes))
                self.assertEqual({path: digest((ROOT / directory / path).read_bytes()) for path in hashes}, hashes)
                evidence = {"reference_source_commit": expected, "report_sha256": "d" * 64,
                            "runtime_image": IMAGE, "report_path": "scientific/five-module-qualification.json"}
                acceptance.validate_analysis_record(evidence, version)
                other = next(commit for commit in versions.values() if commit != expected)
                with self.assertRaisesRegex(ValueError, "frozen NEWPAT reference"):
                    acceptance.validate_analysis_record({**evidence, "reference_source_commit": other}, version)


class FiveModuleAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.legacy = legacy_tests.RevisedRAcceptanceTests()
        self.legacy.setUp()
        self.addCleanup(self.legacy.doCleanups)
        self.legacy.snp2_report()
        self.record = self.legacy.record
        self.manifest = self.legacy.manifest
        self.record.update(schema_version=7, version="0.8.50")
        self.manifest["version"] = "0.8.50"
        self.record["observed_baseline"]["source_comparison_scope"] = acceptance.FIVE_MODULE_SOURCE_SCOPE
        self.record["scientific_analysis_qualification"] = {
            "reference_source_commit": acceptance.ANALYSIS_REFERENCE_COMMIT,
            "report_path": "scientific/newpat-five-modules-check/artifacts/five-module-qualification.json",
            "report_sha256": "e" * 64, "runtime_image": IMAGE,
        }
        sources = self.legacy.sources[COMMIT]
        for path in ["scripts/verify_five_modules.py", acceptance.CPIN_SOURCE,
                *("src/nipat_scientific/" + name for name in acceptance.ANALYSIS_HELPERS),
                *acceptance.CALLER_SUPPORTING_SOURCES]:
            sources[path] = (ROOT / acceptance.source_path(path, "0.9.99")).read_bytes()
        for path in (ROOT / acceptance.ANALYSIS_REFERENCE_ROOT).rglob("*"):
            if path.is_file():
                sources[path.relative_to(ROOT).as_posix()] = path.read_bytes()
        fixtures = {}
        for path in (ROOT / "tests/fixtures/five_modules").rglob("*"):
            if path.is_file():
                relative = path.relative_to(ROOT).as_posix()
                sources[relative] = path.read_bytes()
                fixtures[path.relative_to(ROOT / "tests/fixtures/five_modules").as_posix()] = digest(path.read_bytes())
        caller = self.legacy.report
        caller["candidate_r_sha256"] = {path: value for path, value in caller["candidate_r_sha256"].items()
                                        if acceptance.R_WORKFLOWS[path] in {"dnp-call", "snp-call"}}
        caller["cases"] = [case for case in caller["cases"] if case["workflow"] in {"dnp-call", "snp-call"}]
        caller["helpers"] = [helper for helper in caller["helpers"]
            if not helper["path"].startswith(("tests/r_optimization/cpi/", "tests/r_optimization/contamination/"))]
        caller["supporting_source_sha256"] = {path: digest(sources[path]) for path in acceptance.CALLER_SUPPORTING_SOURCES}
        sources["scientific/SHA256SUMS"] = "".join(f"{digest(sources[path])}  {path.removeprefix('scientific/')}\n"
            for path in sorted(set(acceptance.R_WORKFLOWS) | {acceptance.CPIN_SOURCE})).encode()
        installed = {"scientific/vendor/NEWPAT/" + name: "scientific/vendor/NEWPAT/" + name
                     for name in acceptance.ANALYSIS_REFERENCE_SHA256}
        installed.update({"lib/nipat_scientific/" + name: "src/nipat_scientific/" + name
                          for name in acceptance.ANALYSIS_HELPERS})
        self.report = {
            "schema_version": 2, "status": "passed", "full_batch_matrix": True,
            "inputs_unchanged": True, "source_unchanged": True,
            "runtime": {"kind": "installed-image", "image_id": IMAGE,
                        "candidate_and_helper_sha256": {key: digest(sources[path]) for key, path in installed.items()}},
            "verification_script_sha256": digest(sources["scripts/verify_five_modules.py"]),
            "upstream_reference": json.loads(sources[acceptance.ANALYSIS_REFERENCE_ROOT + "/manifest.json"]),
            "fixture_sha256": fixtures, "results": [], "reference_comparisons": [],
            "reference_comparison_evidence": {},
        }
        registry = json.loads(sources["src/nipat_scientific/settings_data.json"])["workflows"]
        for name, (workflow, marker, candidate, size, mode, cap, variant) in acceptance.analysis_expected_cases().items():
            settings = None
            if candidate:
                params = {key: value["default"] for key, value in registry[workflow]["parameters"].items()}
                params[{"cpi": "min_fetal_reads", "cpin": "min_child_reads", "contamination": "include_zero"}[workflow]] = (
                    variant["include_zero"] if workflow == "contamination" else variant["minimum"])
                settings = {"schema_version": 1, "workflow": workflow, "parameters": params,
                            "constants": registry[workflow]["constants"]}
            self.report["results"].append({"name": name, "status": "passed", "inputs_unchanged": True,
                "workflow": workflow, "marker": marker, "candidate": candidate, "batch_size": size,
                "mode": mode, "max_workers": cap, "variant": variant, "rows": [{"result": "0.1"}],
                "input_sha256": {"input.tsv": "a" * 64}, "output_sha256": {"result.tsv": "b" * 64},
                "log_sha256": {"stdout.log": "c" * 64}, "summary_sha256": "d" * 64,
                "scientific_settings": settings, "settings_match": True if candidate else None,
                "worker_evidence": {"max_planned_workers": 1 if mode == "serial" else 2,
                                    "observed_peak_workers": 1, "completed_worker_tasks": size,
                                    "observed_child_pids": [] if mode == "serial" else [123, 456]} if candidate else None})
            if name.endswith("-candidate"):
                key = name.removesuffix("-candidate")
                self.report["reference_comparisons"].append(key)
                self.report["reference_comparison_evidence"][key] = {
                    "equal": True, "candidate_sha256": "d" * 64, "reference_sha256": "d" * 64}
        self.caller_parallel = None
        self.summaries = {}
        for case in self.report["results"]:
            marker, workflow, size = case["marker"], case["workflow"], case["batch_size"]
            if workflow == "cpin":
                columns = ["Trio", "Marker_type", "Analysis", "N_sites", "N_heterozygous_child_sites",
                           "N_homozygous_child", "Matching_sites", "Mismatching_sites", "Log10_CPI", "CPI",
                           "Error_constant", "Min_child_reads"]
                trios = ([f"MotherM-FatherF-ChildC_{marker}s"] if size == 1 else
                         [f"MotherM{i}-FatherF{i}-ChildC{i}_{marker}s" for i in range(1, size + 1)])
                rows = [{**dict.fromkeys(columns, "0.1"), "Trio": trio, "Marker_type": marker, "Analysis": selection}
                        for trio in trios for selection in ("heterozygous_child_sites", "all_compatible_sites")]
            elif workflow == "cpi":
                columns = ["Pair", "N_sites_mother", "N_sites_father", "Median_fetal_fraction_raw",
                           "Median_fetal_fraction_percent", "Max_logCPI", "Min_logCPI", "Median_logCPI",
                           "Mean_logCPI", "CPI_medianFF", "Error_constant"]
                pairs = ([f"MotherM-FatherF_{marker}s", f"MotherN-FatherN_{marker}s"] if size == 1 else
                         [f"MotherM{i}-FatherF{i}_{marker}s" for i in range(1, size + 1)])
                rows = [{**dict.fromkeys(columns, "0.1"), "Pair": pair} for pair in pairs]
            else:
                columns = ["individuo", "informative_sites", "mean_contamination", "sd_contamination"]
                rows = [{**dict.fromkeys(columns, "0.1"), "individuo": f"Sample{i}"} for i in range(1, size + 1)]
            case["rows"] = rows
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=columns, delimiter="," if workflow == "cpi" else "\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            raw = stream.getvalue().encode()
            filename = {"cpin": "Summary_Postnatal_CPI.txt", "cpi": "Summary_FetalFraction_CPI.csv",
                        "contamination": "contamination_summary.txt"}[workflow]
            self.summaries[case["name"] + "/output/" + filename] = raw
            case["summary_sha256"] = digest(raw)
            case["output_sha256"] = {filename: digest(raw)}
        for name, pair in self.report["reference_comparison_evidence"].items():
            for kind in ("candidate", "reference"):
                pair[kind + "_sha256"] = next(case["summary_sha256"] for case in self.report["results"]
                                             if case["name"] == name + "-" + kind)
        self.write_reports()

    def write_reports(self):
        archive = self.legacy.directory / "qualification-evidence.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            if self.caller_parallel is not None:
                handle.writestr("scientific/_temp/newpat-engine-check/caller-parallel-qualification.json",
                                json.dumps(self.caller_parallel))
            base = Path(self.record["scientific_analysis_qualification"]["report_path"]).parent
            for path, raw in self.summaries.items():
                handle.writestr((base / path).as_posix(), raw)
            for field, report in (("scientific_equivalence", self.legacy.report),
                                  ("scientific_analysis_qualification", self.report)):
                raw = json.dumps(report).encode()
                self.record[field]["report_sha256"] = digest(raw)
                handle.writestr(self.record[field]["report_path"], raw)
        self.record["qualification_evidence_sha256"] = digest(archive.read_bytes())

    def verify(self):
        return self.legacy.verify()

    def test_0895_requires_explicit_complete_zip_digest(self):
        record = copy.deepcopy(self.record)
        record.update(version="0.8.95", publication_channel="stable")
        with self.assertRaisesRegex(ValueError, "fields"):
            acceptance.validate(record, record["version"], COMMIT, record["build_run_id"])
        record["windows_zip_sha256"] = "f" * 64
        acceptance.validate(record, record["version"], COMMIT, record["build_run_id"])
        record["windows_zip_sha256"] = "invalid"
        with self.assertRaisesRegex(ValueError, "digest"):
            acceptance.validate(record, record["version"], COMMIT, record["build_run_id"])

    def test_0899_payload_is_required_in_acceptance_and_baseline_review(self):
        record = copy.deepcopy(self.record)
        record.update(version="0.8.99", publication_channel="stable",
                      windows_zip_sha256="e" * 64, reviewed_source_changes=[])
        files = {path: b"unchanged source" for path in acceptance.REQUIRED_OPERATIVE_PATHS | {"pyproject.toml"}}
        files["distribution-files.txt"] = ("\n".join(sorted(files.keys() | {"distribution-files.txt"})) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "fields"):
            acceptance.verify_baseline(record, lambda commit, path: files[path])
        record["windows_payload_sha256"] = "f" * 64
        checked = acceptance.verify_baseline(record, lambda commit, path: files[path])
        self.assertFalse(checked["candidate_windows_installation_claimed"])
        for value in ("invalid", True, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "digest"):
                acceptance.validate(dict(record, windows_payload_sha256=value),
                                    record["version"], COMMIT, record["build_run_id"])
        installer_set = {
            "version": "0.8.99", "source_commit": COMMIT,
            "installer_manifest_sha256": record["installer_manifest_sha256"],
            "scientific_archive": {"sha256": record["scientific_archive_sha256"]},
            "windows": {"sha256": record["windows_installer_sha256"]},
            "windows_zip": {"sha256": record["windows_zip_sha256"]},
            "linux": {"sha256": record["linux_installer_sha256"]},
            "linux_upgrade_check": {"sha256": record["linux_upgrade_check_sha256"]},
            **{f"macos_{arch}": {"sha256": record[f"macos_{arch}_installer_sha256"]}
               for arch in ("arm64", "x86_64")},
        }
        with self.assertRaisesRegex(ValueError, "separate Windows desktop payload"):
            acceptance.identity(installer_set)
        installer_set["windows_payload"] = {"sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "hashes do not identify"):
            acceptance.validate(record, record["version"], COMMIT,
                                record["build_run_id"], installer_set)
        installer_set["windows_payload"]["sha256"] = record["windows_payload_sha256"]
        acceptance.validate(record, record["version"], COMMIT,
                            record["build_run_id"], installer_set)

    def test_five_modules_require_separate_model_evidence_and_preserve_domain_limits(self):
        checked = self.verify()
        self.assertEqual(checked["cases_verified"], 17)
        analysis = checked["scientific_analysis_qualification"]
        self.assertEqual(analysis["executions_verified"], 86)
        self.assertEqual(analysis["batch_executions_verified"], 54)
        self.assertEqual(analysis["reference_comparisons_verified"], 16)
        self.assertFalse(analysis["domain_validation_claimed"])

    def test_gui_release_retains_all_schema7_evidence_and_explicit_testing_channel(self):
        for version in ("0.9.0", "0.9.1"):
            with self.subTest(version=version):
                self.check_gui_acceptance(version)

    def check_gui_acceptance(self, version):
        record = copy.deepcopy(self.record)
        record.update(version=version, publication_channel="testing", windows_zip_sha256="e" * 64,
                      windows_payload_sha256="f" * 64, windows_testing_sha256="d" * 64)
        acceptance.validate(record, record["version"], COMMIT, record["build_run_id"])
        for field in ("publication_channel", "windows_zip_sha256", "windows_payload_sha256",
                      "windows_testing_sha256", "macos_arm64_installer_sha256",
                      "macos_x86_64_installer_sha256", "qualification_evidence_sha256",
                      "scientific_equivalence", "scientific_analysis_qualification"):
            missing = dict(record)
            del missing[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                acceptance.validate(missing, record["version"], COMMIT, record["build_run_id"])
        for change in ({"publication_channel": "stable"}, {"schema_version": 6},
                       {"windows_testing_sha256": "invalid"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                acceptance.validate(dict(record, **change), record["version"], COMMIT, record["build_run_id"])
        # Later GUI patches keep the explicit research acceptance policy; the
        # authorized previews do not decide their maturity.
        future = dict(record, version="0.9.2", publication_channel="stable")
        del future["windows_testing_sha256"]
        acceptance.validate(future, future["version"], COMMIT, future["build_run_id"])

    def test_gui_template_cannot_authorize_untested_build_or_omit_testing_entrypoint(self):
        for version in ("0.9.0", "0.9.1"):
            with self.subTest(version=version):
                self.check_gui_template(version)

    def test_clean_install_receipt_cannot_reuse_historical_upgrade_evidence(self):
        digest = "a" * 64
        installers = dict(self.legacy.installer_set, version="0.9.99",
                          windows_zip={"sha256": "e" * 64}, windows_payload={"sha256": "f" * 64},
                          linux_upgrade_check={"sha256": "b" * 64},
                          linux_clean_install_check={"sha256": digest})
        record = acceptance.template(installers, 123)
        self.assertEqual(record["linux_clean_install_check_sha256"], digest)
        self.assertNotIn("linux_upgrade_check_sha256", record)
        del installers["linux_clean_install_check"]
        self.assertEqual(acceptance.template(installers, 123)["linux_clean_install_check_sha256"], "")

    def check_gui_template(self, version):
        installers = dict(self.legacy.installer_set, version=version,
                          windows_zip={"sha256": "e" * 64}, windows_payload={"sha256": "f" * 64})
        with self.assertRaisesRegex(ValueError, "testing entrypoint"):
            acceptance.template(installers, 123)
        installers["windows_testing"] = {"sha256": "d" * 64}
        record = acceptance.template(installers, 123)
        self.assertEqual(record["schema_version"], 7)
        self.assertEqual(record["decision"], "pending")
        self.assertIsNone(record["publication_channel"])
        self.assertEqual(record["windows_testing_sha256"], "d" * 64)
        self.assertIn("scientific_analysis_qualification", record)
        self.assertEqual(set(record["macos_validation"]), {"arm64", "x86_64"})
        with self.assertRaises(ValueError):
            acceptance.validate(record, version, COMMIT, 123, installers)

    def test_0895_zip_record_reaches_strict_baseline_verification(self):
        record = copy.deepcopy(self.record)
        record.update(version="0.8.95", publication_channel="stable",
                      windows_zip_sha256="f" * 64, reviewed_source_changes=[])
        files = {path: b"unchanged source" for path in acceptance.REQUIRED_OPERATIVE_PATHS | {"pyproject.toml"}}
        files["distribution-files.txt"] = ("\n".join(sorted(files.keys() | {"distribution-files.txt"})) + "\n").encode()
        checked = acceptance.verify_baseline(record, lambda commit, path: files[path])
        self.assertFalse(checked["candidate_windows_installation_claimed"])
        self.assertEqual(checked["reviewed_source_changes"], [])
        for change in ({"windows_zip_sha256": "invalid"}, {"unexpected_field": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                acceptance.verify_baseline(dict(record, **change), lambda commit, path: files[path])
        without_zip = dict(record)
        del without_zip["windows_zip_sha256"]
        with self.assertRaisesRegex(ValueError, "fields"):
            acceptance.verify_baseline(without_zip, lambda commit, path: files[path])
        with self.assertRaisesRegex(ValueError, "exact baseline-to-candidate"):
            acceptance.verify_baseline(record, lambda commit, path:
                b"unreviewed source" if commit == COMMIT and path == "pyproject.toml" else files[path])

    def test_legacy_schema_cannot_qualify_five_modules(self):
        self.record["schema_version"] = 6
        with self.assertRaisesRegex(ValueError, "schema 7"):
            self.verify()

    def test_new_template_preserves_pending_state_and_separate_reference_ids(self):
        installers = dict(self.legacy.installer_set, version="0.8.50")
        record = acceptance.template(installers, 123)
        self.assertEqual(record["schema_version"], 7)
        self.assertEqual(record["decision"], "pending")
        self.assertEqual(record["scientific_analysis_qualification"]["reference_source_commit"],
                         acceptance.ANALYSIS_REFERENCE_COMMIT)
        self.assertEqual(record["scientific_equivalence"]["reference_source_commit"], acceptance.R_REFERENCE_COMMIT)

    def test_cpin_review_allowed_only_in_five_module_contract(self):
        for version, wanted in (("0.8.35", False), ("0.8.50", True)):
            self.assertEqual(acceptance.reviewable_path(acceptance.CPIN_SOURCE, reliability=True,
                multiplatform=True, revised_r=True, version=version), wanted)
        self.assertFalse(acceptance.reviewable_path("scientific/vendor/NEWPAT/new.R", reliability=True,
            multiplatform=True, revised_r=True, version="0.8.50"))

    def test_only_known_development_provenance_is_reviewable_from_schema7(self):
        path = "docs/validation/0.8.50-development.json"
        for version, wanted in (("0.8.35", False), ("0.8.49", False), ("0.8.50", True)):
            self.assertEqual(acceptance.reviewable_path(path, reliability=True, multiplatform=True,
                revised_r=True, version=version), wanted)
        self.assertFalse(acceptance.reviewable_path(path, reliability=True, multiplatform=True,
            revised_r=False, version="0.8.50"))
        self.assertFalse(acceptance.reviewable_path("docs/validation/other.json", reliability=True,
            multiplatform=True, revised_r=True, version="0.8.50"))

    def test_rejects_incomplete_or_relabelled_matrix_and_sources(self):
        original = copy.deepcopy(self.report)
        mutations = [lambda r: r.update(schema_version=1), lambda r: r.update(status="failed"),
            lambda r: r.update(inputs_unchanged=False), lambda r: r.update(source_unchanged=False),
            lambda r: r.update(full_batch_matrix=False), lambda r: r["results"].pop(),
            lambda r: r["results"].append(r["results"][0]),
            lambda r: r["runtime"].update(kind="local-R"),
            lambda r: r["runtime"].update(image_id="sha256:" + "f" * 64),
            lambda r: r["runtime"]["candidate_and_helper_sha256"].pop(acceptance.CPIN_SOURCE),
            lambda r: r.update(verification_script_sha256="f" * 64),
            lambda r: r["upstream_reference"].update(upstream_commit="f" * 40),
            lambda r: r["fixture_sha256"].pop("SNP/cpin/ChildC.txt"),
            lambda r: r["fixture_sha256"].update({"SNP/cpin/ChildC.txt": "f" * 64}),
            lambda r: r["reference_comparisons"].pop(),
            lambda r: r["reference_comparison_evidence"]["SNP-cpin-0"].update(equal=False),
            lambda r: r["reference_comparison_evidence"]["SNP-cpin-0"].update(candidate_sha256="f" * 64),
        ]
        for index, mutate in enumerate(mutations):
            self.report = copy.deepcopy(original)
            mutate(self.report)
            self.write_reports()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.verify()

    def test_numeric_comparisons_reject_false_self_attested_equality(self):
        with self.assertRaisesRegex(ValueError, "numerical results differ"):
            acceptance.compare_analysis_rows([{"CPI": "9999999999999"}], [{"CPI": "-1"}])
        self.assertFalse(acceptance.same_scientific_values({"value": True}, {"value": 1}))
        self.assertTrue(acceptance.same_scientific_values({"value": 1.0}, {"value": 1}))

    def prepare_fixed_admission_report(self, version="0.9.5"):
        self.record["version"] = self.manifest["version"] = version
        self.record.update(publication_channel="testing", windows_zip_sha256="e" * 64,
                           windows_payload_sha256="f" * 64, windows_testing_sha256="d" * 64)
        helper = "tests/r_optimization/contamination/check_parallel.R"
        raw = (ROOT / helper).read_bytes()
        self.legacy.sources[COMMIT][helper] = raw
        self.legacy.report["helpers"].append({"path": helper, "sha256": digest(raw), "status": "passed"})
        for case in self.report["results"]:
            if case["candidate"] and case["workflow"] == "contamination" and case["mode"] == "auto":
                case["worker_evidence"].update(
                    max_planned_workers=1, observed_peak_workers=1, observed_child_pids=[],
                    completed_worker_tasks=case["batch_size"],
                    phase_plans=[{"label": "contamination-samples", "workers": 1,
                                  "tasks": case["batch_size"], "reason": "workload-not-observed",
                                  "worker_ceiling": case["max_workers"] or 8}])
        self.write_reports()

    def prepare_parallel_report(self):
        self.prepare_fixed_admission_report("0.9.9")
        self.record.pop("windows_testing_sha256")
        self.record["publication_channel"] = "stable"
        for case in self.report["results"]:
            if (case["candidate"] and case["workflow"] == "contamination"
                    and case["mode"] == "auto" and case["batch_size"] > 1):
                worker = case["worker_evidence"]
                workers = min(case["batch_size"], case["max_workers"] or 8)
                worker.update(max_planned_workers=workers, observed_child_pids=[111, 222])
                worker["phase_plans"][0].update(workers=workers, memory_worker_limit=8,
                    reason="fixed-capacity-task-budget", workload_model="max-loaded-coordinator-rss-x2-and-module-estimate")
        self.write_reports()

    def caller_report_fixture(self):
        acquisition = {"contigs": ["chr2", "chr10"], "strategy": "indexed-chromosomes",
                       "workers": 2, "observed_max_processes": 1, "child_pids": [17, 21],
                       "pileup_sha256": {"serial": "d"*64, "auto": "d"*64},
                       "scientific_tables_sha256": {"serial": {"calls.txt": "f"*64}, "auto": {"calls.txt": "f"*64}}}
        inner = {name: {"observed_child_pids": [], "maximum_planned_workers": 1}
                 for name in ("mother", "father", "child")}
        policies = {"serial": {"outer_admission": None, "outer_execution": None},
                    "capped": {"outer_admission": {"workers": 2, "tasks": 3,
                        "workload_model": "max-loaded-coordinator-rss-x2-and-module-estimate"},
                        "outer_execution": {"observed_child_pids": [18, 19], "simultaneous_child_workers": True,
                            "maximum_planned_workers": 2, "maximum_observed_child_workers": 2}}}
        return {"schema_version": 1, "status": "passed", "runtime_image": IMAGE,
                "acquisitions": {name: dict(copy.deepcopy(acquisition), bam_count=bams)
                                 for name, bams in (("dnp-call", 2), ("snp-call", 1))},
                "five_module_workflow": {"image": IMAGE, "status": "passed", "bam_count": 3,
                    "identical_scientific_tables": 54, "runs": {
                        k: {"status": "succeeded", "steps": 10, "snp_execution_evidence":
                            dict(v, loaded_r_execution=copy.deepcopy(inner))} for k, v in policies.items()}}}

    def test_099_requires_measured_contamination_and_exact_image_caller_proof(self):
        self.prepare_parallel_report()
        with self.assertRaisesRegex(ValueError, "Missing.*caller parallel"):
            self.verify()
        self.caller_parallel = self.caller_report_fixture()
        self.write_reports()
        checked = self.verify()
        self.assertEqual(checked["caller_parallel_qualification"]["acquisitions_verified"], ["dnp-call", "snp-call"])
        self.assertNotIn("native_r_qualification", checked)
        for version, expected in (("0.9.8", False), ("0.9.9", True), ("0.9.10", True)):
            self.assertEqual(acceptance.measured_sample_contract(version), expected)
        original = copy.deepcopy(self.report)
        for field, value in (("tasks", 1), ("workers", 1), ("memory_worker_limit", 1),
                             ("worker_ceiling", 8), ("workload_model", "not-observed")):
            self.report = copy.deepcopy(original)
            case = next(c for c in self.report["results"] if c["name"] == "SNP-contamination-batch5-auto-cap2")
            case["worker_evidence"]["phase_plans"][0][field] = value
            self.write_reports()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "measured workload"):
                self.verify()

    def test_0910_publication_requires_both_source_bound_fetal_sex_examples(self):
        report = self.caller_report_fixture()

        def verify(version="0.9.10"):
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("scientific/_temp/newpat-engine-check/caller-parallel-qualification.json",
                                json.dumps(report))
            return acceptance.verify_caller_parallel_qualification(
                archive, IMAGE, version=version, source=lambda path: (ROOT / path).read_bytes())

        self.assertNotIn("fetal_sex_examples_verified", verify("0.9.9"))
        with self.assertRaisesRegex(ValueError, "Both source-free fetal-sex examples"):
            verify()
        folder = ROOT / "tests/fixtures/fetal_sex"
        examples = {}
        for sample, call in (("Female_fetus", "F"), ("Male_fetus", "M")):
            inputs = (folder / "inputs").glob(f"{sample}_*.txt")
            outputs = (folder / "outputs" / sample).glob("*.txt")
            examples[sample] = {"call": call, "sample": sample + "_autosomes",
                                "input_sha256": {p.name: digest(p.read_bytes()) for p in inputs},
                                "output_sha256": {p.name: digest(p.read_bytes()) for p in outputs}}
        report["fetal_sex_examples"] = examples
        with self.assertRaisesRegex(ValueError, "Both published prenatal examples"):
            verify()
        folder = ROOT / "tests/fixtures/prenatal_cpi/outputs"
        report["prenatal_examples"] = {marker: {p.name: p.read_text() for p in (folder / marker).iterdir()}
                                       for marker in ("DNP", "SNP")}
        self.assertEqual(verify()["fetal_sex_examples_verified"], sorted(examples))
        filename = "MotherA1-FatherA1_SNPs_CPI_iterations.csv"
        actual = report["prenatal_examples"]["SNP"][filename]
        report["prenatal_examples"]["SNP"][filename] = actual.replace("2,", "1,", 1)
        with self.assertRaisesRegex(ValueError, "numerical results differ"):
            verify()
        report["prenatal_examples"]["SNP"][filename] = actual
        for key, value in (("call", "F"), ("sample", "Female_fetus_autosomes"),
                           ("input_sha256", examples["Female_fetus"]["input_sha256"]),
                           ("output_sha256", {})):
            report["fetal_sex_examples"] = copy.deepcopy(examples)
            report["fetal_sex_examples"]["Male_fetus"][key] = value
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, "Fetal-sex"):
                verify()
        report["fetal_sex_examples"] = copy.deepcopy(examples)
        report["fetal_sex_examples"]["Male_fetus"]["output_sha256"]["Y_sites.txt"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from the Git fixture"):
            verify()

    def test_0910_publication_requires_one_source_bound_native_report(self):
        self.prepare_parallel_report()
        self.record["version"] = self.manifest["version"] = "0.9.10"
        self.record["scientific_analysis_qualification"]["reference_source_commit"] = acceptance.CPI_REFERENCE_COMMIT
        archive = self.legacy.directory / "qualification-evidence.zip"
        with self.assertRaisesRegex(ValueError, "Missing, duplicate or oversized native R"):
            self.verify()

        def add_report(prefix):
            with zipfile.ZipFile(archive, "a") as handle:
                handle.writestr(prefix + "/newpat-native-r-check/native-r.json",
                                json.dumps({"status": "completed", "passed": False, "tests_run": 0}))
            self.record["qualification_evidence_sha256"] = digest(archive.read_bytes())

        add_report("scientific/_temp")
        with mock.patch.object(acceptance.native_evidence, "git_native_test_paths", return_value=set()) as paths:
            with self.assertRaisesRegex(ValueError, "Native R qualification did not complete successfully"):
                self.verify()
            paths.assert_called_once_with(self.record["source_commit"])
        add_report("scientific/other-run")
        with self.assertRaisesRegex(ValueError, "Missing, duplicate or oversized native R"):
            self.verify()

    def test_099_rejects_partial_parallel_execution_or_changed_scientific_outputs(self):
        self.prepare_parallel_report()
        for path, value in (
                (["runtime_image"], "sha256:"+"0"*64),
                (["acquisitions","snp-call","child_pids"], [4, 4]),
                (["acquisitions","snp-call","observed_max_processes"], 3),
                (["acquisitions","dnp-call","pileup_sha256","auto"], "e"*64),
                (["acquisitions","snp-call","scientific_tables_sha256","auto"], {}),
                (["five_module_workflow","runs","capped","snp_execution_evidence","outer_execution",
                  "simultaneous_child_workers"], False),
                (["five_module_workflow","runs","capped","snp_execution_evidence","loaded_r_execution",
                  "child","maximum_planned_workers"], 2)):
            self.caller_parallel = self.caller_report_fixture()
            item = self.caller_parallel
            for key in path[:-1]:
                item = item[key]
            item[path[-1]] = value
            self.write_reports()
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.verify()

    def test_newpat_serial_outer_admission_keeps_loaded_parallel_proof_required(self):
        self.prepare_fixed_admission_report()
        checked = self.verify()
        self.assertEqual(checked["scientific_analysis_qualification"]["executions_verified"], 86)
        self.legacy.report["helpers"] = [item for item in self.legacy.report["helpers"]
            if item["path"] != "tests/r_optimization/contamination/check_parallel.R"]
        self.write_reports()
        with self.assertRaisesRegex(ValueError, "focused comparisons"):
            self.verify()

    def test_serial_outer_admission_cannot_bypass_other_workers_or_legacy_policy(self):
        self.prepare_fixed_admission_report()
        for version in ("0.9.0", "0.9.1"):
            self.record["version"] = self.manifest["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "distinct child workers"):
                self.verify()
        self.record["version"] = self.manifest["version"] = "0.9.5"
        original = copy.deepcopy(self.report)
        for workflow in ("cpi", "cpin"):
            self.report = copy.deepcopy(original)
            case = next(c for c in self.report["results"] if c["name"] == f"SNP-{workflow}-batch5-auto-cap2")
            case["worker_evidence"].update(max_planned_workers=1, observed_child_pids=[])
            self.write_reports()
            with self.subTest(workflow=workflow), self.assertRaisesRegex(ValueError, "distinct child workers"):
                self.verify()

    def test_serial_outer_admission_rejects_missing_inconsistent_or_fabricated_plans(self):
        self.prepare_fixed_admission_report()
        original = copy.deepcopy(self.report)
        mutations = [lambda w: w.pop("phase_plans"), lambda w: w.update(phase_plans=[]),
            lambda w: w["phase_plans"].append(copy.deepcopy(w["phase_plans"][0])),
            lambda w: w["phase_plans"][0].update(label="other"),
            lambda w: w["phase_plans"][0].update(reason="requested-serial"),
            lambda w: w["phase_plans"][0].update(tasks=4),
            lambda w: w["phase_plans"][0].update(workers=True),
            lambda w: w["phase_plans"][0].update(worker_ceiling=3),
            lambda w: w["phase_plans"][0].update(worker_ceiling=True),
            lambda w: w.update(completed_worker_tasks=4),
            lambda w: w.update(observed_child_pids=[123]),
            lambda w: w.update(max_planned_workers=2)]
        for index, mutate in enumerate(mutations):
            self.report = copy.deepcopy(original)
            case = next(c for c in self.report["results"] if c["name"] == "SNP-contamination-batch5-auto-cap2")
            mutate(case["worker_evidence"])
            self.write_reports()
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "serial admission"):
                self.verify()

    def test_rejects_unverified_settings_inputs_output_and_parallel_workers(self):
        original = copy.deepcopy(self.report)
        mutations = [lambda c: c.update(status="failed"), lambda c: c.update(inputs_unchanged=False),
            lambda c: c.update(input_sha256={}), lambda c: c.update(output_sha256={}),
            lambda c: c.update(settings_match=False), lambda c: c.update(scientific_settings={}),
            lambda c: c["rows"][0].update(CPI="999999"),
            lambda c: c.update(batch_size=True),
            lambda c: c["scientific_settings"]["constants"].update({"homozygous_transmission": {"value": True}}),
            lambda c: c["variant"].update(minimum=99),
            lambda c: c["worker_evidence"].update(max_planned_workers=3),
            lambda c: c["worker_evidence"].update(observed_peak_workers=3),
            lambda c: c["worker_evidence"].update(completed_worker_tasks=0),
            lambda c: c["worker_evidence"].update(observed_child_pids=[123]),
        ]
        for index, mutate in enumerate(mutations):
            self.report = copy.deepcopy(original)
            case = next(c for c in self.report["results"] if c["name"] == "SNP-cpin-batch5-auto-cap2")
            mutate(case)
            self.write_reports()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.verify()


if __name__ == "__main__":
    unittest.main()
