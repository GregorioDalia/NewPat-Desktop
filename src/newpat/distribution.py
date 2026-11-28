"""Installation identity for the official desktop distribution."""

import re


_STABLE_VERSION = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}")

CHANNEL = "desktop"
WINDOWS_DIRECTORY = "NewPat-Desktop"
UNIX_DIRECTORY = "newpat-desktop"


def supported_stable_release(version: object) -> bool:
    """Official package versions start at the NewPat 0.9.99 clean installation."""
    if not isinstance(version, str) or not _STABLE_VERSION.fullmatch(version):
        return False
    return tuple(map(int, version.split("."))) >= (0, 9, 99)
