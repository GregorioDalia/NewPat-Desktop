"""Client errors and compatibility imports for shared scientific validation."""

from nipat_scientific.errors import NipatError, ValidationError

__all__ = ["NipatError", "ValidationError", "RuntimeExecutionError", "RuntimeInterruptedError", "Cancelled"]


class Cancelled(Exception):
    """Leave the current guided action and return to the main menu."""


class RuntimeExecutionError(NipatError):
    """Raised when Docker or a scientific command fails."""


class RuntimeInterruptedError(RuntimeExecutionError):
    """The runtime stopped during execution without a user cancellation request."""
