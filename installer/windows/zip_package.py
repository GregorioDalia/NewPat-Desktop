"""Build and verify the complete Windows ZIP; never execute archive contents.

The reviewed app inventory and installer manifest bind every member, including
the embedded Python, WSL filesystem and scientific image. No source ZIP is an
installable package. Extraction is deliberately limited to this layout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import stat
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from nipat.branding import windows_complete_filename, windows_package_generation

MAX_BYTES = 2**31 - 1
MAX_EXPANDED = 3 * 1024**3


def root_files(version):
    if windows_package_generation(version) == 1:
        return {"1_INSTALLA.cmd": "installer/windows/zip-install.cmd",
                "LEGGIMI.txt": "installer/windows/zip-readme.txt"}
    return {"1_INSTALL.cmd": "installer/windows/zip-install.cmd",
            "README.txt": "installer/windows/zip-readme.txt"}


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return digest(stream)


def filename(version):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Versione ZIP non valida")
    return windows_complete_filename(version)


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or "\\" in name
            or any(p in {".", ".."} or p.endswith((".", " "))
                   or re.search(r'[\x00-\x1f<>:"|?*]', p)
                   or re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p)
                   for p in path.parts)):
        raise ValueError(f"Percorso ZIP non valido: {name}")
    return path


def expected_files(manifest, inventory_bytes):
    inventory = json.loads(inventory_bytes)
    if (inventory.get("schema_version") != 1 or inventory.get("installation_channel") != "desktop"
            or inventory.get("source_commit") != manifest["source_commit"]):
        raise ValueError("Inventario ZIP diverso dalla release")
    expected = {}
    for entry in inventory["files"]:
        name = "app/" + str(safe_name(entry["path"]))
        if name in expected or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
            raise ValueError("Inventario ZIP duplicato o non valido")
        expected[name] = entry["sha256"]
    expected["app/.distribution/application-files.json"] = hashlib.sha256(inventory_bytes).hexdigest()
    for name, source in root_files(manifest["version"]).items():
        expected[name] = manifest["source_sha256"][source]
    for asset in manifest["assets"].values():
        expected["assets/" + str(safe_name(asset["file"]))] = asset["sha256"]
    return expected


def inspect_archive(archive):
    infos = archive.infolist()
    if not infos or len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
        raise ValueError("Dimensioni ZIP non valide")
    seen = set()
    for info in infos:
        safe_name(info.filename)
        mode = info.external_attr >> 16
        if (info.is_dir() or info.flag_bits & 1 or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                or info.filename.casefold() in seen or info.file_size > MAX_BYTES):
            raise ValueError("ZIP con collegamenti, duplicati o membri non regolari")
        seen.add(info.filename.casefold())
    return infos


def verify(package, manifest, inventory_bytes, *, extract_to=None):
    package = Path(package)
    if package.is_symlink() or not 0 < package.stat().st_size <= MAX_BYTES:
        raise ValueError("Pacchetto ZIP non valido")
    expected = expected_files(manifest, inventory_bytes)
    with zipfile.ZipFile(package) as archive:
        infos = inspect_archive(archive)
        if {i.filename for i in infos} != set(expected):
            raise ValueError("Il contenuto ZIP non corrisponde all'inventario")
        for info in infos:
            with archive.open(info) as stream:
                if digest(stream) != expected[info.filename]:
                    raise ValueError(f"SHA-256 ZIP non valido: {info.filename}")
        if extract_to is not None:
            destination = Path(extract_to)
            # New directory only: never traverse or merge with existing files.
            for parent in (destination, *destination.parents):
                if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
                    raise ValueError("Destinazione ZIP contiene collegamenti")
            destination.mkdir()
            for info in infos:
                target = destination.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
    return {"schema_version": 1, "distribution": "self-contained-wsl-zip",
            "version": manifest["version"], "source_commit": manifest["source_commit"],
            "file": filename(manifest["version"]), "sha256": file_digest(package),
            "size": package.stat().st_size,
            "application_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "embedded_assets": {k: {f: v[f] for f in ("file", "sha256", "size")}
                                for k, v in manifest["assets"].items()}}


def build(stage, assets, output):
    app = Path(stage) / "app"
    manifest = json.loads((app / ".distribution/installer-manifest.json").read_bytes())
    inventory = (app / ".distribution/application-files.json").read_bytes()
    paths = {"app/" + p.relative_to(app).as_posix(): p for p in app.rglob("*") if p.is_file()}
    paths.update({name: app / source for name, source in root_files(manifest["version"]).items()})
    paths.update({"assets/" + a["file"]: Path(assets) / a["file"] for a in manifest["assets"].values()})
    expected = expected_files(manifest, inventory)
    if set(paths) != set(expected) or any(p.is_symlink() for p in app.rglob("*")):
        raise ValueError("Stage ZIP contiene file imprevisti o collegamenti")
    for name, path in paths.items():
        if path.is_symlink() or file_digest(path) != expected[name]:
            raise ValueError(f"Stage ZIP modificato: {name}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / filename(manifest["version"])
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as archive:
        for name, path in sorted(paths.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as dest:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    dest.write(chunk)
    record = verify(target, manifest, inventory)
    (output / "windows-zip-build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("build")
    create.add_argument("--stage", type=Path, required=True)
    create.add_argument("--assets", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    unpack = sub.add_parser("extract-update")
    for name in ("package", "destination", "version", "source", "sha256"):
        unpack.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if args.command == "build":
        print(json.dumps(build(args.stage, args.assets, args.output), indent=2))
    else:
        package = Path(args.package)
        if file_digest(package) != args.sha256:
            raise ValueError("Checksum aggiornamento ZIP non valido")
        with zipfile.ZipFile(package) as archive:
            inspect_archive(archive)
            manifest = json.loads(archive.read("app/.distribution/installer-manifest.json"))
            inventory = archive.read("app/.distribution/application-files.json")
        if manifest["version"] != args.version or manifest["source_commit"] != args.source:
            raise ValueError("Identita aggiornamento ZIP non valida")
        verify(package, manifest, inventory, extract_to=Path(args.destination))


if __name__ == "__main__":
    main()
