"""Full package round trips, hostile archives and installed-channel isolation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest

from nipat.errors import NipatError
from nipat.update_handoff import windows_installation_platform

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("windows_zip", ROOT / "installer/windows/zip_package.py")
ZIP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ZIP)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def package(tmp_path, request):
    version = getattr(request, "param", "0.8.99")
    app = tmp_path / "stage/app"
    assets = tmp_path / "assets"
    assets.mkdir()
    manifest = {"schema_version": 1, "version": version, "release_tag": "v" + version,
                "source_commit": "a" * 40, "source_sha256": {}, "assets": {}}
    for key in ("rootfs", "scientific_image"):
        data = (key + " scientific fixture").encode()
        (assets / (key + ".tar.gz")).write_bytes(data)
        manifest["assets"][key] = {"file": key + ".tar.gz", "sha256": sha(data), "size": len(data)}
    files = {"src/nipat/__init__.py": ('__version__ = "' + version + '"\n').encode()}
    files.update({path: (ROOT / path).read_bytes() for path in ZIP.ROOT_FILES.values()})
    manifest["source_sha256"] = {name: sha(data) for name, data in files.items()}
    files[".distribution/installer-manifest.json"] = json.dumps(manifest).encode()
    files[".distribution/python-3.12.10-embed-amd64.zip"] = b"embedded Python fixture"
    for name, data in files.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    inventory = json.dumps({"schema_version": 1, "installation_channel": "desktop",
                            "source_commit": manifest["source_commit"],
                            "files": [{"path": name, "sha256": sha(data)} for name, data in files.items()]}).encode()
    (app / ".distribution/application-files.json").write_bytes(inventory)
    record = ZIP.build(app.parent, assets, tmp_path / "output")
    return tmp_path / "output" / record["file"], manifest, inventory, record


def test_complete_offline_payload_round_trip(package, tmp_path):
    path, manifest, inventory, record = package
    destination = tmp_path / "Extracted & è"
    assert ZIP.verify(path, manifest, inventory, extract_to=destination) == record
    assert (destination / "1_INSTALLA.cmd").read_bytes() == (ROOT / "installer/windows/zip-install.cmd").read_bytes()
    assert (destination / "app/.distribution/python-3.12.10-embed-amd64.zip").is_file()
    assert all((destination / "assets" / item["file"]).is_file() for item in manifest["assets"].values())
    with pytest.raises(FileExistsError):
        ZIP.verify(path, manifest, inventory, extract_to=destination)


@pytest.mark.parametrize("mutation", ["extra", "missing", "modified", "duplicate", "case", "traversal", "link"])
def test_invalid_archive_never_extracts(package, tmp_path, mutation):
    path, manifest, inventory, _ = package
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(bad, "w") as target:
        for info in source.infolist():
            if mutation == "missing" and info.filename == "assets/rootfs.tar.gz":
                continue
            data = source.read(info)
            if mutation == "modified" and info.filename == "assets/scientific_image.tar.gz":
                data += b"changed"
            target.writestr(info, data)
        if mutation in {"extra", "traversal", "case", "duplicate"}:
            name = {"extra": "unexpected.exe", "traversal": "../escaped", "case": "1_installa.cmd", "duplicate": "1_INSTALLA.cmd"}[mutation]
            target.writestr(name, b"unreviewed")
        if mutation == "link":
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(info, "../escape")
    destination = tmp_path / "never-created"
    with pytest.raises(ValueError):
        ZIP.verify(bad, manifest, inventory, extract_to=destination)
    assert not destination.exists()
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("name", ["/absolute", "a/../b", "a//b", "a\\b", "C:/file", "a:ads", "NUL", "dir/COM1.txt", "a./b", "a /b"])
def test_windows_filename_rules(name):
    with pytest.raises(ValueError):
        ZIP.safe_name(name)


def test_zip_destination_cannot_use_symlink_ancestor(package, tmp_path):
    path, manifest, inventory, _ = package
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable to this Windows account")
    with pytest.raises(ValueError, match="collegamenti"):
        ZIP.verify(path, manifest, inventory, extract_to=link / "output")


def test_update_channel_is_bound_to_managed_installation(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "Cartella estratta & è/NIPAT"
    root.mkdir(parents=True)
    owner = root / "installation.json"
    owner.write_text(json.dumps({"schema_version": 1, "product": "nipat-desktop", "installation_method": "zip"}))
    project = root / "versions" / ("0.8.99-" + "a" * 40)
    marker = project / ".runtime/zip-install.json"
    marker.parent.mkdir(parents=True)
    assert windows_installation_platform(project) == "windows-x86_64"
    marker.write_text(json.dumps({"schema_version": 1, "installation_method": "zip", "root": str(root)}))
    assert windows_installation_platform(project) == "windows-zip-x86_64"
    marker.write_text(json.dumps({"schema_version": 1, "installation_method": "zip", "root": str(tmp_path / "other")}))
    with pytest.raises(NipatError):
        windows_installation_platform(project)
    marker.write_text("broken json")
    with pytest.raises(NipatError):
        windows_installation_platform(project)
    marker.write_text(json.dumps({"schema_version": 1, "installation_method": "zip", "root": str(root)}))
    owner.unlink()
    with pytest.raises(NipatError):
        windows_installation_platform(project)
    owner.write_text(json.dumps({"schema_version": 1, "product": "foreign", "installation_method": "zip"}))
    with pytest.raises(NipatError):
        windows_installation_platform(project)


def test_zip_preferences_are_separate_and_survive_application_versions(tmp_path, monkeypatch):
    from nipat import preferences
    monkeypatch.setattr(preferences.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("NIPAT_SETTINGS_FILE", raising=False)
    monkeypatch.delenv("NIPAT_PROJECT_DIR", raising=False)
    assert preferences.preferences_path() == tmp_path / "NIPAT-Desktop/preferences.json"
    root = tmp_path / "Cartella estratta & è/NIPAT"
    root.mkdir(parents=True)
    (root / "installation.json").write_text(json.dumps({"schema_version": 1, "product": "nipat-desktop", "installation_method": "zip"}))
    for version, commit in (("0.8.99", "a" * 40), ("0.9.0", "b" * 40)):
        project = root / "versions" / (version + "-" + commit)
        marker = project / ".runtime/zip-install.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"schema_version": 1, "installation_method": "zip", "root": str(root)}))
        monkeypatch.setenv("NIPAT_PROJECT_DIR", str(project))
        assert preferences.preferences_path() == root / "preferences.json"
    monkeypatch.setenv("NIPAT_SETTINGS_FILE", str(tmp_path / "explicit.json"))
    assert preferences.preferences_path() == tmp_path / "explicit.json"


@pytest.mark.parametrize("package", ["0.9.0", "1.2.3"], indirect=True)
def test_installed_zip_extractor_accepts_future_stable_release(package, tmp_path, monkeypatch):
    import sys
    archive, manifest, _, record = package
    destination = tmp_path / "future update extracted"
    monkeypatch.setattr(sys, "argv", [
        "zip_package.py", "extract-update", "--package", str(archive),
        "--destination", str(destination), "--version", manifest["version"],
        "--source", manifest["source_commit"], "--sha256", record["sha256"],
    ])
    ZIP.main()
    assert manifest["version"] in (destination / "app/src/nipat/__init__.py").read_text()
    assert all((destination / "assets" / asset["file"]).is_file()
               for asset in manifest["assets"].values())


@pytest.mark.parametrize("version", ["0.9.0rc1", "01.2.3", "1.02.3", "1.2.03", "1.2", "../0.9.0"])
def test_zip_release_names_reject_nonstable_and_ambiguous_versions(version):
    with pytest.raises(ValueError):
        ZIP.filename(version)
