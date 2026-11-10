"""Upload and read caps. The checker keeps schedule bytes in memory only."""

from pathlib import Path

MAX_FILE_BYTES = 2_000_000
MAX_FILES = 6
MAX_TOTAL_BYTES = 8_000_000


class InputError(ValueError):
    """A local path or upload cannot be checked."""


def read_limited(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    """Read one file if it is a regular file at or under the byte cap."""
    if not path.is_file():
        raise InputError(f"{path} is not a file.")
    size = path.stat().st_size
    if size > limit:
        raise InputError(f"{path} is {size} bytes, above the {limit} byte cap.")
    data = path.read_bytes()
    if len(data) > limit:
        raise InputError(f"{path} is {len(data)} bytes, above the {limit} byte cap.")
    return data
