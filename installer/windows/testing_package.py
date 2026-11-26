"""Release-specific testing entrypoint; the frozen stable bootstrap stays unchanged."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from nipat.branding import windows_complete_filename, windows_package_generation, windows_testing_filename


def sources(version):
    if windows_package_generation(version) == 1:
        return {"INSTALLA-NewPat-TESTING.cmd": "testing-install.cmd", "LEGGIMI.txt": "testing-readme.txt",
                "install-testing.ps1": "install-testing.ps1"}
    return {"INSTALL-NewPat-Testing.cmd": "testing-install.cmd", "README.txt": "testing-readme.txt",
            "install-testing.ps1": "install-testing.ps1", "install-profile.ps1": "install-profile.ps1",
            "install-layout.ps1": "install-layout.ps1"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def filename(version):
    if not re.fullmatch(r"0\.9\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version):
        raise ValueError("Testing entrypoints require a 0.9 release")
    return windows_testing_filename(version)


def metadata(output, manifest):
    version = manifest["version"]
    filename(version)
    if not re.fullmatch(r"[a-f0-9]{40}", manifest["source_commit"]):
        raise ValueError("Invalid testing source commit")
    value = {"schema_version": 1, "channel": "testing", "version": version,
             "source_commit": manifest["source_commit"]}
    for role, name in {"complete_zip": windows_complete_filename(version),
                       "payload": f"NIPAT-{version}-Windows-payload.zip",
                       "setup": "NIPAT-Setup.exe"}.items():
        path = output / name
        value[role] = {"file": name, "size": path.stat().st_size, "sha256": digest(path)}
    return value


def expected_contents(source, output, manifest):
    result = {name: (source / relative).read_bytes() for name, relative in sources(manifest["version"]).items()}
    result["testing-release.json"] = (json.dumps(metadata(output, manifest), indent=2) + "\n").encode()
    return result


def verify(package, source, output, manifest):
    expected = expected_contents(source, output, manifest)
    with zipfile.ZipFile(package) as archive:
        if len(archive.infolist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError("Unexpected testing entrypoint archive contents")
        for name, content in expected.items():
            if archive.read(name) != content:
                raise ValueError("Testing entrypoint differs from reviewed source or payload identity")
    return {"schema_version": 1, "distribution": "release-specific-testing-entrypoint",
            "version": manifest["version"], "source_commit": manifest["source_commit"],
            "file": package.name, "sha256": digest(package), "size": package.stat().st_size}


def build(source, output, manifest):
    target = output / filename(manifest["version"])
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in expected_contents(source, output, manifest).items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return verify(target, source, output, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    print(json.dumps(build(Path(__file__).resolve().parent, args.output, manifest), indent=2))


if __name__ == "__main__":
    main()
