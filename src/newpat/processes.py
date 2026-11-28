"""Process options for internal, noninteractive client work."""
from __future__ import annotations

import os
import subprocess


def background_process_options() -> dict[str, int]:
    """Keep background Windows helpers inside the desktop UI and logs.

    A GUI launched by pythonw has no console to inherit. Without this flag,
    console helpers such as wsl.exe create a separate visible window. Do not
    use these options for the explicit interactive setup/update handoff.
    """
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}
