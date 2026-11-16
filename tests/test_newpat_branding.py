"""New public identity must preserve data roots and old update contracts."""
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from nipat.branding import PRODUCT_NAME, canonical_asset_name
from nipat.cli import build_parser
from nipat.distribution import is_experimental_version, WINDOWS_DIRECTORY, UNIX_DIRECTORY
from nipat.updates import UpdateAsset, UpdateError, WEB, _public_asset, _validated_asset

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("newpat_migrate", ROOT / "installer/macos/migrate_legacy.py")
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class NewPatBrandingTests(unittest.TestCase):
    def test_public_name_and_stable_technical_identity(self):
        self.assertEqual(PRODUCT_NAME, "NewPat")
        self.assertEqual(build_parser().prog, "newpat")
        self.assertEqual((WINDOWS_DIRECTORY, UNIX_DIRECTORY), ("NIPAT-Desktop", "nipat-desktop"))
        self.assertTrue(is_experimental_version("0.9.5"))
        self.assertTrue(is_experimental_version("0.9.5rc1"))
        self.assertFalse(is_experimental_version("0.8.99"))

    def test_aliases_only_change_known_filenames(self):
        self.assertEqual(canonical_asset_name("NIPAT-0.9.5-macos-arm64.pkg"), "NewPat-0.9.5-macos-arm64.pkg")
        self.assertEqual(canonical_asset_name("nipat-desktop_0.9.5_amd64.deb"), "newpat-desktop_0.9.5_amd64.deb")
        self.assertEqual(canonical_asset_name("/data/NIPAT-old.bam"), "/data/NIPAT-old.bam")

    def test_public_alias_requires_identical_published_bytes(self):
        old = UpdateAsset("windows-x86_64", "NIPAT-Setup.exe", 100, "a" * 64,
                          WEB + "/releases/download/v0.9.5/NIPAT-Setup.exe")
        alias = {"name": "NewPat-Setup.exe", "state": "uploaded", "size": 100,
                 "digest": "sha256:" + "a" * 64,
                 "browser_download_url": WEB + "/releases/download/v0.9.5/NewPat-Setup.exe"}
        selected = _public_asset(old, "0.9.5", [alias])
        self.assertEqual(selected.name, "NewPat-Setup.exe")
        self.assertEqual(selected.sha256, old.sha256)
        for key, value in (("digest", "sha256:" + "b" * 64), ("size", 101), ("state", "new")):
            with self.subTest(key=key), self.assertRaises(UpdateError):
                _public_asset(old, "0.9.5", [{**alias, key: value}])
        with self.assertRaises(UpdateError):
            _public_asset(old, "0.9.5", [alias, alias])
        self.assertEqual(_public_asset(old, "0.9.5", []), old)

    def test_download_validation_accepts_canonical_and_legacy_names(self):
        for name in ("NewPat-Setup.exe", "NIPAT-Setup.exe"):
            data = {"platform": "windows-x86_64", "name": name, "size": 100,
                    "sha256": "a" * 64, "url": WEB + "/releases/download/v0.9.5/" + name}
            self.assertEqual(_validated_asset(data, "0.9.5", "v0.9.5").name, name)
        with self.assertRaises(UpdateError):
            _validated_asset({**data, "name": "Other-Setup.exe"}, "0.9.5", "v0.9.5")


class MacLegacyMigrationTests(unittest.TestCase):
    def bundle(self, path, version):
        source = path / "Contents/Resources/app"
        (source / ".distribution").mkdir(parents=True)
        (source / "code.py").write_text("verified\n")
        (source / ".distribution/macos-manifest.json").write_text(json.dumps({
            "schema_version": 1, "channel": "desktop", "version": version,
            "source_commit": "a" * 40, "source_sha256": {
                "code.py": hashlib.sha256(b"verified\n").hexdigest()}}))
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "org.nipat.desktop", "CFBundleShortVersionString": version}))

    def test_archive_keeps_legacy_bytes_and_user_data(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(migration, "installer_owned"):
            root = Path(tmp); old = root / "NIPAT Desktop.app"; new = root / "NewPat.app"
            state = root / "state"; state.mkdir()
            data = root / "runs/result.txt"; data.parent.mkdir(); data.write_text("keep")
            self.bundle(old, "0.9.1"); self.bundle(new, "0.9.5")
            target = migration.archive_legacy(old, new, state)
            self.assertFalse(old.exists())
            self.assertEqual((target / "Contents/Resources/app/code.py").read_text(), "verified\n")
            self.assertEqual(data.read_text(), "keep")
            self.assertTrue(new.is_dir())

    def test_modified_legacy_or_invalid_new_bundle_is_never_moved(self):
        for damaged in ("old", "new"):
            with self.subTest(damaged=damaged), tempfile.TemporaryDirectory() as tmp, patch.object(migration, "installer_owned"):
                root = Path(tmp); old = root / "old"; new = root / "new"; state = root / "state"; state.mkdir()
                self.bundle(old, "0.9.1"); self.bundle(new, "0.9.5")
                ((old if damaged == "old" else new) / "Contents/Resources/app/code.py").write_text("changed")
                with self.assertRaises(ValueError):
                    migration.archive_legacy(old, new, state)
                self.assertTrue(old.is_dir())
                self.assertFalse((state / "legacy-applications").exists())

    def test_legacy_version_cannot_change_the_backup_destination(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(migration, "installer_owned"):
            root = Path(tmp); old = root / "old"; new = root / "new"; state = root / "state"; state.mkdir()
            self.bundle(old, "../../elsewhere"); self.bundle(new, "0.9.5")
            with self.assertRaisesRegex(ValueError, "Versione"):
                migration.archive_legacy(old, new, state)
            self.assertTrue(old.is_dir())
            self.assertFalse((state / "legacy-applications").exists())

    def test_malformed_legacy_metadata_leaves_app_in_place_but_new_metadata_fails(self):
        for damaged, expected_status in (("old", 0), ("new", 1)):
            for metadata in ("plist", "manifest"):
                with self.subTest(damaged=damaged, metadata=metadata), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp); old = root / "old"; new = root / "new"; state = root / "state"; state.mkdir()
                    self.bundle(old, "0.9.1"); self.bundle(new, "0.9.5")
                    target = old if damaged == "old" else new
                    if metadata == "plist":
                        (target / "Contents/Info.plist").write_bytes(plistlib.dumps([]))
                    else:
                        (target / "Contents/Resources/app/.distribution/macos-manifest.json").write_text("[]")
                    with patch.object(migration, "installer_owned"), \
                            patch.object(migration, "OLD_APP", old), patch.object(migration, "NEW_APP", new), \
                            patch.object(migration, "STATE", state), patch.object(migration.sys, "platform", "darwin"), \
                            patch.object(migration.os, "geteuid", return_value=0, create=True), \
                            patch.object(migration.sys, "stderr", io.StringIO()):
                        self.assertEqual(migration.main(), expected_status)
                    self.assertTrue(old.is_dir())
                    self.assertFalse((state / "legacy-applications").exists())

    def test_ownership_rejects_writable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owned"; path.write_text("data"); path.chmod(0o666)
            with self.assertRaises(ValueError): migration.installer_owned(path)

    def test_ownership_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owned"; path.write_text("data")
            link = Path(tmp) / "link"
            try:
                link.symlink_to(path)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(ValueError): migration.installer_owned(link)


if __name__ == "__main__":
    unittest.main()
