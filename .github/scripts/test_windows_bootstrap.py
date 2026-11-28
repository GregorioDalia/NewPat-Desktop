"""Stable setup reuse is tied to its complete inputs, never to an app version."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("windows_bootstrap_test", Path(__file__).with_name("windows_bootstrap.py"))
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stage = self.root / "stage"
        app = self.stage / "app"
        self.manifest = {"version": "0.9.99", "source_sha256": {}}
        for name in bootstrap.BOOTSTRAP_SOURCES:
            path = app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
            self.manifest["source_sha256"][name] = bootstrap.digest(path)
        distribution = app / ".distribution"
        distribution.mkdir()
        archive = distribution / bootstrap.PYTHON_NAME
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("python.exe", b"signed Python fixture")
            output.writestr("python312.zip", b"stdlib fixture")
        patcher = patch.object(bootstrap, "PYTHON_SHA256", bootstrap.digest(archive))
        patcher.start()
        self.addCleanup(patcher.stop)
        (distribution / "installer-manifest.json").write_text(json.dumps(self.manifest))

    def test_prepare_keeps_exact_python_and_is_independent_of_application_version(self):
        inputs = bootstrap.prepare(self.stage)
        self.assertEqual(bootstrap.verify_stage(self.stage), inputs)
        self.assertEqual((self.stage / "bootstrap/python/python.exe").read_bytes(), b"signed Python fixture")
        newer = copy.deepcopy(self.manifest)
        newer["version"] = "0.9.100"
        self.assertEqual(bootstrap.identities(newer), inputs)
        newer["source_sha256"]["installer/windows/bootstrap_download.py"] = "f" * 64
        self.assertNotEqual(bootstrap.identities(newer), inputs)

    def test_tampered_staged_interpreter_or_bootstrap_is_rejected(self):
        bootstrap.prepare(self.stage)
        target = self.stage / "bootstrap/python/python.exe"
        target.write_bytes(b"substituted interpreter")
        with self.assertRaisesRegex(ValueError, "exact pinned distribution"):
            bootstrap.verify_stage(self.stage)

    def test_input_source_mutation_cannot_be_hidden_by_staging(self):
        bootstrap.prepare(self.stage)
        (self.stage / "app/installer/windows/NewPat.iss").write_text("changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            bootstrap.verify_stage(self.stage)

    def test_clean_installer_never_downloads_an_older_bootstrap(self):
        bootstrap.prepare(self.stage)
        class HistoricalRelease:
            @staticmethod
            def official_release(suffix):
                return ("GregorioDalia/NewPat-Desktop",
                        {"draft": False, "prerelease": False, "tag_name": "v0.9.10"})

        self.assertFalse(bootstrap.reuse(self.stage, self.root / "out", fetcher=HistoricalRelease))
        self.assertFalse((self.root / "out").exists())

    def test_reuse_requires_published_asset_digest_and_matching_all_inputs(self):
        inputs = bootstrap.prepare(self.stage)
        exe = b"previous identical bootstrap"
        record = {"schema_version": 2, "distribution": "online-bootstrap", "bootstrap_version": bootstrap.BOOTSTRAP_VERSION,
                  "version": "0.9.99", "file": "NewPat-Setup.exe", "sha256": hashlib.sha256(exe).hexdigest(),
                  "size": len(exe), "bootstrap_inputs_sha256": inputs}
        records = {"installer-build.json": json.dumps(record).encode(), "NewPat-Setup.exe": exe}
        metadata = {"draft": False, "prerelease": False, "tag_name": "v0.9.99", "assets": [
            {"name": name, "digest": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data),
             "browser_download_url": "https://github.com/GregorioDalia/NewPat-Desktop/releases/download/v0.9.99/" + name}
            for name, data in records.items()]}
        class Fetcher:
            @staticmethod
            def official_release(suffix):
                assert suffix == "latest"
                return "GregorioDalia/NewPat-Desktop", metadata
            @staticmethod
            def checked_download(url, destination, expected_hash, expected_size, *, maximum):
                data = records[url.rsplit("/", 1)[-1]]
                assert hashlib.sha256(data).hexdigest() == expected_hash and len(data) == expected_size <= maximum
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                return destination
        output = self.root / "out"
        self.assertTrue(bootstrap.reuse(self.stage, output, fetcher=Fetcher))
        self.assertEqual((output / "NewPat-Setup.exe").read_bytes(), exe)
        metadata["assets"][1]["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "differs from its asset"):
            bootstrap.reuse(self.stage, self.root / "bad", fetcher=Fetcher)


if __name__ == "__main__":
    unittest.main()
