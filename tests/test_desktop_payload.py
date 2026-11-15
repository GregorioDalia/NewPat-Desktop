"""Independent EXE payload round trips and failure-before-extraction checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("desktop_payload_test", ROOT / "installer/windows/desktop_payload.py")
payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(payload)


@pytest.fixture
def built(tmp_path):
    stage, assets, output = tmp_path / "stage", tmp_path / "assets", tmp_path / "output"
    app = stage / "app"
    assets.mkdir()
    manifest = {"version": "0.8.99", "source_commit": "a" * 40,
                "source_sha256": {}, "assets": {}}
    content = {"2_AVVIA.cmd": b"echo launcher\n"}
    content.update({name: (ROOT / name).read_bytes() for name in payload.zip_support.ROOT_FILES.values()})
    manifest["source_sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    for role in ("rootfs", "scientific_image"):
        data = role.encode()
        (assets / (role + ".tar.gz")).write_bytes(data)
        manifest["assets"][role] = {"file": role + ".tar.gz", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    content[".distribution/installer-manifest.json"] = json.dumps(manifest).encode()
    for name, data in content.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    inventory = json.dumps({"schema_version": 1, "installation_channel": "desktop",
                            "source_commit": manifest["source_commit"],
                            "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                                      for name, data in content.items()]}).encode()
    (app / ".distribution/application-files.json").write_bytes(inventory)
    record = payload.build(stage, assets, output)
    return output / record["file"], manifest, inventory, record


def test_payload_is_distinct_and_round_trips(built, tmp_path):
    package, manifest, inventory, record = built
    destination = tmp_path / "NIPAT payload è & files"
    assert payload.verify(package, manifest, inventory, extract_to=destination) == record
    assert record["distribution"] == "windows-bootstrap-payload"
    assert record["file"] == "NIPAT-0.8.99-Windows-payload.zip"
    assert (destination / "app/2_AVVIA.cmd").read_bytes() == b"echo launcher\n"
    assert not (destination / "1_INSTALLA.cmd").exists()
    assert (destination / "assets/rootfs.tar.gz").is_file()


@pytest.mark.parametrize("change", ["missing", "extra", "tampered", "outer_zip_launcher", "traversal"])
def test_invalid_payload_never_creates_destination(built, tmp_path, change):
    package, manifest, inventory, _ = built
    broken = tmp_path / "bad.zip"
    with zipfile.ZipFile(package) as source, zipfile.ZipFile(broken, "w") as target:
        for info in source.infolist():
            if change == "missing" and info.filename == "assets/rootfs.tar.gz":
                continue
            data = source.read(info)
            target.writestr(info, data + b"changed" if change == "tampered" else data)
        if change in {"extra", "outer_zip_launcher", "traversal"}:
            target.writestr({"extra": "app/unknown.exe", "outer_zip_launcher": "1_INSTALLA.cmd",
                             "traversal": "../escape"}[change], b"unsafe")
    destination = tmp_path / "not-created"
    with pytest.raises(ValueError):
        payload.verify(broken, manifest, inventory, extract_to=destination)
    assert not destination.exists()
    assert not (tmp_path / "escape").exists()
