"""Native application qualification requires real readiness, not a loaded title."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_gui_app", PROJECT / "scripts/verify_gui_app.py")
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class NativeAppVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.app = self.root / "packaged app"
        assets = self.app / "src/newpat/desktop/web"
        assets.mkdir(parents=True)
        (assets / "index.html").write_text("<title>NewPat</title>")
        self.workspace = self.root / "isolated workspace"
        self.report, self.png = self.root / "report.json", self.root / "window.png"

    def invoke(self, **options):
        return VERIFY.verify(self.app, Path(sys.executable), self.workspace, self.report, self.png, **options)

    def produce(self, ready=True, pdf="passed"):
        self.report.write_text(json.dumps({"status": "passed", "nativeWebView": True,
                                           "appReady": ready, "pdfExport": pdf, "host": "native-test"}))
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n")

    def test_isolates_user_preferences_and_uses_actual_packaged_entrypoint(self):
        with patch.dict(os.environ, {"NEWPAT_SETTINGS_FILE": "/existing/research/settings.json",
                                     "NEWPAT_PROJECT_DIR": "/wrong/app", "PYTHONPATH": "/wrong/import"}), \
                patch.object(VERIFY.subprocess, "run", side_effect=lambda *_a, **_k: self.produce()) as child:
            self.assertTrue(self.invoke()["appReady"])
        command = child.call_args.args[0]
        environment = child.call_args.kwargs["env"]
        self.assertIn(str(self.app / "src"), command)
        self.assertIn("gui", command)
        self.assertNotIn("test_gui_windows_native.py", " ".join(command))
        self.assertEqual(environment["NEWPAT_SETTINGS_FILE"], str(self.workspace / "preferences.json"))
        self.assertEqual(environment["NEWPAT_DATA_DIR"], str(self.workspace / "data"))
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["NEWPAT_GUI_VERIFY_PDF"], "1")
        self.assertEqual(json.loads(self.report.read_text())["scope"], "packaged-native-application")

    def test_source_smoke_has_distinct_scope_without_claiming_packaged_validation(self):
        with patch.object(VERIFY.subprocess, "run", side_effect=lambda *_a, **_k: self.produce()):
            result = self.invoke(scope="source-native-application")
        self.assertEqual(result["scope"], "source-native-application")
        self.assertEqual(json.loads(self.report.read_text())["scope"], "source-native-application")

    def test_title_or_fixture_readiness_cannot_qualify_the_full_app(self):
        with patch.object(VERIFY.subprocess, "run", side_effect=lambda *_a, **_k: self.produce(False)):
            with self.assertRaisesRegex(ValueError, "application.*readiness"):
                self.invoke()

    def test_ready_app_without_completed_native_pdf_export_is_rejected(self):
        with patch.object(VERIFY.subprocess, "run", side_effect=lambda *_a, **_k: self.produce(pdf=None)):
            with self.assertRaisesRegex(ValueError, "generate a PDF"):
                self.invoke()

    def test_failed_native_child_cannot_publish_success(self):
        with patch.object(VERIFY.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "native GUI")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.invoke()
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
