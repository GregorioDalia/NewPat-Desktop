"""Internal helpers keep log pipes and cleanup isolation without extra consoles."""
import subprocess
import sys
from unittest.mock import patch

from nipat.processes import background_process_options
from nipat.execution.transport import cleanup_process_options


def test_windows_cleanup_preserves_process_group_and_hides_console():
    with patch("nipat.processes.os.name", "nt"):
        options = background_process_options()
        cleanup = cleanup_process_options()
    assert options == {"creationflags": 0x08000000}
    assert cleanup == {"creationflags": 0x08000200}


def test_posix_cleanup_keeps_session_and_normal_children_unchanged():
    with patch("nipat.processes.os.name", "posix"):
        assert background_process_options() == {}
        assert cleanup_process_options() == {"start_new_session": True}


def test_background_child_preserves_captured_output_and_failure():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; print('progress'); print('detail', file=sys.stderr); sys.exit(7)"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        **background_process_options(),
    )
    assert result.returncode == 7
    assert result.stdout.strip() == "progress"
    assert result.stderr.strip() == "detail"
