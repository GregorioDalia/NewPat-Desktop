"""Archive a verified installer-owned NIPAT app after NewPat installs successfully.

Only the fixed legacy application is moved. User workspaces, VM state, BAMs and
results are never migration targets. A rejected legacy bundle is left in place.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import sys
import uuid

STATE = Path("/Library/Application Support/NIPAT-Desktop Installer")
NEW_APP = Path("/Applications/NewPat.app")
OLD_APP = Path("/Applications/NIPAT Desktop.app")


def installer_owned(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if path.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022 or not correct_type:
        raise ValueError(f"Percorso non appartenente all'installatore: {path}")


def verify_bundle(app: Path) -> dict:
    installer_owned(app, directory=True)
    plist_path = app / "Contents/Info.plist"
    installer_owned(plist_path)
    plist = plistlib.loads(plist_path.read_bytes())
    if not isinstance(plist, dict) or plist.get("CFBundleIdentifier") != "org.nipat.desktop":
        raise ValueError("Identità dell'applicazione precedente non riconosciuta.")
    version = plist.get("CFBundleShortVersionString")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Versione dell'applicazione non valida.")
    source = app / "Contents/Resources/app"
    for directory in (app / "Contents", app / "Contents/Resources", source,
                      source / ".distribution"):
        installer_owned(directory, directory=True)
    manifest_path = source / ".distribution/macos-manifest.json"
    installer_owned(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("channel") != "desktop"
            or manifest.get("version") != plist.get("CFBundleShortVersionString")
            or not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", "")))):
        raise ValueError("Manifest dell'applicazione non verificabile.")
    inventory = manifest.get("source_sha256")
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("Inventario sorgenti mancante.")
    checked_directories = {source}
    for name, expected in inventory.items():
        if not isinstance(name, str):
            raise ValueError("Inventario sorgenti non valido.")
        part = PurePosixPath(name)
        if (part.is_absolute() or ".." in part.parts or part.as_posix() != name
                or "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", str(expected))):
            raise ValueError("Inventario sorgenti non valido.")
        path = source / name
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("Il percorso sorgente esce dall'applicazione.")
        for directory in path.parents:
            if directory == source:
                break
            if directory not in checked_directories:
                installer_owned(directory, directory=True)
                checked_directories.add(directory)
        installer_owned(path)
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Sorgente precedente modificato: {name}")
    return manifest


def archive_legacy(old: Path = OLD_APP, new: Path = NEW_APP, state: Path = STATE) -> Path | None:
    """Caller holds the exclusive installer transaction lock."""
    verify_bundle(new)
    if not old.exists() and not old.is_symlink():
        return None
    previous = verify_bundle(old)
    installer_owned(state, directory=True)
    backup = state / "legacy-applications"
    backup.mkdir(mode=0o755, exist_ok=True)
    installer_owned(backup, directory=True)
    target = backup / f"NIPAT-{previous['version']}-{uuid.uuid4().hex}.app"
    old.rename(target)
    return target


def main() -> int:
    if sys.platform != "darwin" or os.geteuid() != 0:
        print("NewPat: migrazione disponibile solo nell'installatore macOS.", file=sys.stderr)
        return 1
    try:
        verify_bundle(NEW_APP)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"NewPat: nuova applicazione non verificata: {error}", file=sys.stderr)
        return 1
    try:
        target = archive_legacy(OLD_APP, NEW_APP, STATE)
        if target:
            print(f"NewPat: applicazione precedente conservata in {target}")
    except (OSError, ValueError, TypeError, KeyError) as error:
        # Do not fail a valid new installation because of an unrelated/modified
        # legacy directory. It remains untouched for explicit user inspection.
        print(f"NewPat: precedente applicazione conservata al suo posto: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
