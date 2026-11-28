"""Bind both native macOS packages to the reviewed cross-platform release.

The native package checks prove the packaged bytes and bundled client. They do
not claim that a Lima VM or a scientific analysis ran on a researcher's Mac.
"""

import hashlib
import json
from pathlib import Path
import re


ARCHITECTURES = ("arm64", "x86_64")
CHECKS = {
    "package-sha256", "full-payload-inventory", "scientific-archive-reuse",
    "source-inventory", "installer-os-and-architecture", "ad-hoc-code-signatures",
    "native-python", "native-lima", "lima-virtualization-entitlement",
    "packaged-cli-version", "generated-lima-template",
}
NOT_TESTED = {
    "clean-installation", "first-launch-vm-provisioning", "scientific-execution",
    "upgrade", "runtime-removal", "gatekeeper-policy",
}
MAX_PACKAGE_BYTES = 2 * 1024**3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def requires_macos(version):
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:(?:a|b|rc)[0-9]+)?", version or "")
    return bool(match and tuple(map(int, match.groups())) >= (0, 8, 2))


def digest(path):
    require(path.is_file() and not path.is_symlink(), f"Missing or redirected release input: {path.name}")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    digest(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_package(directory, architecture, manifest):
    require(architecture in ARCHITECTURES, "Unsupported macOS release architecture")
    require(requires_macos(manifest.get("version")), "The official macOS release contract starts at 0.8.2")
    require(manifest.get("installation_profile", {}).get("channel") == "desktop",
            "Official macOS releases require the desktop installation channel")
    name = f"NewPat-{manifest['version']}-macos-{architecture}.pkg"
    package = directory / name
    package_hash = digest(package)
    size = package.stat().st_size
    require(0 < size < MAX_PACKAGE_BYTES, "Invalid macOS installer size")
    require({path.name for path in directory.glob("*.pkg")} == {name}, "Ambiguous macOS release packages")
    report_path = directory / "macos-package-verification.json"
    report = read_json(report_path)
    version_parts = tuple(map(int, re.match(r"([0-9]+)\.([0-9]+)\.([0-9]+)", manifest["version"]).groups()))
    native = version_parts >= (0, 9, 99)
    engine = manifest
    native_record = {}
    if native and architecture == "arm64":
        identity = directory / "arm64-scientific.json"
        engine = read_json(identity)
        asset = engine.get("assets", {}).get("scientific_image", {})
        require(all(engine.get(key) == manifest[key] for key in (
                    "version", "release_tag", "source_commit", "source_sha256", "installation_profile"))
                and engine.get("schema_version") == 1 and engine.get("scientific_platform") == "linux/arm64"
                and re.fullmatch(r"sha256:[a-f0-9]{64}", str(engine.get("runtime_image")))
                and engine["runtime_image"] != manifest["runtime_image"]
                and asset.get("file") == f"newpat-scientific-{manifest['version']}-arm64.tar.gz"
                and re.fullmatch(r"[a-f0-9]{64}", str(asset.get("sha256")))
                and asset["sha256"] != manifest["assets"]["scientific_image"]["sha256"]
                and type(asset.get("size")) is int and 0 < asset["size"] < MAX_PACKAGE_BYTES
                and re.fullmatch(r"[a-f0-9]{64}", str(engine.get("engine_description_sha256"))),
                "Unqualified ARM64 scientific identity or source inventory")
        native_record = {"scientific_identity_sha256": digest(identity),
                         "scientific_archive_sha256": asset["sha256"], "runtime_image": engine["runtime_image"]}
    expected = {
        "schema_version": 1, "verified": True, "platform": "darwin",
        "architecture": architecture, "version": manifest["version"],
        "source_commit": manifest["source_commit"], "package_sha256": package_hash,
        "scientific_asset_sha256": engine["assets"]["scientific_image"]["sha256"],
        "runtime_image": engine["runtime_image"], "runtime_vm_qualified": False,
    }
    if native:
        expected["scientific_platform"] = "linux/arm64" if architecture == "arm64" else "linux/amd64"
    require(isinstance(report, dict) and set(report) == set(expected) | {"checks", "not_tested"}
            and all(type(report.get(key)) is type(value) and report.get(key) == value
                    for key, value in expected.items()),
            f"macOS {architecture} verification is not bound to this build")
    checks = CHECKS
    if native:
        checks = checks | {"docker-archive-architecture", "rosetta-disabled"}
        checks = checks | {"newpat-clean-install-identity"}
    for key, values in (("checks", checks), ("not_tested", NOT_TESTED)):
        items = report[key]
        require(isinstance(items, list) and all(isinstance(item, str) for item in items)
                and len(items) == len(values) and set(items) == values,
                f"macOS {architecture} {key} are incomplete or misrepresent qualification")
    record_path = directory / "macos-installer-build.json"
    record = read_json(record_path)
    build_expected = {
        "schema_version": 1, "distribution": "self-contained-macos-lima",
        "version": manifest["version"], "source_commit": manifest["source_commit"],
        "architecture": architecture, "platform": "darwin", "package": name,
        "package_sha256": package_hash, "package_size": size,
        "scientific_asset_sha256": expected["scientific_asset_sha256"],
        "runtime_image": engine["runtime_image"], "runtime_vm_qualified": False,
        "manual_acceptance": False, "signing": "ad-hoc-app; unsigned-installer; not-notarized",
    }
    if native:
        build_expected["scientific_platform"] = expected["scientific_platform"]
    require(isinstance(record, dict) and set(record) == set(build_expected) | {"payload_inventory"}
            and all(type(record.get(key)) is type(value) and record.get(key) == value
                    for key, value in build_expected.items())
            and isinstance(record["payload_inventory"], dict) and record["payload_inventory"],
            f"macOS {architecture} build record differs from the native package verification")
    return {"file": name, "sha256": package_hash, "size": size,
            "verification_sha256": digest(report_path), "build_record_sha256": digest(record_path),
            "runtime_vm_qualified": False, **native_record}


def extend_installer_set(installer_set, macos_directories, manifest):
    """Return one verified record for Windows, Ubuntu and both native Macs."""
    require(requires_macos(manifest.get("version")), "This build does not use the four-platform contract")
    require(isinstance(macos_directories, dict) and set(macos_directories) == set(ARCHITECTURES),
            "Both macOS installer directories are required")
    require(installer_set.get("version") == manifest["version"]
            and installer_set.get("source_commit") == manifest["source_commit"]
            and installer_set.get("scientific_archive") == {
                field: manifest["assets"]["scientific_image"][field] for field in ("file", "sha256", "size")},
            "Windows/Ubuntu and macOS sources or scientific archives differ")
    require(not any(key.startswith("macos_") for key in installer_set), "macOS evidence is already attached")
    result = dict(installer_set)
    result.update({f"macos_{architecture}": verify_package(Path(macos_directories[architecture]), architecture, manifest)
                   for architecture in ARCHITECTURES})
    return result
