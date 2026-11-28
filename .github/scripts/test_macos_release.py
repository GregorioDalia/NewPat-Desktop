import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import macos_trial

SPEC = importlib.util.spec_from_file_location("macos_release", Path(__file__).with_name("macos_release.py"))
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def native_fixture(root, architecture, manifest):
    directory = root / architecture
    directory.mkdir()
    name = f"NewPat-{manifest['version']}-macos-{architecture}.pkg"
    package = directory / name
    package.write_bytes(b"verified native package fixture " + architecture.encode())
    common = {
        "schema_version": 1, "platform": "darwin", "architecture": architecture,
        "version": manifest["version"], "source_commit": manifest["source_commit"],
        "package_sha256": release.digest(package),
        "scientific_asset_sha256": manifest["assets"]["scientific_image"]["sha256"],
        "runtime_image": manifest["runtime_image"], "runtime_vm_qualified": False,
    }
    report = dict(common, verified=True, checks=sorted(release.CHECKS), not_tested=sorted(release.NOT_TESTED))
    build = dict(common, distribution="self-contained-macos-lima", package=name, package_size=package.stat().st_size,
                 manual_acceptance=False, signing="ad-hoc-app; unsigned-installer; not-notarized",
                 payload_inventory={"Contents/Info.plist": {"sha256": "f" * 64}})
    (directory / "macos-package-verification.json").write_text(json.dumps(report))
    (directory / "macos-installer-build.json").write_text(json.dumps(build))
    return directory


class MacosReleaseTests(unittest.TestCase):
    def test_final_trial_binds_the_archived_bytes_commit_and_clickable_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            package = folder / macos_trial.PACKAGE
            package.write_bytes(b"reviewed arm64 package")
            commit = "a" * 40
            sha = release.digest(package)
            record = {"version": "0.9.99", "source_commit": commit, "publication_authorized": False,
                      "macos_arm64": {"file": package.name, "size": package.stat().st_size, "sha256": sha}}
            evidence = folder / "installer-set-check.json"
            evidence.write_text(json.dumps(record))
            output = folder / "trial.zip"
            # Model a checkout without an executable bit while leaving tracked
            # sources untouched. A Windows checkout has the same limitation.
            inputs = {macos_trial.LAUNCHER: "installer/macos/" + macos_trial.LAUNCHER,
                      "mini_suite_macos.py": "scripts/mini_suite_macos.py",
                      "LEGGIMI.txt": "docs/MINI_SUITE_MAC.md"}
            checkout = folder / "checkout"
            for source in inputs.values():
                destination = checkout / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(macos_trial.PROJECT / source, destination)
                destination.chmod(0o644)
            with patch.object(macos_trial, "PROJECT", checkout):
                macos_trial.build_kit(evidence, folder, commit, output)
            with zipfile.ZipFile(output) as kit:
                self.assertEqual(set(kit.namelist()), {package.name, macos_trial.LAUNCHER, "LEGGIMI.txt",
                                                       "mini_suite_macos.py", "source-commit", "SHA256SUMS"})
                self.assertEqual(kit.read(package.name), package.read_bytes())
                self.assertEqual(kit.read("source-commit").decode(), commit + "\n")
                self.assertEqual(kit.read("SHA256SUMS").decode(), f"{sha}  {package.name}\n")
                for name, source in inputs.items():
                    self.assertEqual(kit.read(name), (checkout / source).read_bytes())
                for entry in kit.infolist():
                    mode = 0o755 if entry.filename == macos_trial.LAUNCHER else 0o644
                    self.assertEqual(entry.create_system, 3)
                    self.assertEqual(entry.external_attr >> 16, stat.S_IFREG | mode)
            output.unlink()
            with self.assertRaisesRegex(ValueError, "exact source"):
                macos_trial.build_kit(evidence, folder, "b" * 40, output)
            package.write_bytes(b"X" * package.stat().st_size)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                macos_trial.build_kit(evidence, folder, commit, output)
            self.assertFalse(output.exists())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {"version": "0.8.2", "source_commit": "a" * 40,
                         "installation_profile": {"channel": "desktop"}, "runtime_image": "sha256:" + "b" * 64,
                         "assets": {"scientific_image": {"file": "scientific.tar.gz", "sha256": "c" * 64, "size": 100}}}
        self.pair = {"version": "0.8.2", "source_commit": "a" * 40,
                     "scientific_archive": dict(self.manifest["assets"]["scientific_image"]),
                     "windows": {"sha256": "d" * 64}, "linux": {"sha256": "e" * 64}}
        self.directories = {arch: native_fixture(self.root, arch, self.manifest) for arch in release.ARCHITECTURES}

    def extend(self):
        return release.extend_installer_set(self.pair, self.directories, self.manifest)

    def edit_report(self, name, value):
        path = self.directories["arm64"] / "macos-package-verification.json"
        report = json.loads(path.read_text())
        report[name] = value
        path.write_text(json.dumps(report))

    def test_native_release_binds_arm_to_its_own_image_and_the_common_sources(self):
        common = dict(self.manifest, version="0.9.99", release_tag="v0.9.99", source_sha256={"engine.py": "1" * 64})
        arm = dict(common, schema_version=1, scientific_platform="linux/arm64", runtime_image="sha256:" + "e" * 64,
                   engine_description_sha256="3" * 64,
                   assets={"scientific_image": {"file": "newpat-scientific-0.9.99-arm64.tar.gz", "sha256": "d" * 64, "size": 95}})
        root = self.root / "new"
        root.mkdir()
        directories = {}
        for arch, science in (("arm64", arm), ("x86_64", common)):
            folder = directories[arch] = native_fixture(root, arch, science)
            for filename in ("macos-installer-build.json", "macos-package-verification.json"):
                path = folder / filename
                record = json.loads(path.read_bytes())
                record["scientific_platform"] = "linux/arm64" if arch == "arm64" else "linux/amd64"
                if "checks" in record:
                    record["checks"] += ["docker-archive-architecture", "rosetta-disabled"]
                    record["checks"].append("newpat-clean-install-identity")
                path.write_text(json.dumps(record))
        identity = directories["arm64"] / "arm64-scientific.json"
        identity.write_text(json.dumps(arm))
        pair = dict(self.pair, version="0.9.99")
        result = release.extend_installer_set(pair, directories, common)
        self.assertEqual(result["macos_arm64"]["scientific_identity_sha256"], release.digest(identity))
        for changes in ({"runtime_image": common["runtime_image"]}, {"source_sha256": {}},
                        {"scientific_platform": "linux/amd64"}, {"source_commit": "f" * 40}):
            identity.write_text(json.dumps(dict(arm, **changes)))
            with self.assertRaisesRegex(ValueError, "ARM64"):
                release.extend_installer_set(pair, directories, common)

    def test_exact_native_packages_extend_pair_without_claiming_vm_execution(self):
        result = self.extend()
        for arch in release.ARCHITECTURES:
            record = result[f"macos_{arch}"]
            self.assertFalse(record["runtime_vm_qualified"])
            self.assertEqual(record["sha256"], release.digest(self.directories[arch] / record["file"]))
            self.assertEqual(record["verification_sha256"], release.digest(self.directories[arch] / "macos-package-verification.json"))
        self.assertNotIn("macos_arm64", self.pair)

    def test_both_architectures_and_common_archive_are_required(self):
        for key in ("source_commit", "version", "scientific_archive"):
            changed = dict(self.pair, **{key: "mismatch"})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "archives differ"):
                release.extend_installer_set(changed, self.directories, self.manifest)
        del self.directories["x86_64"]
        with self.assertRaisesRegex(ValueError, "Both macOS"):
            self.extend()

    def test_changed_package_or_unbound_report_cannot_be_published(self):
        for key, value in (("source_commit", "f" * 40), ("scientific_asset_sha256", "f" * 64),
                           ("architecture", "x86_64"), ("verified", 1), ("runtime_vm_qualified", True)):
            path = self.directories["arm64"] / "macos-package-verification.json"
            previous = path.read_bytes()
            self.edit_report(key, value)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "not bound"):
                self.extend()
            path.write_bytes(previous)
        package = next(self.directories["arm64"].glob("*.pkg"))
        package.write_bytes(b"replaced package")
        with self.assertRaisesRegex(ValueError, "not bound"):
            self.extend()

    def test_native_check_gaps_and_unsupported_vm_claims_are_rejected(self):
        self.edit_report("checks", sorted(release.CHECKS - {"native-python"}))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.extend()
        self.edit_report("checks", sorted(release.CHECKS))
        self.edit_report("not_tested", [])
        with self.assertRaisesRegex(ValueError, "misrepresent"):
            self.extend()

    def test_build_record_substitution_and_symlinks_are_rejected(self):
        path = self.directories["arm64"] / "macos-installer-build.json"
        record = json.loads(path.read_text())
        record["package_size"] += 1
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "build record differs"):
            self.extend()
        package = next(self.directories["arm64"].glob("*.pkg"))
        target = self.root / "elsewhere.pkg"
        package.rename(target)
        package.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.extend()


if __name__ == "__main__":
    unittest.main()
