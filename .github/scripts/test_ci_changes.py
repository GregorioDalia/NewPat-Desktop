import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("ci_changes", Path(__file__).with_name("ci_changes.py"))
changes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(changes)


class ScientificSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "CI selection test")
        self.git("config", "user.email", "ci-selection@example.invalid")
        self.write("README.md", "initial\n")
        self.write("scientific/panel.txt", "original input\n")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def selected(self):
        return changes.scientific_decision(self.base, self.commit(), repository=self.root)[0]

    def test_documentation_changes_keep_only_quick_checks(self):
        self.write("README.md", "clarified instructions\n")
        self.write("docs/usage.md", "usage\n")
        self.assertFalse(self.selected())

    def test_acceptance_classification_requires_only_versioned_records(self):
        path = ".github/release-acceptance/v0.8.60.json"
        self.assertTrue(changes.acceptance_only([path]))
        for paths in (None, [], [path, "src/nipat/cli.py"], [path, ".github/scripts/ci_control.py"],
                      [".github/release-acceptance/notes.json"], [path + "/other"]):
            self.assertFalse(changes.acceptance_only(paths))

    def test_acceptance_cli_outputs_and_manual_full_verification(self):
        path = ".github/release-acceptance/v0.8.60.json"
        self.write(path, "{}")
        head = self.commit()
        for event in ("pull_request", "workflow_dispatch"):
            output = self.root / (event + ".out")
            subprocess.run([sys.executable, str(Path(changes.__file__).resolve()),
                            "--base", self.base, "--head", head, "--event", event,
                            "--output", str(output)], cwd=self.root, check=True, capture_output=True)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["acceptance_only"], "true" if event == "pull_request" else "false")
            self.assertEqual(json.loads(values["acceptance_paths"]), [path] if event == "pull_request" else [])
            self.assertEqual(values["scientific"], "false" if event == "pull_request" else "true")
            self.assertEqual(values["documentation_scope"], "none")

    def selection(self, event="pull_request"):
        head = self.commit()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "selection"
            subprocess.run([sys.executable, str(Path(changes.__file__).resolve()),
                            "--base", self.base, "--head", head, "--event", event,
                            "--output", str(output)], cwd=self.root, check=True, capture_output=True)
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_guide_and_shipped_readmes_use_the_documentation_job(self):
        for path in ("docs/archive/guide.md", "docs/WORKFLOW_CONTRACT.md", "engine/README.md",
                     "scientific/vendor/NEWPAT/SNPcall/README.md", "installer/windows/zip-readme.txt",
                     "installer/windows/testing-readme.txt"):
            self.write(path, "revised guidance")
        values = self.selection()
        self.assertEqual(values["documentation_scope"], "guides")
        self.assertTrue(all(values[layer] == "false" for layer in changes.LAYERS))
        self.assertEqual(values["acceptance_only"], "false")

    def test_mixed_documents_and_code_keep_native_and_applicable_integration(self):
        self.write("docs/USER_GUIDE.md", "guide")
        self.write("engine/main.py", "updated")
        values = self.selection()
        self.assertEqual(values["documentation_scope"], "none")
        self.assertEqual(values["scientific"], "true")

    def test_changed_image_notices_with_guides_require_the_image_and_documentation(self):
        self.write("docs/GUI.md", "guide")
        self.write("THIRD_PARTY_NOTICES.md", "image notice")
        values = self.selection()
        self.assertEqual(values["documentation_scope"], "image")
        self.assertEqual(values["scientific"], "true")
        self.assertTrue(all(values[layer] == "false" for layer in ("client", "packaging", "runtime")))

    def test_mixed_records_still_verify_acceptance_without_delegating_native_checks(self):
        record = ".github/release-acceptance/v0.9.7.json"
        self.write("docs/USER_GUIDE.md", "guide")
        self.write(record, "{}")
        values = self.selection()
        self.assertEqual(values["documentation_scope"], "none")
        self.assertEqual(values["acceptance_only"], "false")
        self.assertEqual(json.loads(values["acceptance_paths"]), [record])

    def test_manually_dispatched_or_unrecognized_inputs_keep_full_ci(self):
        self.write("docs/GUI.md", "user guide")
        values = self.selection(event="workflow_dispatch")
        self.assertEqual(values["documentation_scope"], "none")
        self.assertTrue(all(values[layer] == "true" for layer in changes.LAYERS))
        for path in ("docs/validation/record.json", "new-area/README.md", "new-code/tool.py"):
            self.assertEqual(changes.layers_for_path(path), set(changes.LAYERS))
        for path in ("tests/fixtures/cpi/samples/example.md", "src/nipat/gui/web/vendor/README.md",
                     "scientific/vendor/unknown/README.md"):
            self.assertFalse(changes.is_documentation(path))
            self.assertIn("scientific", changes.layers_for_path(path))

    def test_documentation_shortcut_never_includes_scientific_image_sources(self):
        root = Path(__file__).resolve().parents[2]
        dockerfile = (root / "docker/scientific-runtime/Dockerfile").read_text()
        for line in dockerfile.splitlines():
            if line.startswith("COPY "):
                for source in line.split()[1:-1]:
                    path = root / source
                    for file in path.rglob("*") if path.is_dir() else [path]:
                        if file.is_file():
                            name = file.relative_to(root).as_posix()
                            self.assertIn("scientific", changes.layers_for_path(name), name)

    def test_scientific_validator_and_its_evidence_dependencies_request_real_execution(self):
        for path in (".github/scripts/check_native_r.py", ".github/scripts/qualification_evidence.py",
                     ".github/scripts/release_acceptance.py"):
            self.assertIn("scientific", changes.layers_for_path(path), path)

    def test_publisher_workflow_requires_packaging_without_scientific_or_runtime_checks(self):
        self.write(".github/workflows/publish-windows-release.yml", "updated publication policy\n")
        decision, _ = changes.layer_decision(self.base, self.commit(), repository=self.root)
        self.assertEqual(decision, {
            "client": False, "scientific": False, "runtime": False, "packaging": True,
        })

    def test_other_workflows_and_selection_policy_require_every_layer(self):
        for name in (
            ".github/workflows/ci.yml", ".github/workflows/windows-installer.yml",
            ".github/workflows/previously-unknown.yml", ".github/workflows/security-monitoring.yml",
            ".github/scripts/ci_changes.py", ".github/scripts/test_ci_changes.py",
        ):
            with self.subTest(path=name):
                self.write(name, "updated workflow or selection policy\n")
                head = self.commit()
                decision, _ = changes.layer_decision(self.base, head, repository=self.root)
                self.assertEqual(decision, dict.fromkeys(changes.LAYERS, True))
                self.base = head

    def test_publisher_change_cannot_hide_a_scientific_change(self):
        self.write(".github/workflows/publish-windows-release.yml", "updated publication policy\n")
        self.write("scientific/panel.txt", "changed scientific input\n")
        decision, _ = changes.layer_decision(self.base, self.commit(), repository=self.root)
        self.assertTrue(decision["scientific"])
        self.assertTrue(decision["packaging"])

    def test_deleting_scientific_input_requires_integration(self):
        (self.root / "scientific/panel.txt").unlink()
        self.assertTrue(self.selected())

    def test_renaming_scientific_input_outside_its_directory_requires_integration(self):
        self.git("mv", "scientific/panel.txt", "moved panel.txt")
        self.assertTrue(self.selected())

    def test_wrapper_runtime_and_fixture_changes_require_integration(self):
        for name in ("src/nipat/execution/runner.py", "docker/scientific-runtime/dependencies.lock.json",
                     "tests/fixtures/new sample/input.txt", "scripts/verify_input_modes.py"):
            with self.subTest(path=name):
                self.write(name, "changed\n")
                self.assertTrue(self.selected())
                self.base = self.git("rev-parse", "HEAD")

    def test_unknown_or_unavailable_history_fails_closed(self):
        head = self.base
        for base in ("", "0" * 40, "f" * 40, "--output=unexpected"):
            with self.subTest(base=base):
                self.assertTrue(changes.scientific_decision(base, head, repository=self.root)[0])

    def test_engine_package_and_its_checks_require_integration(self):
        for name in ("engine/main.py", "engine/contract.json", "tests/test_engine_package.py",
                     "tests/test_contamination_engine.py", "tests/test_bundled_runner.py",
                     "tests/test_snp_engine.py", "tests/test_input_modes.py",
                     "tests/test_dnp_engine.py", "tests/test_dnp_workflow.py",
                     "tests/test_cpi_engine.py",
                     "scripts/verify_engine_package.py", "scripts/verify_dnp_engine.py",
                     "scripts/verify_cpi_engine.py"):
            with self.subTest(path=name):
                self.write(name, "changed\n")
                self.assertTrue(self.selected())
                self.base = self.git("rev-parse", "HEAD")

    def test_runtime_and_packaging_paths_select_their_real_integration(self):
        for path in ("installer/runtime/Dockerfile", "installer/runtime/nipat-engine",
                     "installer/runtime/component.py"):
            with self.subTest(path=path):
                self.assertTrue({"runtime", "packaging"} <= changes.layers_for_path(path))
        for path in ("installer/linux/launch.py", "installer/windows/bootstrap.ps1",
                     "scripts/build_linux_installer.py", "scripts/build_windows_installer_assets.py",
                     "distribution-files.txt"):
            with self.subTest(path=path):
                self.assertIn("packaging", changes.layers_for_path(path))
        self.assertEqual(changes.layers_for_path("docs/USER_GUIDE.md"), set())

    def test_unknown_comparison_and_deleted_runtime_cover_every_required_layer(self):
        decision, _ = changes.layer_decision("", self.base, repository=self.root)
        self.assertEqual(decision, dict.fromkeys(changes.LAYERS, True))
        self.write("installer/runtime/nipat-engine", "old helper")
        self.base = self.commit()
        (self.root / "installer/runtime/nipat-engine").unlink()
        decision, _ = changes.layer_decision(self.base, self.commit(), repository=self.root)
        self.assertTrue(decision["runtime"])
        self.assertTrue(decision["packaging"])

    def test_windows_launcher_harness_and_defaults_request_client_and_package_checks(self):
        for path in ("scripts/windows/run.ps1", "scripts/acceptance/installed_suite.py", "config/defaults.json"):
            with self.subTest(path=path):
                self.assertTrue({"client", "packaging"} <= changes.layers_for_path(path))

    def test_manual_request_runs_scientific_checks_without_changes(self):
        self.assertTrue(changes.scientific_decision(self.base, self.base, force=True, repository=self.root)[0])

    def test_reviewed_desktop_inputs_cannot_expand_the_shortcut_to_other_gui_or_science(self):
        def selection(*paths, force=False):
            decision, _ = changes.select_layers(paths, force=force)
            return decision["scientific"], *changes.desktop_checks(paths, decision)

        for path in changes.PRESENTATION_FILES:
            self.assertEqual(selection(path), (False, "focused", False), path)
        for path in changes.CALLER_INTEGRATION_FILES:
            self.assertEqual(selection(path, "src/nipat/gui/web/style.css", "docs/GUI.md"),
                             (False, "focused", True), path)
        presentation = "src/nipat/gui/web/i18n.js"
        reference = "src/nipat/gui/references.py"
        self.assertEqual(selection(reference, "installer/windows/setup.iss"), (False, "standard", True))
        for path in ("src/nipat/gui/plan.py", "src/nipat/gui/new_capability.py",
                     "src/nipat/gui/jobs.py", "src/nipat/gui/admission.py",
                     "src/nipat_scientific/desktop_scheduling.py", "src/nipat_scientific/settings_data.json",
                     "src/nipat_scientific/dnp.py", "src/nipat/resources.py", "config/defaults.toml",
                     "installer/runtime/Dockerfile", "engine/main.py", ".github/workflows/ci.yml",
                     "new-area/something", ".github/scripts/verify_caller_smoke.py",
                     ".github/scripts/verify_caller_edges.py", ".github/scripts/test_verify_caller_smoke.py"):
            self.assertEqual(selection(reference, presentation, path), (True, "standard", False), path)
        self.assertEqual(selection(reference, force=True), (True, "standard", False))

    def test_pr_and_main_classify_the_entire_comparison_including_earlier_commits(self):
        self.write("src/nipat/gui/references.py", "new reference import")
        self.commit()
        self.write("src/nipat/gui/web/style.css", "new color")
        values = self.selection()
        self.assertEqual((values["desktop_scope"], values["caller_smoke"]), ("focused", "true"))
        self.write("docs/GUI.md", "guide")
        values = self.selection(event="push")
        self.assertEqual((values["desktop_scope"], values["caller_smoke"]), ("focused", "true"))
        self.write("src/nipat/gui/plan.py", "changed parameters")
        self.commit()
        self.write("src/nipat/gui/web/style.css", "another color")
        values = self.selection()
        self.assertEqual((values["scientific"], values["desktop_scope"], values["caller_smoke"]),
                         ("true", "standard", "false"))

    def test_catalog_and_plan_changes_require_real_engine_checks(self):
        for name in (
            "src/nipat_scientific/catalog_data/dnp-call.json",
            "src/nipat_scientific/catalog.py", "src/nipat_scientific/plan.py",
            "tests/test_scientific_catalog.py", "tests/test_workflow_plan.py",
        ):
            with self.subTest(path=name):
                self.write(name, "changed\n")
                self.assertTrue(self.selected())
                self.base = self.git("rev-parse", "HEAD")

    def test_new_or_renamed_tests_cannot_silently_skip_scientific_integration(self):
        # A whitelist misses future regression tests: the directory is the contract.
        for name in ("tests/test_previously_unknown_regression.py", "tests/new_area/test_workflow.py",
                     ".github/scripts/ci_control.py"):
            with self.subTest(path=name):
                self.write(name, "changed\n")
                self.assertTrue(self.selected())
                self.base = self.git("rev-parse", "HEAD")

    def test_deleting_a_test_requires_scientific_integration(self):
        self.write("tests/test_regression.py", "previous coverage\n")
        self.base = self.commit()
        (self.root / "tests/test_regression.py").unlink()
        self.assertTrue(self.selected())

    def test_r_equivalence_reference_harness_and_cases_require_scientific_integration(self):
        for name in (
            ".github/scripts/test_r_equivalence_ci.py",
            ".github/scripts/scientific_reuse.py",
            ".github/scripts/test_scientific_reuse.py",
            ".github/scripts/test_scientific_reuse_workflows.py",
            "scripts/verify_r_equivalence.py",
            "scripts/scientific_worker_evidence.py",
            "tests/test_r_equivalence.py",
            "tests/reference_r/0.8.5/manifest.json",
            "tests/reference_r/0.8.5/scientific/vendor/DNPcall/DNPcall.R",
            "tests/r_optimization/dnp/grouping.R",
            "tests/r_optimization/cpi/cases.R",
        ):
            with self.subTest(path=name):
                self.write(name, "changed\n")
                self.assertTrue(self.selected())
                self.base = self.git("rev-parse", "HEAD")

    def test_removing_a_frozen_r_reference_cannot_skip_equivalence_checks(self):
        name = "tests/reference_r/0.8.5/scientific/vendor/DNPcall/DNPcall.R"
        self.write(name, "reference\n")
        self.base = self.commit()
        (self.root / name).unlink()
        self.assertTrue(self.selected())


if __name__ == "__main__":
    unittest.main()
