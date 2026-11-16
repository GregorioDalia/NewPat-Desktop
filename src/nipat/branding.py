"""Public product identity, independent of persistent compatibility identifiers.

Existing data roots, package receipts, runtime ownership tokens and update
manifests retain their technical NIPAT identities during the NewPat transition.
"""

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
