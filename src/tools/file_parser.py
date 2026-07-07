"""Pure local file parsing for uploaded CSV/Excel files.

No FastAPI/session-store coupling — this module only turns raw bytes (plus a
filename) into a pandas DataFrame, or raises a clear, specific exception when
that isn't possible. Best-effort partial recovery of malformed rows is
explicitly out of scope for Phase 1 (see `spec/roadmap.md` Phase 2 —
`malformed-file-handling`).
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath

import pandas as pd

_SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class UnsupportedFileTypeError(Exception):
    """Raised when the uploaded file's extension is not one we parse."""


class FileParseError(Exception):
    """Raised when the file is the right type but is unreadable/corrupt."""


def _extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def parse_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse raw file bytes into a DataFrame.

    Args:
        file_bytes: the raw uploaded file content.
        filename: the original filename (used only to determine the
            extension/format — never persisted here).

    Returns:
        A parsed `pandas.DataFrame`.

    Raises:
        UnsupportedFileTypeError: the filename's extension is not
            `.csv`, `.xlsx`, or `.xls`.
        FileParseError: the file has a supported extension but its
            content is genuinely unreadable/corrupt (nothing salvageable).
    """
    extension = _extension(filename)

    if extension not in _SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{extension or filename}'. "
            f"Supported types: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}."
        )

    buffer = io.BytesIO(file_bytes)

    try:
        if extension == ".csv":
            df = pd.read_csv(buffer)
        else:
            df = pd.read_excel(buffer, engine="openpyxl")
    except UnsupportedFileTypeError:
        raise
    except Exception as exc:  # pandas/openpyxl raise a wide variety of types
        raise FileParseError(
            f"Could not parse '{filename}' as a valid {extension} file: {exc}"
        ) from exc

    return df
