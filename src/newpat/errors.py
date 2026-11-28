"""Client errors and compatibility imports for shared scientific validation."""

from newpat_scientific.errors import NewPatError, ValidationError

__all__ = ["NewPatError", "ValidationError", "RuntimeExecutionError", "RuntimeInterruptedError", "Cancelled"]


class Cancelled(Exception):
    """Leave the current guided action and return to the main menu."""


class RuntimeExecutionError(NewPatError):
    """Raised when Docker or a scientific command fails."""


class RuntimeInterruptedError(RuntimeExecutionError):
    """The runtime stopped during execution without a user cancellation request."""
