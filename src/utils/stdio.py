"""Subprocess standard I/O helpers."""

from __future__ import annotations

import sys

DEFAULT_TEXT_ENCODING = "utf-8"
PYTHON_UTF8_MODE = "1"


def configure_standard_streams(encoding: str = DEFAULT_TEXT_ENCODING) -> None:
    """Force stdout/stderr to a predictable text encoding when supported."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding=encoding)
