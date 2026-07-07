"""Unit tests for the subprocess code-execution isolation boundary.

Uses a fixture DataFrame written to a temp parquet file directly (no
dependency on the real upload/session-store path, which is a different,
parallel slice).
"""

import pandas as pd
import pytest

from tools.code_executor import execute_pandas_code


def _write_df(tmp_path, df: pd.DataFrame):
    path = tmp_path / "df.parquet"
    df.to_parquet(path)
    return path


def test_happy_path_returns_correct_aggregate(tmp_path):
    df = pd.DataFrame({"region": ["N", "S", "N", "E"], "revenue": [10.0, 20.0, 30.0, 40.0]})
    path = _write_df(tmp_path, df)
    code = "def analyze(df):\n    return float(df['revenue'].sum())\n"

    result = execute_pandas_code(code, path, timeout_seconds=15)

    assert result["success"] is True
    assert result["error"] is None
    assert result["result"] == pytest.approx(100.0)


def test_edge_case_raw_shaped_result_is_rejected_by_privacy_guard(tmp_path):
    df = pd.DataFrame({"region": [f"r{i}" for i in range(30)], "revenue": list(range(30))})
    path = _write_df(tmp_path, df)
    code = "def analyze(df):\n    return df.to_dict(orient='records')\n"

    result = execute_pandas_code(code, path, timeout_seconds=15)

    assert result["success"] is False
    assert result["result"] is None
    assert result["error"]


def test_error_path_exception_in_generated_code_is_caught_not_raised(tmp_path):
    df = pd.DataFrame({"revenue": [1.0, 2.0, 3.0]})
    path = _write_df(tmp_path, df)
    code = "def analyze(df):\n    return df['does_not_exist'].sum()\n"

    result = execute_pandas_code(code, path, timeout_seconds=15)

    assert result["success"] is False
    assert result["result"] is None
    assert "does_not_exist" in result["error"] or result["error"]


def test_missing_analyze_function_is_treated_as_failure(tmp_path):
    df = pd.DataFrame({"revenue": [1.0, 2.0]})
    path = _write_df(tmp_path, df)
    code = "x = 1\n"

    result = execute_pandas_code(code, path, timeout_seconds=15)

    assert result["success"] is False
    assert "analyze" in result["error"].lower()


def test_syntax_error_in_generated_code_is_caught_not_raised(tmp_path):
    df = pd.DataFrame({"revenue": [1.0, 2.0]})
    path = _write_df(tmp_path, df)
    code = "def analyze(df:\n    return 1\n"  # missing closing paren

    result = execute_pandas_code(code, path, timeout_seconds=15)

    assert result["success"] is False
    assert result["result"] is None
    assert result["error"]


def test_timeout_is_enforced_and_process_is_terminated(tmp_path):
    df = pd.DataFrame({"revenue": [1.0, 2.0]})
    path = _write_df(tmp_path, df)
    code = "import time\ndef analyze(df):\n    time.sleep(5)\n    return 1\n"

    result = execute_pandas_code(code, path, timeout_seconds=1)

    assert result["success"] is False
    assert result["result"] is None
    assert "timed out" in result["error"].lower()


def test_full_dataset_is_used_not_a_truncated_sample(tmp_path):
    """1,000+ row fixture where a naive head(5) sample would differ materially
    from the true full-dataset sum — proves the executor runs against the
    complete cached DataFrame, not a truncated preview.
    """
    n = 1200
    revenue = [1.0] * n
    revenue[0] = 1_000_000.0  # anomalous value only in the first few rows
    df = pd.DataFrame({"revenue": revenue})
    path = _write_df(tmp_path, df)
    code = "def analyze(df):\n    return float(df['revenue'].sum())\n"

    result = execute_pandas_code(code, path, timeout_seconds=15)

    true_total = 1_000_000.0 + (n - 1) * 1.0
    assert result["success"] is True
    assert result["result"] == pytest.approx(true_total)
