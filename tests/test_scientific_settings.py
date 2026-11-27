"""Scientific overrides are validated, reproducible and identical in Python/R."""
from contextlib import redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from newpat_scientific.errors import ValidationError
from newpat_scientific.settings import (
    REGISTRY, defaults, describe_settings, normalize_settings, samtools_options,
    settings_context, settings_from_environment,
)
from newpat_scientific.snp import prepare_snp


def r_jsonlite_available():
    executable = shutil.which("Rscript")
    if executable is None:
        return False
    try:
        result = subprocess.run([executable, "-e",
            'quit(status=if (requireNamespace("jsonlite", quietly=TRUE)) 0L else 1L)'],
            capture_output=True, timeout=20)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


R_JSONLITE_AVAILABLE = r_jsonlite_available()


class ScientificSettingsTests(unittest.TestCase):
    def test_registry_has_all_modules_and_readable_definitions(self):
        modules = describe_settings()
        self.assertEqual(set(modules), {"dnp-call", "snp-call", "contamination", "cpi", "cpin", "fetal-sex"})
        for workflow, schema in modules.items():
            with self.subTest(workflow=workflow):
                expected = defaults(workflow)
                if workflow in {"cpi", "fetal-sex"}:
                    expected["min_fetal_reads"] = 2
                self.assertEqual(normalize_settings(workflow), expected)
                self.assertTrue(schema["constants"])
                for definition in schema["parameters"].values():
                    self.assertTrue(definition["description"])
                    self.assertIn("type", definition)
                    self.assertIn("unit", definition)
        modules["cpi"]["parameters"]["min_fetal_reads"]["default"] = 999
        self.assertIsNone(defaults("cpi")["min_fetal_reads"])

    def test_fetal_sex_read_filters_and_classification_bounds(self):
        self.assertEqual(normalize_settings("fetal-sex")["min_fetal_reads"], 2)
        percent_only = normalize_settings("fetal-sex", {"min_fetal_percent": 3})
        self.assertIsNone(percent_only["min_fetal_reads"])
        both = normalize_settings("fetal-sex", {"min_fetal_reads": 1, "min_fetal_percent": 3})
        self.assertEqual((both["min_fetal_reads"], both["min_fetal_percent"]), (1, 3))
        for invalid in ({"min_fetal_reads": 0}, {"min_fetal_percent": 0}, {"min_fetal_percent": 101},
                        {"maternal_hom_threshold": .5}, {"max_other_fraction": 1.1},
                        {"include_zero_coverage_y": 0}, {"a_threshold": 0}, {"c_male_min": .1},
                        {"b_female_max": 1}, {"b_male_min": float("nan")}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                normalize_settings("fetal-sex", invalid)

    def test_invalid_types_limits_and_cross_parameter_constraints_are_rejected(self):
        for workflow, override in (
            ("cpin", {"min_coverage": True}), ("cpin", {"min_coverage": 2.0}),
            ("cpin", {"min_coverage": 0}), ("cpin", {"include_het_hom": "FALSE"}),
            ("cpin", {f"include_{pair}": False for pair in ("hom_hom", "hom_het", "het_hom", "het_het")}),
            ("cpi", {"min_fetal_percent": 0}), ("cpi", {"min_fetal_percent": 100.0001}),
            ("cpi", {"min_fetal_percent": True}), ("cpi", {"min_fetal_reads": 0}),
            ("cpi", {"min_coverage": 0}), ("cpi", {"min_coverage": 1.5}),
            ("cpi", {"include_homozygous_child": "FALSE"}),
            ("cpi", {"err_const_dnp": 0}), ("cpi", {"err_const_snp": math.inf}),
            ("snp-call", {"other_fraction_max": math.nan}),
            ("dnp-call", {"baq": 1}), ("dnp-call", {"baq": False, "redo_baq": True}),
            ("dnp-call", {"min_base_quality": -1}), ("dnp-call", {"max_depth": 2**100}),
            ("cpi", {"heterozygous_min": .05}), ("cpi", {"heterozygous_max": .95}),
            ("cpin", {"log_cpi_lower": 5}), ("contamination", {"homozygous_ref_min": .05}),
            ("contamination", {"include_zero": "false"}), ("snp-call", {"typo": 1}),
        ):
            with self.subTest(workflow=workflow, override=override), self.assertRaises(ValidationError):
                normalize_settings(workflow, override)
        for invalid in ([], "x", 12):
            with self.assertRaises(ValidationError):
                normalize_settings("cpin", invalid)
        with self.assertRaises(ValidationError):
            describe_settings([])

    def test_effective_settings_are_saved_and_environment_restored_on_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "test"):
                with settings_context("cpin", {"min_coverage": 5}, root / "outer") as value:
                    saved = json.loads((root / "outer/effective-scientific-settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved["parameters"], value)
                    self.assertEqual(saved["constants"], describe_settings("cpin")["constants"])
                    self.assertEqual(settings_from_environment("cpin")["min_coverage"], 5)
                    with self.assertRaises(ValidationError):
                        settings_from_environment("cpi")
                    outer_path = os.environ["NIPAT_SCIENTIFIC_SETTINGS"]
                    with settings_context("cpi", {}, root / "inner"):
                        self.assertEqual(settings_from_environment("cpi"), normalize_settings("cpi"))
                    self.assertEqual(os.environ["NIPAT_SCIENTIFIC_SETTINGS"], outer_path)
                    raise RuntimeError("test")
            self.assertNotIn("NIPAT_SCIENTIFIC_SETTINGS", os.environ)
            with self.assertRaises(ValidationError), settings_context("cpi", {"err_const_snp": 0}, root / "bad"):
                pass
            self.assertFalse((root / "bad").exists())

    def test_prenatal_active_filters_and_conditional_fallback(self):
        for supplied, effective in (({}, (2, None)), ({"min_fetal_reads": None}, (2, None)),
                ({"min_fetal_reads": 3}, (3, None)), ({"min_fetal_percent": 100}, (None, 100)),
                ({"min_fetal_percent": 2.5, "min_fetal_reads": 1}, (1, 2.5))):
            with self.subTest(supplied=supplied):
                values = normalize_settings("cpi", supplied)
                self.assertEqual((values["min_fetal_reads"], values["min_fetal_percent"]), effective)
                self.assertEqual(normalize_settings("cpi", values), values)

    def test_samtools_default_and_custom_flags(self):
        for caller in ("dnp-call", "snp-call"):
            self.assertEqual(normalize_settings(caller, {})["max_depth"], 2147483647)
            for depth, flag in ((2147483647, "0"), (0, "0"), (8000, "8000"), (1, "1")):
                with self.subTest(caller=caller, depth=depth):
                    self.assertEqual(samtools_options(caller, {"max_depth": depth}), ["-d", flag])
            self.assertEqual(samtools_options(caller), ["-d", "0"])
        values = {"max_depth": 12000, "min_base_quality": 20, "min_mapping_quality": 10,
                  "mapping_quality_adjustment": 50, "excluded_flags": 4, "baq": False,
                  "count_overlaps": True, "include_orphans": True}
        self.assertEqual(samtools_options("dnp-call", values),
                         ["-d", "12000", "-Q", "20", "-q", "10", "-C", "50", "--ff", "4", "-B", "-x", "-A"])
        self.assertEqual(samtools_options("snp-call", {"redo_baq": True}), ["-d", "0", "-E"])

    def test_reused_context_preserves_prior_provenance_and_rejects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            with settings_context("cpin", {"min_coverage": 5}, work):
                target = work / "effective-scientific-settings.json"
                original, timestamp = target.read_bytes(), target.stat().st_mtime_ns
                with settings_context("cpin", {"min_coverage": 5}, work):
                    self.assertEqual(target.stat().st_mtime_ns, timestamp)
                with self.assertRaises(ValidationError), settings_context("cpin", {}, work):
                    pass
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(target.stat().st_mtime_ns, timestamp)
                self.assertEqual(list(work.glob(".settings-*")), [])
            linked = Path(directory) / "linked"
            linked.symlink_to(work, target_is_directory=True)
            with self.assertRaises(ValidationError), settings_context("cpin", {}, linked):
                pass

    def test_saved_settings_do_not_accept_boolean_numeric_aliases_or_partial_documents(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            work = Path(directory) / "work"
            with settings_context("cpi", {"min_fetal_reads": 1}, work):
                target = work / "effective-scientific-settings.json"
                original = target.read_text(encoding="utf-8")
            for mutation in (lambda doc: doc.update(schema_version=True),
                             lambda doc: doc["parameters"].update(min_fetal_reads=True),
                             lambda doc: doc["parameters"].pop("min_fetal_reads"),
                             lambda doc: doc["constants"]["homozygous_transmission"].update(value=True)):
                document = json.loads(original)
                mutation(document)
                target.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValidationError), settings_context("cpi", {"min_fetal_reads": 1}, work):
                    pass
                with patch.dict(os.environ, {"NIPAT_SCIENTIFIC_SETTINGS": str(target)}):
                    with self.assertRaises(ValidationError):
                        settings_from_environment("cpi")
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), document)

    def test_existing_pileup_warns_about_unapplied_acquisition_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel = root / "panel.txt"
            panel.write_text("chr\tpos\tref\talt\nchr1\t100\tA\tG\n")
            pileup = root / "pileup.txt"
            pileup.write_text("chr1\t100\tA\t1\t.\tI\tread1\n")
            request = {"schema_version": 1, "workflow": "snp-call", "mode": "pileup",
                       "panel": str(panel), "bam": None, "pileup": str(pileup), "reference": None,
                       "work_dir": str(root / "work"), "out_dir": str(root / "out"),
                       "scientific_settings": {"min_base_quality": 25, "other_fraction_max": .2}}
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(prepare_snp(request).preparation_command)
            warning = json.loads((root / "work/input-validation.json").read_text(encoding="utf-8"))["warnings"][0]
            self.assertEqual(warning["code"], "input.existing_pileup_acquisition_settings")
            self.assertIn("min_base_quality", warning["message"])
            self.assertNotIn("other_fraction_max", warning["message"])

    @unittest.skipUnless(R_JSONLITE_AVAILABLE, "R runtime with jsonlite not available on this host")
    def test_r_and_python_share_defaults_and_custom_settings(self):
        helper = REGISTRY.with_name("settings.R")
        expression = ('args <- commandArgs(TRUE); source(args[[1]]); '
                      'cat(jsonlite::toJSON(nipat_settings(args[[2]]), auto_unbox=TRUE, digits=17, null="null"))')
        with tempfile.TemporaryDirectory() as directory:
            for workflow in describe_settings():
                override = {"other_fraction_max": .25}
                if workflow == "fetal-sex":
                    override = {"max_other_fraction": .25, "include_zero_coverage_y": False}
                if workflow == "cpi":
                    override.update(min_coverage=12, include_homozygous_child=True)
                if workflow == "cpin":
                    override.update(min_coverage=7, include_het_hom=False)
                with self.subTest(workflow=workflow), settings_context(workflow, override, Path(directory) / workflow):
                    result = subprocess.run(["Rscript", "-e", expression, str(helper), workflow],
                                            capture_output=True, text=True, check=True)
                    self.assertEqual(json.loads(result.stdout), normalize_settings(workflow, override))

    @unittest.skipUnless(R_JSONLITE_AVAILABLE, "R runtime with jsonlite not available on this host")
    def test_r_native_sidecar_records_final_overrides_without_replacing_prior_values(self):
        helper = REGISTRY.with_name("settings.R")
        expression = ('args <- commandArgs(TRUE); source(args[[1]]); cfg <- nipat_settings("cpi"); '
                      'cfg$min_fetal_reads <- 7L; nipat_write_settings("cpi", cfg, args[[2]]); '
                      'nipat_write_settings("cpi", cfg, args[[2]]); cfg$min_fetal_reads <- 8L; '
                      'stopifnot(inherits(try(nipat_write_settings("cpi", cfg, args[[2]]), silent=TRUE), "try-error"))')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with settings_context("cpi", {}, root / "work"):
                subprocess.run(["Rscript", "-e", expression, str(helper), str(root / "output")],
                               capture_output=True, text=True, check=True)
            original = json.loads((root / "work/effective-scientific-settings.json").read_text(encoding="utf-8"))
            native = json.loads((root / "output/scientific-settings.json").read_text(encoding="utf-8"))
            self.assertEqual(original["parameters"]["min_fetal_reads"], 2)
            self.assertEqual(native["parameters"]["min_fetal_reads"], 7)
            self.assertEqual(native["constants"], original["constants"])

    @unittest.skipUnless(R_JSONLITE_AVAILABLE, "R runtime with jsonlite not available on this host")
    def test_r_native_sidecar_does_not_ignore_changed_parameter_names(self):
        helper = REGISTRY.with_name("settings.R")
        expression = ('args <- commandArgs(TRUE); source(args[[1]]); cfg <- nipat_settings("cpi"); '
                      'path <- nipat_write_settings("cpi", cfg, args[[2]]); '
                      'saved <- jsonlite::fromJSON(path, simplifyVector=FALSE); '
                      'names(saved$parameters)[names(saved$parameters)=="min_fetal_reads"] <- "renamed"; '
                      'jsonlite::write_json(saved, path, auto_unbox=TRUE, digits=NA); '
                      'stopifnot(inherits(try(nipat_write_settings("cpi", cfg, args[[2]]), silent=TRUE), "try-error"))')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with settings_context("cpi", {}, root / "work"):
                subprocess.run(["Rscript", "-e", expression, str(helper), str(root / "output")],
                               capture_output=True, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
