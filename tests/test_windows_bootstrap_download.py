"""Exercise the frozen setup contract independently of changing application code."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "nipat_bootstrap_download", ROOT / "installer/windows/bootstrap_download.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def package(tmp_path, *, version="0.9.10", corrupt_member=False, extra=None):
    members = {"app/2_LAUNCH.cmd": b"@echo fixture", "assets/rootfs.tar.gz": b"rootfs",
               "assets/scientific.tar.gz": b"scientific"}
    manifest = {"schema_version": 1, "version": version, "source_commit": "a" * 40,
                "installation_profile": {"channel": "desktop"}, "assets": {
                    "rootfs": {"file": "rootfs.tar.gz", "sha256": sha(b"rootfs"), "size": 6},
                    "scientific_image": {"file": "scientific.tar.gz", "sha256": sha(b"scientific"), "size": 10}}}
    members["app/.distribution/installer-manifest.json"] = json.dumps(manifest).encode()
    inventory = {"schema_version": 1, "installation_channel": "desktop", "source_commit": "a" * 40,
                 "files": [{"path": name.removeprefix("app/"), "sha256": sha(value)}
                           for name, value in members.items() if name.startswith("app/")]}
    members["app/.distribution/application-files.json"] = json.dumps(inventory).encode()
    if corrupt_member:
        members["app/2_LAUNCH.cmd"] += b"changed"
    if extra:
        members.update(extra)
    target = tmp_path / "payload.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name, value in members.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, value)
    expected = {"version": version, "source_commit": "a" * 40,
                "size": target.stat().st_size, "sha256": sha(target.read_bytes())}
    return target, expected


def feed():
    name = "NIPAT-0.9.10-Windows-payload.zip"
    return {"schema_version": 1, "product": "nipat-desktop", "version": "0.9.10",
            "source_commit": "a" * 40, "release_tag": "v0.9.10", "channel": "stable",
            "minimum_updater_version": 2,
            "release_notes_url": bootstrap.REPOSITORY + "/releases/tag/v0.9.10",
            "assets": [{"platform": "windows-bootstrap-x86_64", "name": name,
                        "size": 123, "sha256": "b" * 64,
                        "url": bootstrap.REPOSITORY + "/releases/download/v0.9.10/" + name}]}


def test_new_setup_refuses_payloads_from_legacy_layout():
    with pytest.raises(ValueError, match="compatibile"):
        bootstrap._target("0.9.9", "a" * 40, "b" * 64, 100)


def test_freeze_can_install_new_compatible_application_versions(tmp_path):
    for version in ("0.9.10", "0.9.11", "1.2.3"):
        base = tmp_path / version
        base.mkdir()
        archive, target = package(base, version=version)
        bootstrap._target(version, target["source_commit"], target["sha256"], target["size"])
        destination = base / "NIPAT con spazi è"
        manifest = bootstrap.extract_payload(archive, destination, target)
        assert manifest["version"] == version
        assert (destination / "app/2_LAUNCH.cmd").read_bytes() == b"@echo fixture"
        assert (destination / "runtime-cache" / (sha(b"rootfs") + "-rootfs.tar.gz")).read_bytes() == b"rootfs"
        assert (destination / "runtime-cache" / (sha(b"scientific") + "-scientific.tar.gz")).read_bytes() == b"scientific"


@pytest.mark.parametrize("alter", ["size", "sha256", "version", "source_commit"])
def test_wrong_target_never_extracts(tmp_path, alter):
    archive, target = package(tmp_path)
    target[alter] = {"size": 1, "sha256": "0" * 64, "version": "0.9.1",
                     "source_commit": "b" * 40}[alter]
    destination = tmp_path / "app"
    with pytest.raises(ValueError):
        bootstrap.extract_payload(archive, destination, target)
    assert not destination.exists()


@pytest.mark.parametrize("extra", ["../outside.txt", "app/../outside.txt", "app/a:b", "app/CON.txt",
                                  "app/2_launch.CMD", "unlisted.txt"])
def test_unsafe_or_unlisted_archive_members_never_extract(tmp_path, extra):
    archive, target = package(tmp_path, extra={extra: b"unexpected"})
    destination = tmp_path / "app"
    with pytest.raises(ValueError):
        bootstrap.extract_payload(archive, destination, target)
    assert not destination.exists()


def test_member_corruption_rejected_even_if_outer_hash_matches(tmp_path):
    archive, target = package(tmp_path, corrupt_member=True)
    with pytest.raises(ValueError, match="integro"):
        bootstrap.extract_payload(archive, tmp_path / "extracted", target)
    assert not (tmp_path / "extracted").exists()


def test_existing_destination_and_symlinks_rejected_without_data_loss(tmp_path):
    archive, target = package(tmp_path)
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "research.txt"
    sentinel.write_text("keep")
    with pytest.raises(ValueError, match="esiste"):
        bootstrap.extract_payload(archive, destination, target)
    assert sentinel.read_text() == "keep"
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip("User cannot create symlinks on this machine")
    with pytest.raises(ValueError, match="collegamento"):
        bootstrap.extract_payload(archive, linked / "new", target)


def test_official_feed_and_origin_are_bound():
    valid = feed()
    assert bootstrap.validate_feed(valid)["version"] == "0.9.10"
    valid["assets"][0]["url"] = "https://github.com/another/repo/releases/download/v0.9.10/payload.zip"
    with pytest.raises(ValueError, match="ufficiale"):
        bootstrap.validate_feed(valid)
    valid = feed()
    valid["minimum_updater_version"] = 1
    with pytest.raises(ValueError, match="supportato"):
        bootstrap.validate_feed(valid)


@pytest.mark.parametrize("url", ["http://github.com/a", "https://github.com.evil.invalid/a",
                                 "file:///C:/payload.zip", "https://user@github.com/a",
                                 "https://github.com:444/a"])
def test_unapproved_download_locations_rejected(url):
    assert not bootstrap._approved_url(url)


@pytest.mark.parametrize("active", bootstrap.OFFICIAL_REPOSITORIES)
@pytest.mark.parametrize("recorded", bootstrap.OFFICIAL_REPOSITORIES)
def test_manual_setup_downloads_from_current_verified_repository(monkeypatch, active, recorded):
    from nipat.repository import REPOSITORY_ID, OFFICIAL_REPOSITORIES
    assert bootstrap.REPOSITORY_ID == int(REPOSITORY_ID)
    assert bootstrap.OFFICIAL_REPOSITORIES == OFFICIAL_REPOSITORIES
    manifest = json.loads(json.dumps(feed()).replace(bootstrap.REPOSITORY, "https://github.com/" + recorded))
    metadata = {"id": int(REPOSITORY_ID), "full_name": active}
    expected = "https://github.com/" + active
    urls = []

    def get(url):
        urls.append(url)
        response = metadata if url == bootstrap.REPOSITORY_API else manifest
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(bootstrap, "_open", get)
    target = bootstrap.current_target()
    assert urls == [bootstrap.REPOSITORY_API, expected + "/releases/latest/download/" + bootstrap.FEED_NAME]
    assert target["url"] == expected + "/releases/download/v0.9.10/NIPAT-0.9.10-Windows-payload.zip"


@pytest.mark.parametrize(("repo_id", "name"), [
    (1, "GregorioDalia/nipat-desktop"), (1307623649, "other/NewPat-Desktop"),
    (1307623649, "GregorioDalia/another-project"),
])
def test_manual_setup_rejects_different_repository_before_fetching_feed(monkeypatch, repo_id, name):
    def get(url):
        assert url == bootstrap.REPOSITORY_API
        return io.BytesIO(json.dumps({"id": repo_id, "full_name": name}).encode())
    monkeypatch.setattr(bootstrap, "_open", get)
    with pytest.raises(ValueError, match="repository"):
        bootstrap.current_target()


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError, match="duplicata"):
        bootstrap._json('{"schema_version":1,"schema_version":2}')


def test_explicit_update_does_not_resolve_latest(tmp_path, monkeypatch):
    archive, target = package(tmp_path)
    monkeypatch.setattr(bootstrap, "current_target", lambda: pytest.fail("Explicit update queried latest"))
    result = bootstrap.main(["--package", str(archive), "--destination", str(tmp_path / "extracted"),
                             "--version", target["version"], "--source", target["source_commit"],
                             "--sha256", target["sha256"], "--size", str(target["size"]),
                             "--error-file", str(tmp_path / "error.txt"),
                             "--report-file", str(tmp_path / "report.ini")])
    assert result == 0
    assert "version=0.9.10" in (tmp_path / "report.ini").read_text(encoding="utf-16")


def test_partial_update_identity_fails_before_network_or_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "current_target", lambda: pytest.fail("Partial identity queried latest"))
    assert bootstrap.main(["--version", "0.9.10", "--destination", str(tmp_path / "extracted"),
                           "--error-file", str(tmp_path / "error.txt"),
                           "--report-file", str(tmp_path / "report.ini")]) == 1
    assert not (tmp_path / "extracted").exists()


def test_downgrade_and_reused_version_rejected(tmp_path):
    metadata = tmp_path / ".distribution"
    metadata.mkdir()
    manifest = metadata / "installer-manifest.json"
    manifest.write_text(json.dumps({"version": "0.9.11", "source_commit": "a" * 40}))
    with pytest.raises(ValueError, match="recente"):
        bootstrap.check_installed(tmp_path, "0.9.10", "b" * 40)
    with pytest.raises(ValueError, match="differenti"):
        bootstrap.check_installed(tmp_path, "0.9.11", "b" * 40)
    bootstrap.check_installed(tmp_path, "0.9.11", "a" * 40)
    bootstrap.check_installed(tmp_path, "0.9.12", "b" * 40)


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows file sharing contract")
def test_verified_archive_handle_denies_writers_and_deletion(tmp_path):
    archive, _ = package(tmp_path)
    original = archive.read_bytes()
    with bootstrap._locked_reader(archive) as stream:
        assert stream.read(4) == b"PK\x03\x04"
        with pytest.raises(OSError):
            with archive.open("wb") as writer:
                writer.write(b"replacement")
        with pytest.raises(OSError):
            archive.unlink()
        assert archive.read_bytes() == original
    # The handle is released on exit; normal cleanup is possible again.
    archive.unlink()
    assert not archive.exists()


def test_extracted_payload_mutation_is_rejected_before_installation(tmp_path):
    archive, target = package(tmp_path)
    destination = tmp_path / "staged"
    bootstrap.extract_payload(archive, destination, target)
    bootstrap.extract_payload(archive, destination, target, check_only=True)
    changed = destination / "app/2_LAUNCH.cmd"
    changed.write_bytes(b"@echo changed")
    with pytest.raises(ValueError, match="modificato"):
        bootstrap.extract_payload(archive, destination, target, check_only=True)
    assert changed.read_bytes() == b"@echo changed"


def test_new_unlisted_staging_file_is_rejected_before_installation(tmp_path):
    archive, target = package(tmp_path)
    destination = tmp_path / "staged"
    bootstrap.extract_payload(archive, destination, target)
    extra = destination / "app/unlisted.py"
    extra.write_text("unreviewed fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="modificato"):
        bootstrap.extract_payload(archive, destination, target, check_only=True)
    assert extra.read_text(encoding="utf-8") == "unreviewed fixture"


def test_download_keeps_existing_file_and_removes_only_its_own_partial(tmp_path, monkeypatch):
    target = {"url": "https://github.com/unused", "version": "0.9.10",
              "size": 5, "sha256": sha(b"valid")}
    destination = tmp_path / "download.zip"
    monkeypatch.setattr(bootstrap, "_open", lambda url: io.BytesIO(b"wrong"))
    destination.write_bytes(b"previous download")
    with pytest.raises(FileExistsError):
        bootstrap.download(target, destination)
    assert destination.read_bytes() == b"previous download"
    destination.unlink()
    with pytest.raises(ValueError, match="SHA-256"):
        bootstrap.download(target, destination)
    assert not destination.exists()
