"""The testing entrypoint binds exact downloads without changing stable setup."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "installer/windows"
SPEC = importlib.util.spec_from_file_location("testing_package", SOURCE / "testing_package.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class TestingPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.manifest = {"version": "0.9.10", "source_commit": "a" * 40}
        for name in ("NewPat-Setup.exe", "NewPat-0.9.10-Windows-payload.zip", "NewPat-0.9.10-Windows-complete.zip"):
            (self.output / name).write_bytes(name.encode())

    def test_english_testing_archive_names_and_manifest_use_same_generation(self):
        self.manifest["version"] = "0.9.10"
        for name in ("NewPat-0.9.10-Windows-payload.zip", "NewPat-0.9.10-Windows-complete.zip"):
            (self.output / name).write_bytes(name.encode())
        record = PACKAGE.build(SOURCE, self.output, self.manifest)
        self.assertEqual(record["file"], "NewPat-0.9.10-Testing-installer.zip")
        with zipfile.ZipFile(self.output / record["file"]) as archive:
            metadata = json.loads(archive.read("testing-release.json"))
            self.assertEqual(metadata["complete_zip"]["file"], "NewPat-0.9.10-Windows-complete.zip")

    def test_exact_downloads_and_reviewed_entrypoints_are_bound(self):
        record = PACKAGE.build(SOURCE, self.output, self.manifest)
        archive = self.output / record["file"]
        self.assertEqual(PACKAGE.verify(archive, SOURCE, self.output, self.manifest), record)
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {"README.txt", "INSTALL-NewPat-Testing.cmd",
                                                      "install-testing.ps1", "install-profile.ps1",
                                                      "install-layout.ps1", "testing-release.json"})
            data = json.loads(bundle.read("testing-release.json"))
            self.assertEqual(data["channel"], "testing")
            self.assertEqual(data["source_commit"], self.manifest["source_commit"])
            for role in ("setup", "payload", "complete_zip"):
                path = self.output / data[role]["file"]
                self.assertEqual(data[role]["sha256"], PACKAGE.digest(path))
                self.assertEqual(data[role]["size"], path.stat().st_size)

    def test_download_entrypoint_contains_its_powershell_dependencies(self):
        record = PACKAGE.build(SOURCE, self.output, self.manifest)
        with zipfile.ZipFile(self.output / record["file"]) as bundle:
            for name in (path for path in bundle.namelist() if path.endswith(".ps1")):
                source = bundle.read(name).decode("utf-8-sig")
                for dependency in re.findall(r"(?m)^\s*\. \(Join-Path \$PSScriptRoot '([^']+)'\)", source):
                    self.assertIn(dependency, bundle.namelist(), f"{name} loads {dependency}")

    def test_replaced_payload_or_source_commit_invalidates_entrypoint(self):
        record = PACKAGE.build(SOURCE, self.output, self.manifest)
        archive = self.output / record["file"]
        with self.assertRaisesRegex(ValueError, "payload identity"):
            PACKAGE.verify(archive, SOURCE, self.output, dict(self.manifest, source_commit="b" * 40))
        (self.output / "NewPat-0.9.10-Windows-payload.zip").write_bytes(b"replaced payload")
        with self.assertRaisesRegex(ValueError, "payload identity"):
            PACKAGE.verify(archive, SOURCE, self.output, self.manifest)

    def test_unexpected_archive_member_and_stable_version_are_rejected(self):
        record = PACKAGE.build(SOURCE, self.output, self.manifest)
        archive = self.output / record["file"]
        with zipfile.ZipFile(archive, "a") as bundle:
            bundle.writestr("unexpected.exe", b"unexpected")
        with self.assertRaisesRegex(ValueError, "archive contents"):
            PACKAGE.verify(archive, SOURCE, self.output, self.manifest)
        with self.assertRaises(ValueError):
            PACKAGE.filename("0.8.99")


if __name__ == "__main__":
    unittest.main()
