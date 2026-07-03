import json

import numpy as np
import pandas as pd
import pytest

from tools.schema_profile import extract_schema_profile

CANARY = "canary-only-in-high-cardinality-column-xyz123"


def _fixture_df() -> pd.DataFrame:
    n = 60
    # (a) numeric column with a null
    revenue = [float(i * 10) for i in range(n)]
    revenue[5] = np.nan

    # (b) low-cardinality string column (<= 20 distinct)
    region = [["North", "South", "East", "West"][i % 4] for i in range(n)]

    # (c) high-cardinality string column (> 20 distinct, 50 unique free-text values)
    high_card = [f"free-text-note-{i}" for i in range(n)]
    high_card[3] = CANARY  # exists ONLY here, nowhere else in the frame

    return pd.DataFrame(
        {
            "revenue": revenue,
            "region": region,
            "notes": high_card,
        }
    )


def test_row_and_column_counts_are_correct():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    assert profile["row_count"] == len(df)
    assert profile["column_count"] == 3
    assert {c["name"] for c in profile["columns"]} == {"revenue", "region", "notes"}


def test_columns_report_dtype_and_null_counts():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    revenue_col = next(c for c in profile["columns"] if c["name"] == "revenue")
    assert revenue_col["null_count"] == 1
    assert revenue_col["non_null_count"] == len(df) - 1
    assert "float" in revenue_col["dtype"]


def test_numeric_summary_has_correct_stats_for_numeric_column():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    clean = df["revenue"].dropna()
    stats = profile["numeric_summary"]["revenue"]

    assert stats["min"] == clean.min()
    assert stats["max"] == clean.max()
    assert stats["mean"] == pytest.approx(clean.mean())
    assert stats["median"] == clean.median()
    assert stats["std"] == pytest.approx(clean.std())

    # non-numeric columns must never appear in numeric_summary
    assert "region" not in profile["numeric_summary"]
    assert "notes" not in profile["numeric_summary"]


def test_categorical_samples_contains_low_cardinality_exact_distinct_set():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    assert set(profile["categorical_samples"]["region"]) == {
        "North",
        "South",
        "East",
        "West",
    }
    assert len(profile["categorical_samples"]["region"]) == 4


def test_categorical_samples_excludes_high_cardinality_column():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    assert "notes" not in profile["categorical_samples"]


def test_profile_is_json_serializable():
    df = _fixture_df()
    profile = extract_schema_profile(df)

    dumped = json.dumps(profile)
    assert isinstance(dumped, str)


def test_canary_value_from_high_cardinality_column_never_leaks_into_profile():
    """Regression test for the privacy boundary: a value that exists ONLY in
    a high-cardinality (>20 distinct) non-numeric column must never appear
    anywhere in the serialized schema profile.
    """
    df = _fixture_df()
    assert CANARY in df["notes"].values  # sanity: canary really is in the raw data

    profile = extract_schema_profile(df)
    serialized = json.dumps(profile)

    assert CANARY not in serialized


def test_categorical_samples_never_exceeds_twenty_entries():
    # A column with exactly 21 distinct values must be excluded entirely.
    df = pd.DataFrame({"tag": [f"tag-{i}" for i in range(21)]})
    profile = extract_schema_profile(df)

    assert "tag" not in profile["categorical_samples"]


def test_categorical_samples_includes_column_at_exactly_twenty_distinct():
    df = pd.DataFrame({"tag": [f"tag-{i}" for i in range(20)]})
    profile = extract_schema_profile(df)

    assert "tag" in profile["categorical_samples"]
    assert len(profile["categorical_samples"]["tag"]) == 20
