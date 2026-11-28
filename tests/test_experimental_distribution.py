"""NewPat installs its settings and runtime under product-owned roots."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from newpat.activity import windows_activity_path
from newpat.distribution import CHANNEL, WINDOWS_DIRECTORY
from newpat.installation import installation_inventory, inventory_lines
from newpat.errors import ValidationError
from newpat.paths import ProjectLayout
from newpat.preferences import preferences_path
from newpat.storage import validate_managed_directories


class DesktopDistributionTests(unittest.TestCase):
    def test_macos_data_cannot_overwrite_runtime_or_application(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            app = root / "app"
            workspace = root / "workspace"
            with patch.dict(os.environ, {"NEWPAT_BACKEND": "lima"}), patch("newpat.storage.Path.home", return_value=root):
                for selected in (workspace, root / ".newpat" / "lima", workspace / ".runtime", app / "data"):
                    layout = ProjectLayout(app, workspace, selected, root / "results", app / "compose.yaml")
                    with self.subTest(selected=selected), self.assertRaises(ValidationError):
                        validate_managed_directories(layout)
                layout = ProjectLayout(app, workspace, workspace / "data", workspace / "runs", app / "compose.yaml")
                validate_managed_directories(layout)

    def test_stable_installer_and_client_share_the_official_identity(self):
        root = Path(__file__).resolve().parents[1]
        profile = json.loads((root / "installer/windows/install-profile.json").read_text())
        self.assertEqual(profile["channel"], CHANNEL)
        self.assertEqual(profile["data_dir_name"], WINDOWS_DIRECTORY)
        self.assertEqual(profile["channel"], "desktop")

    def test_windows_preferences_and_lease_never_touch_stable_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            stable = root / "NIPAT-Experimental08"
            stable.mkdir()
            sentinel = stable / "preferences.json"
            sentinel.write_text('{"stable":true}')
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}, clear=True), \
                    patch("newpat.preferences.sys.platform", "win32"):
                self.assertEqual(preferences_path(), root / WINDOWS_DIRECTORY / "preferences.json")
                self.assertEqual(windows_activity_path(), root / WINDOWS_DIRECTORY / "activity.lock")
            self.assertEqual(sentinel.read_text(), '{"stable":true}')
            self.assertEqual(list(stable.iterdir()), [sentinel])

    def test_macos_preferences_and_inventory_use_macos_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder).resolve()
            with patch.dict(os.environ, {}, clear=True), patch("newpat.preferences.sys.platform", "darwin"), \
                    patch("newpat.preferences.Path.home", return_value=home):
                expected = home / "Library/Application Support/NewPat-Desktop/preferences.json"
                self.assertEqual(preferences_path(), expected)
                inventory = installation_inventory(home)
            self.assertEqual(inventory["platform"], "macos")
            self.assertIn("Lima", " ".join(inventory_lines(inventory)))
            self.assertNotIn("APT", " ".join(inventory_lines(inventory)))
            self.assertFalse(expected.exists())
