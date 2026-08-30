"""Normalize expected failures and exit codes for screen mock entry points."""

from __future__ import annotations

from collections.abc import Callable


def run_screen_mock(
    factory: Callable[[], object],
    *,
    expected_errors: tuple[type[Exception], ...],
) -> int:
    """Run one mock factory and convert expected failures to CLI exit codes."""

    if not callable(factory):
        raise TypeError("factory must be callable")
    if not isinstance(expected_errors, tuple) or not all(
        isinstance(error_type, type)
        and issubclass(error_type, Exception)
        for error_type in expected_errors
    ):
        raise TypeError("expected_errors must be exception types")

    try:
        factory()
        return 0
    except expected_errors as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


__all__ = ["run_screen_mock"]
