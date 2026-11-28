"""Build and verify the versioned payload consumed by the stable Windows setup.

This package is deliberately distinct from the complete, locally installed ZIP:
it has no double-click entry point and is applied only by the verified bootstrap.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

_SPEC = importlib.util.spec_from_file_location("newpat_payload_zip", Path(__file__).with_name("zip_package.py"))
zip_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(zip_support)


def filename(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Versione payload non valida")
    return f"NewPat-{version}-Windows-payload.zip"


def expected_files(manifest, inventory_bytes):
    expected = zip_support.expected_files(manifest, inventory_bytes)
    for name in zip_support.root_files(manifest["version"]):
        expected.pop(name)
    return expected


def verify(package, manifest, inventory_bytes, *, extract_to=None):
    package = Path(package)
    if package.is_symlink() or not 0 < package.stat().st_size <= zip_support.MAX_BYTES:
        raise ValueError("Pacchetto desktop non valido")
    expected = expected_files(manifest, inventory_bytes)
    with zipfile.ZipFile(package) as archive:
        infos = zip_support.inspect_archive(archive)
        if {item.filename for item in infos} != set(expected):
            raise ValueError("Il payload desktop non corrisponde all'inventario")
        for item in infos:
            with archive.open(item) as stream:
                if zip_support.digest(stream) != expected[item.filename]:
                    raise ValueError(f"SHA-256 payload non valido: {item.filename}")
        if extract_to is not None:
            destination = Path(extract_to)
            for parent in (destination, *destination.parents):
                if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                    raise ValueError("Destinazione payload contiene collegamenti")
            destination.mkdir()
            for item in infos:
                target = destination.joinpath(*PurePosixPath(item.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("xb") as output:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(block)
    return {
        "schema_version": 1, "distribution": "windows-bootstrap-payload",
        "version": manifest["version"], "source_commit": manifest["source_commit"],
        "file": filename(manifest["version"]), "sha256": zip_support.file_digest(package),
        "size": package.stat().st_size,
        "application_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "embedded_assets": {key: {field: value[field] for field in ("file", "sha256", "size")}
                            for key, value in manifest["assets"].items()},
    }


def build(stage, assets, output):
    app = Path(stage) / "app"
    manifest = json.loads((app / ".distribution/installer-manifest.json").read_bytes())
    inventory = (app / ".distribution/application-files.json").read_bytes()
    expected = expected_files(manifest, inventory)
    paths = {"app/" + path.relative_to(app).as_posix(): path
             for path in app.rglob("*") if path.is_file()}
    paths.update({"assets/" + value["file"]: Path(assets) / value["file"]
                  for value in manifest["assets"].values()})
    if set(paths) != set(expected) or any(path.is_symlink() for path in app.rglob("*")):
        raise ValueError("Stage payload contiene file imprevisti o collegamenti")
    for name, path in paths.items():
        if path.is_symlink() or zip_support.file_digest(path) != expected[name]:
            raise ValueError(f"Stage payload modificato: {name}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / filename(manifest["version"])
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, path in sorted(paths.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    destination.write(block)
    record = verify(target, manifest, inventory)
    (output / "windows-payload-build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.stage, args.assets, args.output), indent=2))


if __name__ == "__main__":
    main()
