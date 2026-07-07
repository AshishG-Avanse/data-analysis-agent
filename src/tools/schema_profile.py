"""Local, network-free extraction of a compact schema/summary profile.

This is the privacy boundary described in `spec/architecture.md` ->
"Data Privacy Boundary". The returned dict must never contain raw row
data — only aggregated/derived facts — and must always be JSON-serializable.
"""

from __future__ import annotations

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

_MAX_CATEGORICAL_DISTINCT = 20


def extract_schema_profile(df: pd.DataFrame) -> dict:
    """Build a JSON-serializable schema/summary profile for `df`.

    Never inspects or returns individual rows/cells beyond the aggregates
    documented in `spec/architecture.md`.
    """
    columns: list[dict] = []
    categorical_samples: dict[str, list] = {}
    numeric_summary: dict[str, dict] = {}

    for column_name in df.columns:
        name = str(column_name)
        series = df[column_name]
        dtype_str = str(series.dtype)
        null_count = int(series.isna().sum())
        non_null_count = int(series.notna().sum())

        columns.append(
            {
                "name": name,
                "dtype": dtype_str,
                "null_count": null_count,
                "non_null_count": non_null_count,
            }
        )

        if is_numeric_dtype(series) and not is_bool_dtype(series):
            numeric_summary[name] = _numeric_stats(series)
        else:
            distinct_values = series.dropna().unique().tolist()
            if len(distinct_values) <= _MAX_CATEGORICAL_DISTINCT:
                categorical_samples[name] = [_to_native(v) for v in distinct_values]

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
        "categorical_samples": categorical_samples,
        "numeric_summary": numeric_summary,
    }


def _numeric_stats(series: pd.Series) -> dict:
    clean = series.dropna()
    if clean.empty:
        return {"min": None, "max": None, "mean": None, "std": None, "median": None}

    std = clean.std()
    return {
        "min": _to_native(clean.min()),
        "max": _to_native(clean.max()),
        "mean": _to_native(clean.mean()),
        "std": _to_native(std) if pd.notna(std) else None,
        "median": _to_native(clean.median()),
    }


def _to_native(value):
    """Convert numpy/pandas scalars to native Python types for JSON safety."""
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
