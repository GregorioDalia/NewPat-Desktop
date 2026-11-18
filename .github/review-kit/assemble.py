"""Assemble the inputs for an offline native build on an Apple Silicon Mac."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


SOURCE_COMMIT = "aec701f6f14bbd0f770dd79812b085be1e17096c"
KIT_NAME = "NewPat-0.9.8-Apple-Silicon"


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def main():
    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    source = workspace / "release"
    artifacts = workspace / "scientific"
    output = workspace / "delivery"
    output.mkdir()
    sys.path.insert(0, str(source / "scripts"))
    import build_macos_installer as builder

    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        kit = work / KIT_NAME
        support = kit / "support"
        assets = support / "assets"
        assets.mkdir(parents=True)

        # Make a fresh, offline checkout. No Actions credentials or local configuration are copied.
        clean = work / "source"
        run("git", "init", "--quiet", str(clean))
        run("git", "-C", str(clean), "fetch", "--quiet", "--no-tags", "--depth=1", str(source), SOURCE_COMMIT)
        run("git", "-C", str(clean), "checkout", "--quiet", "--detach", "FETCH_HEAD")
        (clean / ".git/FETCH_HEAD").unlink()
        run("tar", "-czf", str(support / "source.tar.gz"), "-C", str(work), "source")

        manifest, _, scientific, _ = builder.verified_inputs(
            clean, artifacts / "installer-manifest.json", artifacts / "engine-description.json"
        )
        if manifest["version"] != "0.9.8" or manifest["source_commit"] != SOURCE_COMMIT:
            raise ValueError("Unexpected version or scientific archive provenance")
        for item in (scientific, artifacts / "installer-manifest.json", artifacts / "engine-description.json"):
            shutil.copyfile(item, assets / item.name)
        dependencies = json.loads((clean / "installer/macos/dependencies.json").read_text())["architectures"]["arm64"]
        for component in ("python", "lima"):
            archive = builder.dependency_archive(dependencies[component], work, None)
            archive.rename(support / f"{component}.tar.gz")

        script = kit / "Prepara-NewPat.command"
        shutil.copyfile(Path(__file__).with_name(script.name), script)
        script.chmod(0o755)
        run("bash", "-n", str(script))
        checksum_lines = []
        for path in sorted(p for p in kit.rglob("*") if p.is_file()):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            checksum_lines.append(f"{digest}  {path.relative_to(kit)}\n")
        (kit / "SHA256SUMS").write_text("".join(checksum_lines))

        archive = output / f"{KIT_NAME}.tar.gz"
        run("tar", "-cf", str(archive), "--use-compress-program=gzip -1", "-C", str(work), KIT_NAME)

        # Re-open the deliverable and check the source, hashes, native inputs and executable mode.
        restored = work / "restored"
        restored.mkdir()
        run("tar", "-xzf", str(archive), "-C", str(restored))
        restored_kit = restored / KIT_NAME
        run("sha256sum", "-c", "SHA256SUMS", cwd=restored_kit)
        if not os.access(restored_kit / script.name, os.X_OK):
            raise ValueError("The double-click launcher lost its executable mode")
        run("tar", "-xzf", str(restored_kit / "support/source.tar.gz"), "-C", str(restored))
        restored_assets = restored_kit / "support/assets"
        builder.verified_inputs(restored / "source", restored_assets / "installer-manifest.json",
                                restored_assets / "engine-description.json")
        for component in ("python", "lima"):
            builder.dependency_archive(dependencies[component], restored, restored_kit / f"support/{component}.tar.gz")


if __name__ == "__main__":
    main()
