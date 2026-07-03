import io

import pandas as pd
import pytest

from tools.file_parser import FileParseError, UnsupportedFileTypeError, parse_file


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["North", "South", "East"],
            "revenue": [100.5, 200.25, 300.0],
        }
    )


def test_parse_valid_csv_returns_correct_shape_and_columns():
    df = _sample_df()
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    result = parse_file(csv_bytes, "sales.csv")

    assert list(result.columns) == ["region", "revenue"]
    assert len(result) == 3
    assert result["revenue"].sum() == pytest.approx(600.75)


def test_parse_valid_xlsx_returns_correct_shape_and_columns():
    df = _sample_df()
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    xlsx_bytes = buffer.getvalue()

    result = parse_file(xlsx_bytes, "sales.xlsx")

    assert list(result.columns) == ["region", "revenue"]
    assert len(result) == 3
    assert result["revenue"].sum() == pytest.approx(600.75)


def test_unsupported_extension_raises_unsupported_file_type_error():
    with pytest.raises(UnsupportedFileTypeError):
        parse_file(b"just some text content", "notes.txt")


def test_unsupported_extension_json_raises_unsupported_file_type_error():
    with pytest.raises(UnsupportedFileTypeError):
        parse_file(b'{"a": 1}', "data.json")


def test_garbage_bytes_with_csv_extension_raises_file_parse_error():
    # Genuinely corrupt/binary content that is not valid CSV at all —
    # a NUL-laden binary blob has no valid delimiter/row structure.
    garbage = bytes(range(256)) * 4
    with pytest.raises(FileParseError):
        parse_file(garbage, "corrupt.csv")


def test_corrupted_beyond_repair_xlsx_bytes_raise_file_parse_error():
    # A byte stream that merely has an .xlsx extension but is not a valid
    # zip/OOXML container at all (e.g. truncated/garbled) is unreadable.
    # Full password-protected-workbook coverage is exercised in Phase 2's
    # `malformed-file-handling` slice fixtures (tests/fixtures/protected.xlsx)
    # per spec/roadmap.md — out of scope here.
    corrupted = b"PK\x03\x04not a real zip/xlsx container" + b"\x00" * 50
    with pytest.raises(FileParseError):
        parse_file(corrupted, "protected.xlsx")


def test_empty_bytes_with_csv_extension_raises_file_parse_error():
    with pytest.raises(FileParseError):
        parse_file(b"", "empty.csv")
