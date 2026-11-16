"""Installation identity for the official desktop distribution."""

import re

CHANNEL = "desktop"
WINDOWS_DIRECTORY = "NIPAT-Desktop"
UNIX_DIRECTORY = "nipat-desktop"
EXPERIMENT_URL = "https://github.com/GregorioDalia/nipat-desktop/releases"


def is_experimental_version(version: str) -> bool:
    """These builds must never consume the stable desktop update feed."""
    return isinstance(version, str) and bool(re.fullmatch(
        r"(?:0\.8\.\d+(?:a|b|rc)\d+|0\.9\.[01](?:(?:a|b|rc)\d+)?)", version))
