"""Installation identity for the official desktop distribution."""

import re

CHANNEL = "desktop"
WINDOWS_DIRECTORY = "NIPAT-Desktop"
UNIX_DIRECTORY = "nipat-desktop"
EXPERIMENT_URL = "https://github.com/GregorioDalia/nipat-desktop/releases"


def is_experimental_version(version: str) -> bool:
    """Explicit testing builds must never consume the stable desktop feed.

    A final-looking version number does not promote a testing release. Add a
    version deliberately; release acceptance separately selects publication.
    """
    return isinstance(version, str) and bool(re.fullmatch(
        r"(?:0\.8\.\d+(?:a|b|rc)\d+|0\.9\.(?:0|1|5)(?:(?:a|b|rc)\d+)?)", version))
