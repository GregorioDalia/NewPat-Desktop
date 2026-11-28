"""A review build must bind Linux acceptance evidence to both installer inputs."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("verify_set", Path(__file__).with_name("verify_installer_set.py"))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class InstallationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest_bytes = b"reviewed shared manifest"
        self.manifest = {"version": "0.6.0", "source_commit": "a" * 40,
                         "assets": {"scientific_image": {"sha256": "b" * 64}}}
        self.package = {"sha256": "c" * 64}
        self.evidence = {
            "schema_version": 1, "distribution": "native-linux-deb",
            "platform": "ubuntu-24.04-amd64", "scenario": "prepared-ci-runner",
            "source_commit": "a" * 40,
            "installer_manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
            "package_sha256": "c" * 64, "runtime_archive_sha256": "b" * 64,
            "nonroot_uid": 1001, "resolved_runtime_image": "sha256:" + "d" * 64,
            "checks": dict.fromkeys(VERIFY.INSTALLATION_CHECKS, True),
        }

    def verify(self, evidence):
        VERIFY.verify_installation_check(evidence, self.manifest, self.manifest_bytes, self.package)

    def test_accepts_bound_nonroot_checks(self):
        self.verify(self.evidence)

    def test_0850_requires_five_scientific_workflows(self):
        self.manifest["version"] = "0.8.50"
        old = copy.deepcopy(self.evidence)
        old["checks"].update(dict.fromkeys(VERIFY.WORKFLOW_INSTALLATION_CHECKS, True))
        with self.assertRaises(ValueError):
            self.verify(old)
        updated = copy.deepcopy(old)
        updated["checks"].pop("all_four_workflows")
        updated["checks"]["all_five_workflows"] = True
        self.verify(updated)

    def test_clean_installer_requires_six_workflows_and_verified_sex_example(self):
        self.manifest["version"] = "0.9.99"
        checks = dict.fromkeys(VERIFY.installation_checks("0.9.10"), True)
        with self.assertRaisesRegex(ValueError, "required Linux installation check"):
            self.verify(dict(self.evidence, checks=checks))
        del checks["all_five_workflows"]
        checks["all_six_workflows"] = True
        self.verify(dict(self.evidence, checks=checks))
        del checks["fetal_sex_example"]
        with self.assertRaisesRegex(ValueError, "required Linux installation check"):
            self.verify(dict(self.evidence, checks=checks))

    def test_090_retains_five_workflows_and_bootstrap_evidence(self):
        self.manifest["version"] = "0.9.0"
        complete = copy.deepcopy(self.evidence)
        complete["checks"] = dict.fromkeys(VERIFY.installation_checks("0.9.0"), True)
        self.verify(complete)
        self.assertIn("all_five_workflows", complete["checks"])
        self.assertNotIn("all_four_workflows", complete["checks"])
        self.assertTrue(VERIFY.requires_windows_bootstrap("0.9.0"))
        self.assertTrue(VERIFY.requires_reliability_evidence("0.9.0"))
        self.assertTrue(VERIFY.requires_windows_bootstrap("0.8.99"))
        self.assertFalse(VERIFY.requires_windows_bootstrap("0.8.98"))

    def test_07_requires_workflow_and_preference_evidence(self):
        for version in ("0.7.0a1", "0.7.0b1", "0.7.0rc1", "0.7.0", "0.7.5"):
            self.manifest["version"] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.verify(self.evidence)
            complete = copy.deepcopy(self.evidence)
            complete["checks"].update(dict.fromkeys(VERIFY.WORKFLOW_INSTALLATION_CHECKS, True))
            self.verify(complete)
            for check in VERIFY.WORKFLOW_INSTALLATION_CHECKS:
                for value in (None, False, 1, "true"):
                    changed = copy.deepcopy(complete)
                    if value is None:
                        del changed["checks"][check]
                    else:
                        changed["checks"][check] = value
                    with self.subTest(version=version, check=check, value=value), self.assertRaises(ValueError):
                        self.verify(changed)

    def test_06_contract_does_not_change_and_unreviewed_families_are_rejected(self):
        self.verify(self.evidence)
        extra = copy.deepcopy(self.evidence)
        extra["checks"].update(dict.fromkeys(VERIFY.WORKFLOW_INSTALLATION_CHECKS, True))
        with self.assertRaises(ValueError):
            self.verify(extra)
        for version in (None, [], "0.5.0a1", "0.8.0", "1.0.0", "0.7.0+local", "0.7.0\n"):
            self.manifest["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "review contract"):
                self.verify(self.evidence)

    def test_rejects_substituted_source_package_or_archive(self):
        for key in ("source_commit", "installer_manifest_sha256", "package_sha256", "runtime_archive_sha256"):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.evidence)
                changed[key] = "0" * len(changed[key])
                with self.assertRaises(ValueError):
                    self.verify(changed)

    def test_rejects_missing_failed_or_nonboolean_checks(self):
        for check in VERIFY.INSTALLATION_CHECKS:
            for value in (None, False, 1, "true"):
                with self.subTest(check=check, value=value):
                    changed = copy.deepcopy(self.evidence)
                    if value is None:
                        del changed["checks"][check]
                    else:
                        changed["checks"][check] = value
                    with self.assertRaises(ValueError):
                        self.verify(changed)

    def test_rejects_root_and_invalid_resolved_image(self):
        for key, values in (("nonroot_uid", (0, -1, True, "1001")),
                            ("resolved_runtime_image", ("latest", "", "sha256:bad")),
                            ("schema_version", (True, "1")),
                            ("scenario", ("fresh-desktop",)),
                            ("platform", ("ubuntu-22.04-amd64",))):
            for value in values:
                with self.subTest(key=key, value=value):
                    changed = copy.deepcopy(self.evidence)
                    changed[key] = value
                    with self.assertRaises(ValueError):
                        self.verify(changed)


class DependencyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest_bytes = b"reviewed shared manifest"
        self.manifest = {"source_commit": "a" * 40, "assets": {"scientific_image": {"sha256": "b" * 64}}}
        self.package = {"sha256": "c" * 64}
        self.evidence = {
            "schema_version": 1, "distribution": "native-linux-deb",
            "platform": "ubuntu-24.04-amd64", "scenario": "clean-ubuntu-container",
            "source_commit": "a" * 40,
            "installer_manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
            "package_sha256": "c" * 64, "runtime_archive_sha256": "b" * 64,
            "base_image": "ubuntu:24.04@sha256:" + "d" * 64,
            "dependency_packages": dict.fromkeys(
                ("python3.12", "docker.io", "docker-compose-v2", "newpat-desktop"), "1.2.3"),
            "checks": dict.fromkeys(VERIFY.DEPENDENCY_CHECKS, True),
        }

    def verify(self, evidence):
        VERIFY.verify_dependency_check(evidence, self.manifest, self.manifest_bytes, self.package)

    def test_accepts_bound_clean_container_dependency_check(self):
        self.verify(self.evidence)

    def test_090_requires_installed_gtk_and_webkit_packages(self):
        self.manifest["version"] = "0.9.0"
        with self.assertRaises(ValueError):
            self.verify(self.evidence)
        complete = copy.deepcopy(self.evidence)
        gui_packages = ("python3-gi", "gir1.2-gtk-3.0", "gir1.2-webkit2-4.1")
        complete["dependency_packages"].update(dict.fromkeys(gui_packages, "1.2.3"))
        self.verify(complete)
        for package in gui_packages:
            missing = copy.deepcopy(complete)
            del missing["dependency_packages"][package]
            with self.subTest(package=package), self.assertRaises(ValueError):
                self.verify(missing)

    def test_rejects_unbound_or_misrepresented_scenarios(self):
        for key, value in (
            ("source_commit", "0" * 40), ("package_sha256", "0" * 64),
            ("installer_manifest_sha256", "0" * 64), ("runtime_archive_sha256", "0" * 64),
            ("scenario", "fresh-desktop"), ("base_image", "ubuntu:24.04"),
            ("schema_version", True), ("dependency_packages", {}),
        ):
            changed = copy.deepcopy(self.evidence)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(changed)

    def test_rejects_missing_failed_or_nonboolean_dependency_checks(self):
        for check in VERIFY.DEPENDENCY_CHECKS:
            for value in (None, False, 1, "true"):
                changed = copy.deepcopy(self.evidence)
                if value is None:
                    del changed["checks"][check]
                else:
                    changed["checks"][check] = value
                with self.subTest(check=check, value=value), self.assertRaises(ValueError):
                    self.verify(changed)


class OnlinePayloadEvidenceTests(unittest.TestCase):
    def test_only_shipped_downloader_evidence_with_exact_payload_is_accepted(self):
        manifest = {"version": "0.8.99", "source_commit": "a" * 40}
        check = {"schema_version": 1, **manifest, "package_sha256": "b" * 64,
                 "scope": "staged-bootstrap-payload", "complete_payload_verified": True,
                 "embedded_python_executed": True, "production_downloader_executed": True,
                 "wsl_execution": False, "smart_app_control": "not-performed"}
        VERIFY.verify_windows_payload_check(check, manifest, "b" * 64)
        for key, value in (
            ("schema_version", True), ("source_commit", "c" * 40), ("version", "0.8.95"),
            ("package_sha256", "c" * 64), ("production_downloader_executed", False),
            ("production_downloader_executed", 1), ("complete_payload_verified", False),
            ("embedded_python_executed", False), ("wsl_execution", True),
            ("smart_app_control", "passed"), ("scope", "live-desktop"),
        ):
            with self.subTest(field=key, value=value), self.assertRaisesRegex(ValueError, "staged-payload"):
                VERIFY.verify_windows_payload_check(dict(check, **{key: value}), manifest, "b" * 64)


class WindowsClientEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.manifest_bytes = b"reviewed shared manifest"
        self.manifest = {
            "version": "0.7.0a1", "source_commit": "a" * 40,
            "source_sha256": {"src/newpat/cli.py": "c" * 64},
        }
        self.installer_sha256 = "d" * 64
        self.launcher_sha256 = "e" * 64
        self.bundle = VERIFY.load_module(
            "newpat_review_test_distribution", VERIFY.PROJECT / "scripts/distribution_support.py",
        )
        files = dict(self.manifest["source_sha256"])
        files.update({
            "release.json": "f" * 64, "NewPat.exe": self.launcher_sha256,
            "installer/windows/EnableWsl.exe": "1" * 64,
            ".distribution/installer-manifest.json": hashlib.sha256(self.manifest_bytes).hexdigest(),
            f".distribution/{self.bundle.PYTHON_NAME}": self.bundle.PYTHON_SHA256,
        })
        self.inventory = {
            "schema_version": 1, "installation_channel": "desktop",
            "source_commit": self.manifest["source_commit"],
            "files": [{"path": path, "sha256": digest} for path, digest in files.items()],
        }
        self.inventory_bytes = json.dumps(self.inventory).encode("utf-8")
        self.evidence = {
            "schema_version": 1, "platform": "windows-amd64",
            "scenario": "staged-embedded-python-client", "version": self.manifest["version"],
            "source_commit": self.manifest["source_commit"],
            "installer_manifest_sha256": hashlib.sha256(self.manifest_bytes).hexdigest(),
            "installer_sha256": self.installer_sha256, "launcher_sha256": self.launcher_sha256,
            "application_inventory_sha256": hashlib.sha256(self.inventory_bytes).hexdigest(),
            "python_version": "3.12.10", "scientific_execution": False, "wsl_execution": False,
            "checks": dict.fromkeys(VERIFY.WINDOWS_CLIENT_CHECKS, True),
        }

    def verify(self, evidence, inventory_bytes=None):
        VERIFY.verify_windows_client_check(
            evidence, self.manifest, self.manifest_bytes,
            installer_sha256=self.installer_sha256, launcher_sha256=self.launcher_sha256,
            inventory_bytes=self.inventory_bytes if inventory_bytes is None else inventory_bytes,
        )

    def test_0899_client_binds_script_entrypoint_without_unsigned_helpers(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["version"] = "0.8.99"
        manifest["source_sha256"]["2_LAUNCH.cmd"] = "9" * 64
        inventory = copy.deepcopy(self.inventory)
        inventory["files"] = [item for item in inventory["files"]
                              if item["path"] not in {"NewPat.exe", "installer/windows/EnableWsl.exe"}]
        inventory["files"].append({"path": "2_LAUNCH.cmd", "sha256": "9" * 64})
        evidence = copy.deepcopy(self.evidence)
        evidence.update(schema_version=2, version="0.8.99", entrypoint_sha256="9" * 64)
        del evidence["launcher_sha256"]
        evidence["checks"].update(dict.fromkeys(VERIFY.FIVE_MODULE_CLIENT_CHECKS, True))

        def check(changed_inventory, changed_evidence=None):
            raw = json.dumps(changed_inventory).encode()
            current = dict(evidence if changed_evidence is None else changed_evidence,
                           application_inventory_sha256=hashlib.sha256(raw).hexdigest())
            VERIFY.verify_windows_client_check(current, manifest, self.manifest_bytes,
                installer_sha256=self.installer_sha256, entrypoint_sha256="9" * 64,
                inventory_bytes=raw)

        check(inventory)
        for helper in ("NewPat.exe", "installer/windows/EnableWsl.exe", "installer/windows/NewPatActivityNative.dll"):
            changed = copy.deepcopy(inventory)
            changed["files"].append({"path": helper, "sha256": "0" * 64})
            with self.subTest(helper=helper), self.assertRaisesRegex(ValueError, "obsolete unsigned"):
                check(changed)
        with self.assertRaisesRegex(ValueError, "evidence mismatch"):
            check(inventory, dict(evidence, entrypoint_sha256="0" * 64))
        changed = copy.deepcopy(inventory)
        changed["files"][-1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from the verified source"):
            check(changed)

    def test_0850_requires_settings_and_five_module_client_evidence(self):
        self.manifest["version"] = "0.8.50"
        self.evidence["version"] = "0.8.50"
        self.inventory["files"].append({"path": "installer/windows/NewPatActivityNative.dll", "sha256": "2" * 64})
        self.inventory_bytes = json.dumps(self.inventory).encode("utf-8")
        self.evidence["application_inventory_sha256"] = hashlib.sha256(self.inventory_bytes).hexdigest()
        with self.assertRaises(ValueError):
            self.verify(self.evidence)
        self.evidence["checks"].update(dict.fromkeys(VERIFY.FIVE_MODULE_CLIENT_CHECKS, True))
        self.verify(self.evidence)
        for name in VERIFY.FIVE_MODULE_CLIENT_CHECKS:
            changed = copy.deepcopy(self.evidence)
            changed["checks"][name] = False
            with self.subTest(check=name), self.assertRaises(ValueError):
                self.verify(changed)

    def test_accepts_exact_client_checks_bound_to_compiled_installer_and_sources(self):
        self.verify(self.evidence)

    def test_0820_requires_compiled_activity_helper_but_keeps_historical_inventory(self):
        self.manifest["version"] = self.evidence["version"] = "0.8.20"
        with self.assertRaisesRegex(ValueError, "Windows application inventory differs"):
            self.verify(self.evidence)
        self.inventory["files"].append({"path": "installer/windows/NewPatActivityNative.dll", "sha256": "7" * 64})
        self.inventory_bytes = json.dumps(self.inventory).encode()
        self.evidence["application_inventory_sha256"] = hashlib.sha256(self.inventory_bytes).hexdigest()
        self.verify(self.evidence)
        self.manifest["version"] = self.evidence["version"] = "0.8.14"
        with self.assertRaisesRegex(ValueError, "Windows application inventory differs"):
            self.verify(self.evidence)

    def test_rejects_replaced_build_identity_or_overstated_execution_scope(self):
        mutations = [
            ("schema_version", True), ("platform", "windows-arm64"),
            ("scenario", "fresh-desktop"), ("version", "0.7.0"),
            ("source_commit", "0" * 40), ("python_version", "3.13.0"),
            ("scientific_execution", True), ("wsl_execution", True),
            ("scientific_execution", 0), ("wsl_execution", 0),
            ("unreviewed_extra", True),
        ]
        mutations.extend((field, "0" * 64) for field in (
            "installer_manifest_sha256", "installer_sha256", "launcher_sha256",
            "application_inventory_sha256",
        ))
        for field, value in mutations:
            changed = copy.deepcopy(self.evidence)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.verify(changed)
        missing = copy.deepcopy(self.evidence)
        del missing["scientific_execution"]
        with self.assertRaises(ValueError):
            self.verify(missing)

    def test_rejects_missing_failed_or_nonboolean_client_checks(self):
        for check in VERIFY.WINDOWS_CLIENT_CHECKS:
            for value in (None, False, 1, "true"):
                changed = copy.deepcopy(self.evidence)
                if value is None:
                    del changed["checks"][check]
                else:
                    changed["checks"][check] = value
                with self.subTest(check=check, value=value), self.assertRaises(ValueError):
                    self.verify(changed)
        changed = copy.deepcopy(self.evidence)
        changed["checks"]["wsl_installation"] = True
        with self.assertRaises(ValueError):
            self.verify(changed)

    def test_inventory_is_verified_even_when_its_evidence_hash_is_updated(self):
        mutations = []
        for field, value in (("source_commit", "0" * 40), ("schema_version", True),
                             ("installation_channel", "preview"), ("files", {})):
            changed = copy.deepcopy(self.inventory)
            changed[field] = value
            mutations.append((field, changed))
        for path in ("src/newpat/cli.py", "NewPat.exe", ".distribution/installer-manifest.json",
                     f".distribution/{self.bundle.PYTHON_NAME}"):
            changed = copy.deepcopy(self.inventory)
            next(item for item in changed["files"] if item["path"] == path)["sha256"] = "0" * 64
            mutations.append((path, changed))
        changed = copy.deepcopy(self.inventory)
        changed["files"].pop()
        mutations.append(("missing file", changed))
        for path in ("extra.py", "src/newpat/cli.py", "SRC/NewPat/CLI.PY"):
            changed = copy.deepcopy(self.inventory)
            changed["files"].append({"path": path, "sha256": "2" * 64})
            mutations.append(("extra or ambiguous file " + path, changed))
        for label, inventory in mutations:
            inventory_bytes = json.dumps(inventory).encode("utf-8")
            evidence = copy.deepcopy(self.evidence)
            evidence["application_inventory_sha256"] = hashlib.sha256(inventory_bytes).hexdigest()
            with self.subTest(mutation=label), self.assertRaises(ValueError):
                self.verify(evidence, inventory_bytes)


class WindowsInstallerFixtureTests(unittest.TestCase):
    def test_fixture_is_bound_to_source_and_cannot_claim_production_installation(self):
        manifest = {"version": "0.8.60", "source_commit": "a" * 40,
                    "source_sha256": {"installer/windows/NewPat.iss": "b" * 64}}
        evidence = {
            "schema_version": 1, "scenario": "compiled-installer-fixture-on-server-2022",
            "source_commit": "a" * 40, "source_definition_sha256": "b" * 64,
            "fixture_definition_sha256": "c" * 64, "uninstaller_sha256": "d" * 64,
            "status": "passed", "production_setup_executed": False, "wsl_execution": False,
            "smart_app_control": "not-performed",
            "substitutions": ["Windows workstation/elevation setup gate", "uninstaller elevation gate",
                              "synthetic runtime bootstrap and payload"],
            "checks": dict.fromkeys(("installed_0.0.1", "installed_0.0.2", "upgrade_backup",
                                    "silent_removal_preserves_data"), True),
        }
        VERIFY.verify_windows_installer_fixture(evidence, manifest)
        candidate = dict(manifest, version="0.8.70")
        with self.assertRaisesRegex(ValueError, "fixture is incomplete"):
            VERIFY.verify_windows_installer_fixture(evidence, candidate)
        VERIFY.verify_windows_installer_fixture(
            dict(evidence, checks=dict(evidence["checks"], reboot_exit_code=True)), candidate,
        )
        for field, replacement in (("source_commit", "e" * 40), ("source_definition_sha256", "f" * 64),
                                   ("production_setup_executed", True), ("wsl_execution", True),
                                   ("smart_app_control", "passed"), ("status", "failed"),
                                   ("checks", {"installed_0.0.1": True}), ("substitutions", [])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                VERIFY.verify_windows_installer_fixture({**evidence, field: replacement}, manifest)


class FrozenInstallerFixtureTests(unittest.TestCase):
    def test_099_requires_one_frozen_setup_and_explicit_fixture_substitutions(self):
        manifest = {"version": "0.8.99", "source_commit": "a" * 40,
                    "source_sha256": {"installer/windows/NewPat.iss": "b" * 64}}
        evidence = {
            "schema_version": 1, "scenario": "compiled-installer-fixture-on-server-2022",
            "source_commit": "a" * 40, "source_definition_sha256": "b" * 64,
            "fixture_definition_sha256": "c" * 64, "uninstaller_sha256": "d" * 64,
            "status": "passed", "production_setup_executed": False, "wsl_execution": False,
            "smart_app_control": "not-performed",
            "substitutions": ["Windows workstation/elevation setup gate", "uninstaller elevation gate",
                              "synthetic runtime bootstrap and payload", "host Python interpreter for fixture"],
            "checks": dict.fromkeys(("installed_0.9.99", "installed_0.9.100", "upgrade_backup",
                "reboot_exit_code", "silent_removal_preserves_data", "frozen_setup_reused",
                "bootstrap_marker", "display_version_matches_payload", "resume_archives_cached"), True),
        }
        VERIFY.verify_windows_installer_fixture(evidence, manifest)
        for key in evidence["checks"]:
            for value in (None, False, 1):
                changed = copy.deepcopy(evidence)
                if value is None:
                    del changed["checks"][key]
                else:
                    changed["checks"][key] = value
                with self.subTest(check=key, value=value), self.assertRaisesRegex(ValueError, "fixture is incomplete"):
                    VERIFY.verify_windows_installer_fixture(changed, manifest)
        changed = copy.deepcopy(evidence)
        changed["substitutions"].pop()
        with self.assertRaisesRegex(ValueError, "substitutions"):
            VERIFY.verify_windows_installer_fixture(changed, manifest)
        with self.assertRaises(ValueError):
            VERIFY.verify_windows_installer_fixture(evidence, dict(manifest, version="0.8.95"))


class VersionedInstallerSetTests(unittest.TestCase):
    def test_historical_package_set_cannot_qualify_as_a_clean_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets, linux = root / "assets", root / "linux"
            for folder in (assets, linux):
                folder.mkdir()
                (folder / "installer-manifest.json").write_text("{}")
            publisher = SimpleNamespace(prepare_assets=lambda *_: {"version": "0.9.10"})
            with patch.object(VERIFY, "load_module", return_value=publisher), self.assertRaisesRegex(
                    ValueError, "requires a clean NewPat release"):
                VERIFY.verify_set(root / "windows", linux, assets, root / "result", "a" * 40)
            self.assertFalse((root / "result").exists())


if __name__ == "__main__":
    unittest.main()
