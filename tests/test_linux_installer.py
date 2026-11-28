"""Validate the native Linux distribution independently of a Docker daemon."""

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "linux_installer", Path(__file__).resolve().parents[1] / "scripts/build_linux_installer.py",
)
linux = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(linux)
COMMIT = "a" * 40
HAS_DPKG = shutil.which("dpkg-deb") is not None


class LinuxInstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        files = {
            "pyproject.toml": '[project]\nversion = "0.9.99"\n',
            "README.md": "Approved documentation\n",
            "LICENSE": "License fixture\n",
            "THIRD_PARTY_NOTICES.md": "Third-party notices fixture\n",
            "installer/linux/launch.py": 'print("launcher fixture")\n',
            linux.SMALL_ICON_SOURCE: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"/>\n',
            linux.ICON_SOURCE: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"/>\n',
            "installer/windows/install-profile.json": json.dumps(linux.assets.EXPECTED_INSTALLATION_PROFILE),
        }
        files["distribution-files.txt"] = "\n".join([*files, "distribution-files.txt"]) + "\n"
        for name, contents in files.items():
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        (self.project / "private.txt").write_text("Must never be packaged", encoding="utf-8")
        self.archive = self.root / "scientific.tar.gz"
        self.archive.write_bytes(gzip.compress(b"exact scientific image fixture", mtime=0))
        self.rootfs = self.root / "rootfs.tar.gz"
        self.rootfs.write_bytes(gzip.compress(b"WSL only fixture", mtime=0))
        runtime = self.project / "installer/runtime"
        runtime.mkdir()
        for name in linux.assets.component.SOURCE_FILES:
            (runtime / name).write_text(f"fixture {name}")
        self.provenance = {
            "schema_version": 2, "vendor": "newpat-desktop", "purpose": "dedicated-wsl-runtime",
            "base_image": "debian@sha256:" + "d" * 64, "apt_packages": {"libc6": "2.41"},
            "docker_engine_version": "29.0.0", "compose_version": "2.40.0",
            "source_sha256": linux.assets.component.source_inventory(runtime),
        }
        self.provenance["component_sha256"] = linux.assets.component.component_identity(self.provenance)
        self.manifest = linux.assets.make_manifest(
            self.project, source_commit=COMMIT, runtime_image="sha256:" + "b" * 64,
            rootfs=self.rootfs, scientific_image=self.archive,
            rootfs_provenance=self.provenance,
        )
        self.manifest_path = self.root / "installer-manifest.json"
        self.write_manifest(self.manifest)
        self.output = self.root / "output"
        git = patch.object(linux.bundle, "git_source", return_value={
            "available": True, "dirty": False, "commit": COMMIT,
        })
        self.git_source = git.start()
        self.addCleanup(git.stop)

    def write_manifest(self, manifest):
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def inputs(self):
        return linux.verified_inputs(self.project, self.manifest_path)

    def test_debian_versions_require_canonical_official_newpat_versions(self):
        for value in ("0.9.99", "0.10.0", "1.0.0"):
            self.assertEqual(linux.debian_version(value), value)
        for value in ("0.9.98", "../1.0.0", "1.0.0\nDepends: anything", "1.0", "1.0.0+local", "1.0.0b1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                linux.debian_version(value)

    def test_scientific_archive_is_required_but_windows_rootfs_is_not(self):
        self.rootfs.unlink()
        self.assertEqual(self.inputs()[3], self.archive)
        self.archive.unlink()
        with self.assertRaises(ValueError):
            self.inputs()

    def test_rejects_dirty_wrong_or_unavailable_source_commit(self):
        for source in ({"available": True, "dirty": True, "commit": COMMIT},
                       {"available": True, "dirty": False, "commit": "c" * 40},
                       {"available": False, "dirty": None, "commit": None}):
            self.git_source.return_value = source
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "checkout Git pulito"):
                self.inputs()

    def test_rejects_source_edits_and_additional_manifest_source(self):
        (self.project / "README.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sorgenti non corrispondono"):
            self.inputs()
        (self.project / "README.md").write_text("Approved documentation\n", encoding="utf-8")
        modified = copy.deepcopy(self.manifest)
        modified["source_sha256"]["../private.txt"] = "d" * 64
        self.write_manifest(modified)
        with self.assertRaisesRegex(ValueError, "sorgenti non corrispondono"):
            self.inputs()

    def test_rejects_foreign_channel_and_wrong_provenance(self):
        for field, value in (("installation_profile", {"channel": "stable"}),
                             ("installation_profile", {"channel": "preview-0.5"}),
                             ("rootfs_provenance", {"schema_version": 1, "vendor": "newpat-desktop", "source_commit": "e" * 40})):
            manifest = dict(self.manifest, **{field: value})
            self.write_manifest(manifest)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inputs()

    def test_rejects_other_release_families_before_packaging(self):
        for version in ("0.9.10", "0.9.98", "0.9.99rc1"):
            manifest = copy.deepcopy(self.manifest)
            manifest.update(version=version, release_tag="v" + version)
            for asset in manifest["assets"].values():
                asset["url"] = asset["url"].replace("/v0.9.99/", "/v" + version + "/")
            self.write_manifest(manifest)
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.inputs()

    def set_version(self, version):
        (self.project / "pyproject.toml").write_text(
            f'[project]\nversion = "{version}"\n', encoding="utf-8",
        )
        self.manifest = linux.assets.make_manifest(
            self.project, source_commit=COMMIT, runtime_image="sha256:" + "b" * 64,
            rootfs=self.rootfs, scientific_image=self.archive,
            rootfs_provenance=self.provenance,
        )
        self.write_manifest(self.manifest)

    def test_current_and_future_versions_require_matching_source_and_profile(self):
        for version in ("0.9.99", "0.10.0", "1.0.0"):
            with self.subTest(version=version):
                self.set_version(version)
                self.assertEqual(self.inputs()[0]["version"], version)
                (self.project / "pyproject.toml").write_text(
                    '[project]\nversion = "1.2.3"\n', encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "Versione dei sorgenti diversa"):
                    self.inputs()

    @unittest.skipUnless(HAS_DPKG, "Requires the Linux dpkg-deb tool")
    def test_next_major_build_keeps_version_and_verified_runtime(self):
        self.set_version("1.0.0")
        package = linux.build_installer(self.project, self.manifest_path, self.output)
        self.assertEqual(package.name, "newpat-desktop_1.0.0_amd64.deb")
        record = linux.verify_package(package, self.manifest_path, self.project)
        self.assertEqual(record["version"], "1.0.0")
        self.assertEqual(record["source_commit"], COMMIT)
        self.assertEqual(record["embedded_scientific_asset"]["sha256"],
                         hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(subprocess.check_output(
            ["dpkg-deb", "-f", str(package), "Version"], text=True,
        ).strip(), "1.0.0")

    def test_rejects_malformed_manifest_and_unsafe_asset_names(self):
        for value in ([], None, {"schema_version": True}, dict(self.manifest, assets=[]),
                      dict(self.manifest, version=["0.9.99"])):
            self.write_manifest(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.inputs()
        for name in ("../scientific.tar.gz", "/scientific.tar.gz", "nested/scientific.tar.gz", "scientific.tar.gz\n"):
            manifest = copy.deepcopy(self.manifest)
            manifest["assets"]["scientific_image"]["file"] = name
            self.write_manifest(manifest)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.inputs()

    def test_rejects_tampered_archive_before_creating_output(self):
        self.archive.write_bytes(gzip.compress(b"different archive", mtime=0))
        with self.assertRaisesRegex(ValueError, "Archivio scientifico diverso"):
            linux.build_installer(self.project, self.manifest_path, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_existing_output(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "deve essere nuova"):
            linux.build_installer(self.project, self.manifest_path, self.output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    @unittest.skipUnless(HAS_DPKG, "Requires the Linux dpkg-deb tool")
    def test_build_extract_and_verify_exact_single_package(self):
        self.rootfs.unlink()
        package = linux.build_installer(self.project, self.manifest_path, self.output)
        self.assertEqual(package.name, "newpat-desktop_0.9.99_amd64.deb")
        self.assertEqual({path.name for path in self.output.iterdir()}, {
            package.name, "installer-manifest.json", "linux-installer-build.json", "SHA256SUMS",
        })
        record = json.loads((self.output / linux.BUILD_RECORD).read_text())
        self.assertEqual(linux.verify_package(package, self.manifest_path, self.project), record)
        self.assertEqual(record["embedded_scientific_asset"]["sha256"], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(record["source_commit"], COMMIT)
        self.assertEqual((self.output / "installer-manifest.json").read_bytes(), self.manifest_path.read_bytes())
        extracted = self.root / "extracted"
        subprocess.run(["dpkg-deb", "-x", str(package), str(extracted)], check=True)
        app = extracted / linux.APP_PATH
        self.assertEqual(json.loads((app / "release.json").read_text())["status"], "for-domain-validation")
        self.assertEqual((app / ".distribution" / self.archive.name).read_bytes(), self.archive.read_bytes())
        self.assertFalse((app / "private.txt").exists())
        self.assertFalse((app / ".distribution" / self.rootfs.name).exists())
        self.assertEqual((extracted / "usr/bin" / linux.COMMAND).stat().st_mode & 0o777, 0o755)
        self.assertIn("Terminal=false", (extracted / "usr/share/applications/newpat-desktop.desktop").read_text())
        desktop = (extracted / "usr/share/applications/newpat-desktop.desktop").read_text()
        self.assertIn("Name=NewPat\n", desktop)
        self.assertEqual([path.name for path in (extracted / "usr/bin").iterdir()], ["newpat"])
        self.assertIn("Exec=/usr/bin/newpat --desktop\nTryExec=/usr/bin/newpat\n", desktop)
        self.assertIn(f"Icon={linux.PACKAGE}\n", desktop)
        for size, source in linux.THEME_ICONS.items():
            themed = extracted / f"usr/share/icons/hicolor/{size}/apps/{linux.PACKAGE}.svg"
            self.assertEqual(themed.read_bytes(), (self.project / source).read_bytes())
        self.assertEqual((app / linux.ICON_SOURCE).read_bytes(), (self.project / linux.ICON_SOURCE).read_bytes())
        dependencies = subprocess.check_output(["dpkg-deb", "-f", str(package), "Depends"], text=True).strip()
        self.assertEqual(dependencies, linux.DEPENDENCIES)
        self.assertEqual(linux.APP_PATH.as_posix(), "opt/newpat-desktop")
        self.assertFalse((extracted / "opt/newpat-05-preview").exists())
        self.assertFalse((extracted / "usr/bin/newpat-05-preview").exists())
        controls = subprocess.check_output(["dpkg-deb", "-f", str(package)], text=True)
        self.assertNotIn("Replaces:", controls)
        self.assertNotIn("Conflicts:", controls)

    @unittest.skipUnless(HAS_DPKG, "Requires the Linux dpkg-deb tool")
    def test_verifier_rejects_unexpected_payload_privileges_and_contents(self):
        package = linux.build_installer(self.project, self.manifest_path, self.output)
        original = package.read_bytes()
        for scenario in ("source", "extra", "permissions", "maintainer", "launcher", "symlink"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(dir=self.root) as temporary:
                stage = Path(temporary) / "stage"
                package.write_bytes(original)
                subprocess.run(["dpkg-deb", "-R", str(package), str(stage)], check=True)
                if scenario == "source":
                    (stage / linux.APP_PATH / "README.md").write_text("tampered source", encoding="utf-8")
                elif scenario == "extra":
                    (stage / linux.APP_PATH / "private.txt").write_text("unlisted", encoding="utf-8")
                elif scenario == "permissions":
                    (stage / "usr/bin" / linux.COMMAND).chmod(0o4755)
                elif scenario == "maintainer":
                    path = stage / "DEBIAN/postinst"
                    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    path.chmod(0o755)
                elif scenario == "launcher":
                    (stage / "usr/bin" / linux.COMMAND).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                else:
                    path = stage / linux.APP_PATH / "README.md"
                    path.unlink()
                    path.symlink_to("/etc/passwd")
                subprocess.run(["dpkg-deb", "--root-owner-group", "-Znone", "--build", str(stage), str(package)],
                               check=True, stdout=subprocess.DEVNULL)
                with self.assertRaises(ValueError):
                    linux.verify_package(package, self.manifest_path, self.project)

    @unittest.skipUnless(HAS_DPKG, "Requires the Linux dpkg-deb tool")
    def test_verifier_checks_without_clean_git_or_external_runtime_archive(self):
        package = linux.build_installer(self.project, self.manifest_path, self.output)
        self.archive.unlink()
        self.git_source.return_value = {"available": False, "dirty": True, "commit": None}
        linux.verify_package(package, self.manifest_path, self.project)


if __name__ == "__main__":
    unittest.main()
