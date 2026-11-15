"""Prepare, reuse and bind the stable online installer independently of app versions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_VERSION = "1.0.0"
BOOTSTRAP_SOURCES = (
    "installer/windows/NIPAT.iss", "installer/windows/bootstrap-profile.iss",
    "installer/windows/bootstrap_download.py", "LICENSE", "assets/branding/nipat-icon.ico",
    ".github/scripts/install_inno.ps1",
)
PYTHON_NAME = "python-3.12.10-embed-amd64.zip"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identities(manifest):
    result = {name: manifest["source_sha256"][name] for name in BOOTSTRAP_SOURCES}
    result[".distribution/" + PYTHON_NAME] = PYTHON_SHA256
    require(all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
                for value in result.values()), "Invalid stable bootstrap inputs")
    return result


def prepare(stage):
    stage = Path(stage)
    app = stage / "app"
    manifest = json.loads((app / ".distribution/installer-manifest.json").read_bytes())
    expected = identities(manifest)
    require(all((app / name).is_file() and not (app / name).is_symlink()
                and digest(app / name) == value for name, value in expected.items()),
            "Stable bootstrap source bytes differ from the verified application")
    target = stage / "bootstrap"
    require(not target.exists() and not target.is_symlink(), "Bootstrap stage already exists")
    python = target / "python"
    python.mkdir(parents=True)
    with zipfile.ZipFile(app / ".distribution" / PYTHON_NAME) as archive:
        # Official pinned archive contains only flat regular members.
        for entry in archive.infolist():
            require(entry.filename == Path(entry.filename).name and not entry.is_dir()
                    and "/" not in entry.filename and "\\" not in entry.filename,
                    "Unexpected embedded Python layout")
            with archive.open(entry) as source, (python / entry.filename).open("xb") as output:
                shutil.copyfileobj(source, output)
    for name in ("bootstrap_download.py", "bootstrap-profile.iss"):
        shutil.copyfile(app / "installer/windows" / name, target / name)
    (target / "bootstrap-inputs.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    verify_stage(stage)
    return expected


def verify_stage(stage):
    stage = Path(stage)
    app, target = stage / "app", stage / "bootstrap"
    manifest = json.loads((app / ".distribution/installer-manifest.json").read_bytes())
    expected = identities(manifest)
    require(json.loads((target / "bootstrap-inputs.json").read_bytes()) == expected,
            "Bootstrap inventory identity changed")
    require(all(digest(app / name) == value for name, value in expected.items()),
            "Bootstrap source changed")
    with zipfile.ZipFile(app / ".distribution" / PYTHON_NAME) as archive:
        members = {entry.filename: hashlib.sha256(archive.read(entry)).hexdigest()
                   for entry in archive.infolist()}
    actual = {path.relative_to(target / "python").as_posix(): digest(path)
              for path in (target / "python").rglob("*") if path.is_file()}
    require(not any(path.is_symlink() for path in target.rglob("*")) and actual == members,
            "Bootstrap Python is not the exact pinned distribution")
    require({path.name for path in target.iterdir()} == {
        "python", "bootstrap_download.py", "bootstrap-profile.iss", "bootstrap-inputs.json"},
        "Unexpected bootstrap component")
    for name in ("bootstrap_download.py", "bootstrap-profile.iss"):
        require(digest(target / name) == expected["installer/windows/" + name],
                "Bootstrap component differs from reviewed source")
    return expected


def reuse(stage, output, *, fetcher=None):
    """Reuse only the latest official EXE with the identical complete bootstrap input set."""
    expected = verify_stage(stage)
    release = fetcher or load_module("bootstrap_release_inputs", ROOT / ".github/scripts/release_inputs.py")
    metadata = release.fetch_json(f"https://api.github.com/repos/{release.REPOSITORY}/releases/latest")
    require(metadata.get("draft") is False and metadata.get("prerelease") is False,
            "Bootstrap reuse requires a stable public release")
    tag = metadata.get("tag_name", "")
    require(re.fullmatch(r"v\d+\.\d+\.\d+", tag), "Unexpected bootstrap baseline tag")
    assets = {asset["name"]: asset for asset in metadata["assets"]}
    require(len(assets) == len(metadata["assets"]), "Duplicate baseline release assets")
    if "installer-build.json" not in assets:
        return False

    def download(name, destination, maximum):
        asset = assets[name]
        checksum = asset.get("digest", "")
        url = f"https://github.com/{release.REPOSITORY}/releases/download/{tag}/{name}"
        require(isinstance(checksum, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", checksum)
                and asset.get("browser_download_url") == url,
                "Baseline asset identity is invalid")
        return release.checked_download(url, destination, checksum[7:], asset["size"], maximum=maximum)

    with tempfile.TemporaryDirectory(prefix="nipat-bootstrap-reuse-") as directory:
        record = json.loads(download("installer-build.json", Path(directory) / "build.json", 1024 * 1024).read_bytes())
        if (record.get("schema_version") != 2 or record.get("distribution") != "online-bootstrap"
                or record.get("bootstrap_version") != BOOTSTRAP_VERSION
                or record.get("bootstrap_inputs_sha256") != expected):
            return False
        asset = assets.get("NIPAT-Setup.exe", {})
        require(record.get("file") == "NIPAT-Setup.exe" and record.get("version") == tag[1:]
                and asset.get("digest") == "sha256:" + record.get("sha256", "")
                and asset.get("size") == record.get("size"), "Baseline bootstrap record differs from its asset")
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        require(not (output / "NIPAT-Setup.exe").exists(), "Bootstrap output already exists")
        download("NIPAT-Setup.exe", output / "NIPAT-Setup.exe", 64 * 1024 * 1024)
    return True


def record(stage, output):
    stage, output = Path(stage), Path(output)
    inputs = verify_stage(stage)
    manifest_path = stage / "app/.distribution/installer-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    payload = load_module("bootstrap_payload", ROOT / "installer/windows/desktop_payload.py")
    inventory = (stage / "app/.distribution/application-files.json").read_bytes()
    payload_record = payload.verify(output / payload.filename(manifest["version"]), manifest, inventory)
    require(json.loads((output / "windows-payload-build.json").read_bytes()) == payload_record,
            "Desktop payload build record changed")
    setup = output / "NIPAT-Setup.exe"
    require(setup.is_file() and not setup.is_symlink() and 0 < setup.stat().st_size < 64 * 1024 * 1024,
            "Stable bootstrap is missing or exceeds its 64 MiB limit")
    result = {
        "schema_version": 2, "distribution": "online-bootstrap", "bootstrap_version": BOOTSTRAP_VERSION,
        "version": manifest["version"], "source_commit": manifest["source_commit"],
        "file": setup.name, "sha256": digest(setup), "size": setup.stat().st_size,
        "installer_manifest_sha256": digest(manifest_path),
        "application_inventory_sha256": hashlib.sha256(inventory).hexdigest(),
        "installation_profile": manifest["installation_profile"],
        "bootstrap_inputs_sha256": inputs, "payload_record": payload_record,
    }
    (output / "installer-build.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(manifest_path, output / "installer-manifest.json")
    (output / "SHA256SUMS").write_text(f"{result['sha256']}  NIPAT-Setup.exe\n", encoding="ascii")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "reuse", "record"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    if args.command in {"reuse", "record"}:
        require(args.output is not None, "Output directory is required")
    result = (prepare(args.stage) if args.command == "prepare" else
              verify_stage(args.stage) if args.command == "verify" else
              reuse(args.stage, args.output) if args.command == "reuse" else record(args.stage, args.output))
    if args.command == "reuse" and args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"reused={str(result).lower()}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
