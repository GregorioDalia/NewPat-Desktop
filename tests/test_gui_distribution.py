"""Native GUI distribution provenance and launcher preparation behavior."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


PROJECT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, PROJECT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


VERIFY = module("gui_distribution", "scripts/verify_gui_distribution.py")
LINUX = module("gui_linux_launch", "installer/linux/launch.py")


class GuiDistributionTests(unittest.TestCase):
    def test_pdf_renderer_fonts_and_notices_ship_with_verified_bytes(self):
        directory = PROJECT / "src/newpat/desktop/web/vendor/pdfmake"
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        expected = {"pdfmake.min.js", "vfs_fonts.js", "pdfmake.LICENSE.txt",
                    "Roboto.OFL.txt", "BUNDLED-NOTICES.txt"}
        self.assertEqual(manifest["assets"].keys(), expected)
        shipped = set((PROJECT / "distribution-files.txt").read_text(encoding="utf-8").splitlines())
        self.assertIn(manifest_path.relative_to(PROJECT).as_posix(), shipped)
        for name in expected:
            with self.subTest(name=name):
                path = directory / name
                self.assertIn(path.relative_to(PROJECT).as_posix(), shipped)
                data = path.read_bytes()
                self.assertEqual({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
                                 manifest["assets"][name])

    def observations(self):
        return [{"name": name, "status": "Valid", "subject": "CN=Microsoft, O=Microsoft Corporation, C=US",
                 "thumbprint": "A" * 40} for name in sorted(VERIFY.EXPECTED_BINARY_NAMES)]

    def test_signature_json_preserves_two_individual_binary_observations(self):
        observations = self.observations()
        self.assertEqual(VERIFY.signature_observations("\ufeff" + json.dumps(observations)), observations)

    def test_signature_json_rejects_collapsed_missing_duplicate_or_foreign_binaries(self):
        observations = self.observations()
        invalid = [observations[0], [], observations[:1], [observations],
                   [observations[0], observations[0]], [observations[0], None],
                   [observations[0], dict(observations[1], name="foreign.dll")],
                   [observations[0], dict(observations[1], name=["WebView2Loader.dll"])]]
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Incomplete"):
                VERIFY.signature_observations(json.dumps(value))

    def test_signature_json_rejects_invalid_signature_or_non_microsoft_signer(self):
        for changes in ({"status": "NotSigned"}, {"status": ["Valid", "Valid"]},
                        {"subject": "O=Another Corporation, C=US"}, {"subject": None},
                        {"subject": "CN=O=Microsoft Corporation, C=US"},
                        {"subject": ["O=Microsoft Corporation", "O=Microsoft Corporation"]}):
            observations = self.observations()
            observations[1].update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Authenticode"):
                VERIFY.signature_observations(json.dumps(observations))

    def test_reference_catalog_and_downloader_are_in_every_desktop_source_bundle(self):
        # The Windows, macOS and Linux builders stage code from this common inventory.
        shipped = (PROJECT / "distribution-files.txt").read_text(encoding="utf-8").splitlines()
        for source in ("src/newpat/desktop/references.py", "src/newpat/desktop/reference_downloads.py"):
            with self.subTest(source=source):
                self.assertIn(source, shipped)
                self.assertTrue((PROJECT / source).is_file())

    def test_pinned_dependencies_have_complete_verified_inventory(self):
        report = VERIFY.verify(PROJECT)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["authenticode_checked"])
        self.assertEqual(report["smart_app_control"], "not-performed")
        self.assertEqual({item["path"] for item in report["files"]}, VERIFY.EXPECTED_FILES)

    def test_modified_dependency_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "src/newpat/desktop/native/windows"
            shutil.copytree(PROJECT / "src/newpat/desktop/native/windows", destination)
            loader = destination / "x64/WebView2Loader.dll"
            data = bytearray(loader.read_bytes())
            data[-1] ^= 1
            loader.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "pinned provenance"):
                VERIFY.verify(root)


class DesktopPreparationTests(unittest.TestCase):
    def launch(self, arguments, *, failure=False):
        events = []

        @contextmanager
        def progress(_app):
            events.append("progress opened")
            try:
                yield
            finally:
                events.append("progress closed")

        def prepare(*_args, **_kwargs):
            events.append("prepare")
            if failure:
                raise LINUX.SetupError("Runtime non disponibile")
            return "sha256:" + "a" * 64

        def run(_app, command, _environment):
            events.append(("run", command))
            return 0

        helper = SimpleNamespace(preparation_notice=progress, show_startup_error=Mock())
        with patch.object(LINUX, "require_host"), \
                patch.object(LINUX, "gui_startup", return_value=helper) as gui, \
                patch.object(LINUX, "ensure_ready", side_effect=prepare), \
                patch.object(LINUX, "run_cli", side_effect=run):
            result = LINUX.launch(arguments)
        return result, events, helper, gui

    def test_default_desktop_closes_preparation_notice_before_gui(self):
        for arguments in ([], ["gui"]):
            with self.subTest(arguments=arguments):
                result, events, helper, _ = self.launch(arguments)
                self.assertEqual(result, 0)
                self.assertEqual(events, ["progress opened", "prepare", "progress closed", ("run", ["gui"])])
                helper.show_startup_error.assert_not_called()

    def test_cli_keeps_its_requested_mode_without_native_notice(self):
        result, events, _, gui = self.launch(["wizard"])
        self.assertEqual(result, 0)
        self.assertEqual(events, ["prepare", ("run", ["wizard"])])
        gui.assert_not_called()

    def test_failure_closes_progress_and_shows_native_error(self):
        result, events, helper, _ = self.launch([], failure=True)
        self.assertEqual(result, 1)
        self.assertEqual(events, ["progress opened", "prepare", "progress closed"])
        helper.show_startup_error.assert_called_once()
        self.assertIn("Runtime non disponibile", helper.show_startup_error.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
