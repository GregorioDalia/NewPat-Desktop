"""Independent WSL identity and verified byte-for-byte archive reuse."""
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("component_assets", PROJECT / "scripts/build_windows_installer_assets.py")
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


class RuntimeComponentTests(unittest.TestCase):
    def marker(self):
        result = {
            "schema_version": 2, "vendor": "nipat-desktop", "purpose": "dedicated-wsl-runtime",
            "source_sha256": assets.component.source_inventory(PROJECT / "installer/runtime"),
            "apt_packages": {"docker-ce": "29.9.1", "libc6": "2.36"},
            "base_image": "debian@sha256:" + "a" * 64,
            "docker_engine_version": "Docker version 29.9.1, build abcdef",
            "compose_version": "Docker Compose version v2.40.3",
        }
        result["component_sha256"] = assets.component.component_identity(result)
        return result

    def previous(self, root, marker, embedded=None):
        archive = root / "nipat-wsl-rootfs-0.7.2-amd64.tar.gz"
        payload = json.dumps(embedded if embedded is not None else marker).encode()
        with tarfile.open(archive, "w:gz") as stream:
            info = tarfile.TarInfo("etc/nipat-runtime.json")
            info.size = len(payload)
            stream.addfile(info, io.BytesIO(payload))
        scientific = root / "nipat-scientific-runtime-0.7.2-amd64.tar.gz"
        scientific.write_bytes(gzip.compress(b"scientific fixture"))
        manifest = {
            "schema_version": 1, "version": "0.7.2", "release_tag": "v0.7.2",
            "source_commit": "a" * 40, "runtime_image": "sha256:" + "b" * 64,
            "installation_profile": dict(assets.EXPECTED_INSTALLATION_PROFILE, display_name="NIPAT Desktop"),
            "rootfs_provenance": marker,
            "assets": {"rootfs": assets.asset_metadata(archive, "v0.7.2"),
                       "scientific_image": assets.asset_metadata(scientific, "v0.7.2")},
        }
        (root / assets.MANIFEST_NAME).write_text(json.dumps(manifest))
        return archive, manifest

    def test_app_commit_and_export_image_do_not_define_component(self):
        marker = self.marker()
        assets.validate_rootfs_provenance(PROJECT, marker, "a" * 40)
        assets.validate_rootfs_provenance(PROJECT, marker, "b" * 40)
        marker["rootfs_image_id"] = "sha256:" + "c" * 64
        self.assertEqual(assets.component.component_identity(marker), marker["component_sha256"])

    def test_actual_dependency_change_requires_new_component(self):
        old = self.marker()
        changed = copy.deepcopy(old)
        changed["apt_packages"]["libc6"] = "2.37"
        self.assertNotEqual(assets.component.component_identity(old), assets.component.component_identity(changed))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.previous(root, old)
            target = root / "candidate.tar.gz"
            self.assertIsNone(assets.reuse_rootfs(root, changed, target))
            self.assertFalse(target.exists())

    def test_modified_runtime_source_is_rejected(self):
        marker = self.marker()
        marker["source_sha256"]["nipat-engine"] = "d" * 64
        marker["component_sha256"] = assets.component.component_identity(marker)
        with self.assertRaisesRegex(ValueError, "sorgenti"):
            assets.validate_rootfs_provenance(PROJECT, marker, "a" * 40)

    def test_same_component_reuses_identical_archive_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = self.marker()
            archive, _ = self.previous(root, marker)
            target = root / "next-release.tar.gz"
            self.assertEqual(assets.reuse_rootfs(root, marker, target), marker)
            self.assertEqual(archive.read_bytes(), target.read_bytes())

    def test_changed_archive_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = self.marker()
            archive, _ = self.previous(root, marker)
            with archive.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "manifest"):
                assets.reuse_rootfs(root, marker, root / "next.tar.gz")

    def test_embedded_marker_must_match_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = self.marker()
            embedded = copy.deepcopy(marker)
            embedded["apt_packages"]["libc6"] = "unexpected"
            self.previous(root, marker, embedded)
            with self.assertRaisesRegex(ValueError, "contenuto"):
                assets.reuse_rootfs(root, marker, root / "next.tar.gz")

    def test_legacy_rootfs_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.previous(root, {"schema_version": 1, "source_commit": "a" * 40})
            self.assertIsNone(assets.reuse_rootfs(root, self.marker(), root / "next.tar.gz"))

    def test_newpat_export_reads_historical_profile_and_binds_current_inputs(self):
        version = assets.checked_version(PROJECT)
        current_profile = json.loads((PROJECT / assets.PROFILE_PATH).read_bytes())
        self.assertEqual(current_profile["display_name"], "NewPat")
        for matching_component in (True, False):
            with self.subTest(matching_component=matching_component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                previous = root / "previous"
                previous.mkdir()
                marker = self.marker()
                archive, historical = self.previous(previous, marker)
                expected = copy.deepcopy(marker)
                if not matching_component:
                    expected["apt_packages"]["libc6"] = "2.37"
                    expected["component_sha256"] = assets.component.component_identity(expected)
                scientific_id, rootfs_id = "sha256:" + "b" * 64, "sha256:" + "c" * 64
                container_id = "f" * 64
                commands, exports = [], []

                def run(command, **kwargs):
                    commands.append(command)
                    output = json.dumps(expected) if command[:2] == ["docker", "run"] else (
                        container_id if command[:2] == ["docker", "create"] else "")
                    return subprocess.CompletedProcess(command, 0, output, "")

                def export(command, destination):
                    exports.append(command)
                    destination.write_bytes(gzip.compress(b"fresh export fixture", mtime=0))

                with patch.object(assets.bundle, "git_source", return_value={"commit": "a" * 40, "dirty": False}), \
                     patch.object(assets, "inspect_image", side_effect=[{"Id": scientific_id}, {"Id": rootfs_id}]), \
                     patch.object(assets.subprocess, "run", side_effect=run), \
                     patch.object(assets, "gzip_export", side_effect=export):
                    output = assets.export_assets(PROJECT, root / "assets", source_commit="a" * 40,
                        scientific_reference="science:tag", rootfs_reference="rootfs:tag",
                        reuse_rootfs_directory=previous)
                manifest = json.loads(output.read_bytes())
                assets.verify_runtime_assets(manifest, output.parent)
                self.assertEqual(manifest["version"], version)
                self.assertEqual(manifest["installation_profile"], current_profile)
                self.assertEqual(manifest["source_sha256"][assets.PROFILE_PATH.as_posix()],
                                 assets.bundle.sha256_file(PROJECT / assets.PROFILE_PATH))
                rootfs = output.parent / manifest["assets"]["rootfs"]["file"]
                self.assertEqual(manifest["rootfs_provenance"]["component_sha256"], expected["component_sha256"])
                self.assertEqual(exports[0], ["docker", "image", "save", scientific_id])
                self.assertEqual(len(exports), 1 if matching_component else 2)
                if matching_component:
                    self.assertEqual(rootfs.read_bytes(), archive.read_bytes())
                    self.assertFalse(any(command[:2] == ["docker", "create"] for command in commands))
                else:
                    self.assertNotEqual(rootfs.read_bytes(), archive.read_bytes())
                    self.assertEqual(exports[1], ["docker", "container", "export", container_id])
                    self.assertIn(["docker", "container", "rm", "--force", container_id], commands)
                self.assertEqual(json.loads((previous / assets.MANIFEST_NAME).read_bytes()), historical)


if __name__ == "__main__":
    unittest.main()
