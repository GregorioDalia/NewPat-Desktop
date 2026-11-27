"""Public product identity, independent of persistent compatibility identifiers.

Existing data roots, package receipts, runtime ownership tokens and update
manifests retain their technical NIPAT identities during the NewPat transition.
"""

import re


PRODUCT_NAME = "NewPat"
LEGACY_PRODUCT_NAME = "NIPAT"
APPLICATION_NAME = PRODUCT_NAME
MACOS_APP_NAME = "NewPat.app"
LEGACY_MACOS_APP_NAME = "NIPAT Desktop.app"
CLI_NAME = "newpat"
TECHNICAL_PRODUCT_ID = "nipat-desktop"


def canonical_asset_name(name: str) -> str:
    """Return the public download alias; never rewrite arbitrary paths or IDs."""
    if name.startswith("NIPAT-"):
        return "NewPat-" + name[len("NIPAT-"):]
    if name.startswith("nipat-desktop_"):
        return "newpat-desktop_" + name[len("nipat-desktop_"):]
    return name


def windows_package_generation(version: str) -> int:
    parts = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?", version)
    if parts is None:
        raise ValueError("Invalid Windows package version")
    return 2 if tuple(map(int, parts.groups())) >= (0, 9, 10) else 1


def windows_complete_filename(version: str) -> str:
    suffix = "complete" if windows_package_generation(version) == 2 else "completo"
    return f"NIPAT-{version}-Windows-{suffix}.zip"


def windows_testing_filename(version: str) -> str:
    suffix = "installer" if windows_package_generation(version) == 2 else "installazione"
    return f"NIPAT-{version}-Testing-{suffix}.zip"


def windows_feed_filename(method: str, version: str) -> str:
    if method not in {"zip", "bootstrap"}:
        raise ValueError("Unknown Windows update method")
    suffix = "-v2" if windows_package_generation(version) == 2 else ""
    return f"update-manifest-windows-{method}{suffix}.json"
