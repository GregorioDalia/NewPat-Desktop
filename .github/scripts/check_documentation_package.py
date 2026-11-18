"""Check documented CLI syntax and a small Windows archive built with real shipping text."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import shlex
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from nipat.cli import build_parser
from installer.windows import testing_package, zip_package
from scripts.distribution_support import sha256_file, source_files

# Current user/developer guides with directly invocable CLI examples. Historical
# release notes describe the interfaces of earlier releases.
GUIDES = ("README.md", "docs/GUIDA_UTILIZZO.md", "docs/CATALOGO_SCIENTIFICO.md",
          "docs/DISTRIBUZIONE.md", "docs/ESECUZIONI.md", "docs/INSTALLATORE_LINUX.md",
          "docs/INSTALLATORE_WINDOWS.md", "docs/PERFORMANCE.md", "docs/RISORSE.md")
LAUNCH = re.compile(r"^(?:newpat|python -m nipat|& \$newpat)(?:\s+|$)")


def commands(text):
    """Yield arguments from fenced shell examples; never evaluate any command."""
    lines = text.splitlines()
    fence = None
    language = ""
    for i, raw in enumerate(lines):
        line = raw.strip()
        marker = re.fullmatch(r"(`{3,}|~{3,})\s*([\w+-]*)", line)
        if marker:
            if fence is None:
                fence, language = marker.groups()
            elif not marker[2] and marker[1].startswith(fence):
                fence, language = None, ""
            continue
        if language not in {"bash", "sh", "powershell"}:
            continue
        start = LAUNCH.match(line)
        if not start:
            continue
        argument_text = line[start.end():]
        continuation = "`" if language == "powershell" else "\\"
        j = i
        while argument_text.endswith(continuation):
            j += 1
            if j == len(lines) or lines[j].strip().startswith(fence):
                raise ValueError(f"Unfinished command on line {i + 1}")
            argument_text = argument_text[:-1] + " " + lines[j].strip()
        yield i + 1, shlex.split(argument_text)


def check_examples(source, parser):
    errors = StringIO()
    count = 0
    for number, arguments in commands(source.read_text(encoding="utf-8")):
        with redirect_stdout(StringIO()), redirect_stderr(errors):
            try:
                parser.parse_args(arguments)
            except SystemExit as exc:
                if exc.code != 0:
                    raise ValueError(f"{source}:{number}: {errors.getvalue().strip()}") from exc
        count += 1
    return count


def check_members(package, sources):
    with ZipFile(package) as archive:
        for member, source in sources.items():
            if archive.read(member) != source.read_bytes():
                raise ValueError(f"{member} in {package.name} differs from {source}")


def check_package(root, work):
    # Only the text slice of the real installer allowlist is staged here. The
    # release workflow separately checks the full packages and runtime assets.
    included = {p.relative_to(root).as_posix(): p for p in source_files(root)}
    needed = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "docs/GUIDA_UTILIZZO.md",
              "installer/windows/zip-readme.txt", "installer/windows/testing-readme.txt"}
    missing = needed - included.keys()
    if missing:
        raise ValueError(f"Missing required distribution texts: {sorted(missing)}")
    files = {name: path for name, path in included.items()
             if path.suffix.lower() == ".md" or name in needed or name in zip_package.ROOT_FILES.values()}
    stage = work / "stage"
    app = stage / "app"
    for name, source in files.items():
        dest = app / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
    metadata = app / ".distribution"
    metadata.mkdir()
    # Fixed fixture identity is local to the packaging test, never release evidence.
    manifest = {"version": "0.9.0", "source_commit": "a" * 40, "assets": {},
                "source_sha256": {k: sha256_file(v) for k, v in files.items()}}
    manifest_path = metadata / "installer-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    hashes = {**manifest["source_sha256"], ".distribution/installer-manifest.json": sha256_file(manifest_path)}
    inventory = {"schema_version": 1, "installation_channel": "desktop", "source_commit": manifest["source_commit"],
                 "files": [{"path": key, "sha256": value} for key, value in hashes.items()]}
    (metadata / "application-files.json").write_text(json.dumps(inventory), encoding="utf-8")
    output = work / "packages"
    complete = zip_package.build(stage, work, output)
    members = {"app/" + name: path for name, path in files.items()}
    members["LEGGIMI.txt"] = root / "installer/windows/zip-readme.txt"
    check_members(output / complete["file"], members)
    for name in ("NIPAT-Setup.exe", "NIPAT-0.9.0-Windows-payload.zip"):
        (output / name).write_bytes(b"package identity fixture")
    testing = testing_package.build(root / "installer/windows", output, manifest)
    check_members(output / testing["file"], {"LEGGIMI.txt": root / "installer/windows/testing-readme.txt"})
    return len(files)


def main():
    parser = build_parser()
    count = sum(check_examples(ROOT / name, parser) for name in GUIDES)
    if not count:
        raise ValueError("No documented CLI examples were checked")
    with tempfile.TemporaryDirectory() as work:
        members = check_package(ROOT, Path(work))
    print(f"Validated {count} CLI examples and {members} distribution inputs in archive fixtures.")


if __name__ == "__main__":
    main()
