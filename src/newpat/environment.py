"""Read public client settings while accepting earlier launcher environments."""

import os


def setting(name, default=None):
    """The NewPat spelling takes precedence, including an explicitly empty value."""
    return os.environ.get("NEWPAT_" + name, os.environ.get("NIPAT_" + name, default))
