"""Installation channels and release downloads use the same product identity."""
import pytest

from newpat import __version__
from newpat.branding import PRODUCT_NAME
from newpat.cli import build_parser
from newpat.distribution import WINDOWS_DIRECTORY, UNIX_DIRECTORY
from newpat.updates import UpdateError, WEB, _validated_asset


def test_product_names_and_installation_roots():
    assert PRODUCT_NAME == "NewPat"
    assert build_parser().prog == "newpat"
    assert WINDOWS_DIRECTORY == "NewPat-Desktop"
    assert UNIX_DIRECTORY == "newpat-desktop"


def test_windows_download_must_use_the_current_release_name():
    version = __version__
    def asset(name):
        return {"platform": "windows-x86_64", "name": name, "size": 100,
                "sha256": "a" * 64, "url": f"{WEB}/releases/download/v{version}/{name}"}
    assert _validated_asset(asset("NewPat-Setup.exe"), version, "v" + version).name == "NewPat-Setup.exe"
    with pytest.raises(UpdateError):
        _validated_asset(asset("NIPAT-Setup.exe"), version, "v" + version)
