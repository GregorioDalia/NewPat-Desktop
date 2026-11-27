"""Resolve build inputs against the source layout of the release being verified."""
import re


def uses_newpat_layout(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:(?:a|b|rc)\d+)?", version)
    if not match:
        raise ValueError("Invalid source layout version")
    return tuple(map(int, match.groups())) >= (0, 9, 99)


def source_path(path, version):
    """Historical acceptance records and frozen references retain their original file names."""
    if not uses_newpat_layout(version):
        return path
    if path.startswith(("src/nipat_scientific/", "lib/nipat_scientific/")):
        return path.replace("/nipat_scientific/", "/newpat_scientific/", 1)
    if path.startswith("assets/branding/nipat-"):
        return path.replace("/nipat-", "/newpat-", 1)
    return {"src/nipat/cli.py": "src/newpat/cli.py",
            "installer/windows/NIPAT.iss": "installer/windows/NewPat.iss"}.get(path, path)
