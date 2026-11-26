import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("linux_upgrade", Path(__file__).resolve().parents[1] / "scripts/verify_linux_upgrade.py")
upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upgrade)


class LinuxUpgradePreservationTests(unittest.TestCase):
    def test_historical_candidates_keep_the_baseline_used_in_their_reports(self):
        self.assertEqual(upgrade.baseline_for("0.9.9"), upgrade.BASELINE_072)
        self.assertEqual(upgrade.baseline_for("0.8.2"), upgrade.BASELINE_072)
        self.assertEqual(upgrade.baseline_for("0.7.2"), upgrade.BASELINE)

    def test_0910_upgrade_matches_the_published_099_package_and_commit(self):
        for version in ("0.9.10rc1", "0.9.10"):
            with self.subTest(candidate=version):
                self.assertEqual(upgrade.baseline_for(version), {
                    "version": "0.9.9", "file": "nipat-desktop_0.9.9_amd64.deb",
                    "source_commit": "adc659bd132cc24353e637f6430e3cc470e0a8f8",
                    "sha256": "b8bb9fb6c8305ab482d16310eb69414d7312060210950280e31683939d63f39f",
                })

    def test_upgrade_allows_new_runs_but_never_changes_previous_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "old/result.tsv"
            old.parent.mkdir()
            old.write_text("value\n0.602\n")
            before = upgrade.install.snapshot(root)
            (root / "new-result.tsv").write_text("new data\n")
            self.assertTrue(upgrade.preserved_files(root, before))
            old.write_text("value\n0.603\n")
            self.assertFalse(upgrade.preserved_files(root, before))
            old.unlink()
            self.assertFalse(upgrade.preserved_files(root, before))


if __name__ == "__main__":
    unittest.main()
