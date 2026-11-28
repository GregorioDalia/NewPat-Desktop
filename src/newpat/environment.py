"""Environment settings shared by the NewPat client and its launchers."""

import os


def setting(name, default=None):
    return os.environ.get("NEWPAT_" + name, default)
