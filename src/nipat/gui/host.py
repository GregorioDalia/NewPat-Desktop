"""Select the platform's embedded native view, never the default browser."""
import sys


def native_host():
    if sys.platform == "win32":
        from . import windows_host
        return windows_host
    if sys.platform == "darwin":
        from . import macos_host
        return macos_host
    if sys.platform == "linux":
        from . import linux_host
        return linux_host
    raise RuntimeError("La GUI NIPAT supporta Windows, Ubuntu e macOS.")
