"""Names used for the NewPat application and its release artifacts."""

import re


PRODUCT_NAME = "NewPat"
APPLICATION_NAME = PRODUCT_NAME
MACOS_APP_NAME = "NewPat.app"
CLI_NAME = "newpat"
TECHNICAL_PRODUCT_ID = "newpat-desktop"
WINDOWS_PACKAGE_GENERATION = 2


def _validate_version(version: str) -> None:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?", version):
        raise ValueError("Invalid Windows package version")


def windows_complete_filename(version: str) -> str:
    _validate_version(version)
    return f"NewPat-{version}-Windows-complete.zip"


def windows_testing_filename(version: str) -> str:
    _validate_version(version)
    return f"NewPat-{version}-Testing-installer.zip"


def windows_feed_filename(method: str, version: str) -> str:
    if method not in {"zip", "bootstrap"}:
        raise ValueError("Unknown Windows update method")
    _validate_version(version)
    return f"update-manifest-windows-{method}-v{WINDOWS_PACKAGE_GENERATION}.json"
