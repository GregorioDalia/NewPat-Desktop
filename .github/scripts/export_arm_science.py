"""Export the exact tagless image exercised by the ARM64 scientific oracles."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from native_evidence import verify_report

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts"))
import build_macos_installer as builder


def export(evidence, destination):
    source = builder.bundle.git_source(PROJECT)
    commit = source["commit"]
    if source["dirty"] or (evidence / "source-commit").read_text().strip() != commit:
        raise ValueError("The checkout differs from the qualified source")
    verify_report((evidence / "native-r.json").read_bytes(), commit)
    image = (evidence / "image-id").read_text().strip()
    details = builder.assets.inspect_image(image, architecture="arm64")
    if details["Id"] != image:
        raise ValueError("The image differs from the native oracle run")
    version = builder.assets.checked_version(PROJECT)
    destination.mkdir(parents=True)
    archive = destination / f"newpat-scientific-{version}-arm64.tar.gz"
    builder.assets.gzip_export(["docker", "image", "save", image], archive)
    description = destination / "engine-description.json"
    with description.open("xb") as output:
        subprocess.run(["docker", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--tmpfs", "/tmp",
                        "--platform=linux/arm64", image, "python3", "/opt/nipat/engine/main.py", "describe", "--json"],
                       check=True, stdout=output)
    asset = builder.assets.asset_metadata(archive, f"v{version}")
    asset.pop("url")
    manifest = {"schema_version": 1, "scientific_platform": "linux/arm64", "runtime_image": image,
                "version": version, "source_commit": commit, "release_tag": f"v{version}",
                "installation_profile": builder.assets.installation_profile(PROJECT),
                "engine_description_sha256": builder.bundle.sha256_file(description),
                "assets": {"scientific_image": asset},
                "source_sha256": {path.relative_to(PROJECT).as_posix(): builder.bundle.sha256_file(path)
                                  for path in builder.bundle.source_files(PROJECT)}}
    builder.validate_scientific_manifest(manifest, "arm64")
    (destination / "installer-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.evidence, args.output)
