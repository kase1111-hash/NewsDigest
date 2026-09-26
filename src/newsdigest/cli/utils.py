"""Shared helpers for CLI commands."""

import sys
from pathlib import Path


def read_source(source: str) -> str:
    """Resolve a SOURCE argument to content the extractor accepts.

    "-" reads standard input, a path to an existing file is read from disk,
    and anything else (a URL or raw text) is returned unchanged.

    Args:
        source: SOURCE argument as given on the command line.

    Returns:
        File or stdin contents, or the argument itself.
    """
    if source == "-":
        return sys.stdin.read()
    try:
        path = Path(source)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        # Raw text can be too long for a file name or contain NUL bytes
        pass
    return source
