"""Phase 1 end-to-end gate: real Gemini API, full HTTP round-trip.

Fixture anomaly (see `tests/fixtures/sales_1000.csv`, generated with
`numpy.random.default_rng(42)`):
  - The file has 1,000 rows with columns `region` (categorical) and
    `revenue` (numeric).
  - Rows 0-4 (the first five rows) are DELIBERATELY anomalous: all five
    have `region == "West"` and `revenue == 50000.0` (an extreme, planted
    outlier).
  - Rows 5-999 (995 rows) have `revenue` drawn from a normal distribution
    (mean ~1000, std ~150), clipped to be positive, across four regions.

Traceable true values (computed directly with pandas over the FULL file,
not reproduced here from memory — see `test_average_revenue_...` below,
which independently recomputes them at test time so this file is the
single source of truth):
  - TRUE full-dataset mean revenue: ~1241.78
  - NAIVE first-5-rows-only mean revenue: 50000.0 (>40x the true value)

If the agent's generated code were run against only a truncated head of
the file (e.g. `df.head()` or a partial read), the answer would land near
50000, not ~1242. Asserting the answer is close to the true full-dataset
mean and far from the naive value is the proof that the generated code
runs against the complete, real DataFrame.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sales_1000.csv"


@pytest.fixture
def client(_isolated_db):
    from api import app
    with TestClient(app) as c:
        yield c


def _upload_fixture(client: TestClient) -> str:
    with open(_FIXTURE_PATH, "rb") as f:
        resp = client.post(
            "/api/sessions",
            files={"file": ("sales_1000.csv", f.read(), "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["row_count"] == 1000
    return body["data"]["session_id"]


def _extract_number(text: str) -> float | None:
    """Pull the first plausible decimal number out of a plain-language answer.

    `\\d+` (unbounded) must come before the optional comma-grouping so a
    plain 4+ digit number with no thousand separators (e.g. "1241.78") is
    not truncated to its first 3 digits.
    """
    match = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


@pytest.mark.usefixtures("_require_llm_key")
def test_average_revenue_uses_full_dataset_not_truncated_sample(client):
    session_id = _upload_fixture(client)

    true_mean = pd.read_csv(_FIXTURE_PATH)["revenue"].mean()
    naive_first_5_mean = pd.read_csv(_FIXTURE_PATH)["revenue"].head(5).mean()
    # Sanity-check the fixture itself is engineered as documented above.
    assert naive_first_5_mean == pytest.approx(50000.0)
    assert abs(true_mean - naive_first_5_mean) > 1000

    resp = client.post(
        f"/api/sessions/{session_id}/questions",
        json={"question": "What is the average revenue across all rows?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    data = body["data"]

    assert data["status"] == "completed"
    assert data["question"] == "What is the average revenue across all rows?"
    assert data["code"], "expected non-null generated pandas code on success"
    assert "def analyze" in data["code"] or "df" in data["code"]
    assert isinstance(data["retry_count"], int)
    # Phase 1 stubs — always null until Phase 2.
    assert data["cost_estimate_usd"] is None
    assert data["chart_spec"] is None
    assert data["table"] is None

    answer_number = _extract_number(data["answer"])
    assert answer_number is not None, f"could not extract a number from: {data['answer']!r}"

    # The critical proof: close to the TRUE full-dataset mean, nowhere near
    # the naive first-5-rows-only value.
    assert answer_number == pytest.approx(true_mean, rel=0.1), (
        f"answer number {answer_number} not close to true full-dataset mean {true_mean}"
    )
    assert abs(answer_number - naive_first_5_mean) > 1000, (
        "answer looks like it was computed from a truncated sample, not the full file"
    )


@pytest.mark.usefixtures("_require_llm_key")
def test_nonexistent_column_self_corrects_or_gives_up_cleanly(client):
    session_id = _upload_fixture(client)

    resp = client.post(
        f"/api/sessions/{session_id}/questions",
        json={"question": "What is the average of a column called zzz_not_real?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    data = body["data"]

    assert data["status"] in ("completed", "gave_up")
    if data["status"] == "gave_up":
        assert data["code"] is None
        assert data["answer"]
        assert "wasn't able" in data["answer"].lower() or "rephrasing" in data["answer"].lower()
    else:
        assert data["code"]


@pytest.mark.usefixtures("_require_llm_key")
def test_empty_question_returns_400(client):
    session_id = _upload_fixture(client)

    resp = client.post(f"/api/sessions/{session_id}/questions", json={"question": ""})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "EMPTY_QUESTION"


@pytest.mark.usefixtures("_require_llm_key")
def test_missing_question_field_returns_400_not_422(client):
    session_id = _upload_fixture(client)

    resp = client.post(f"/api/sessions/{session_id}/questions", json={})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "EMPTY_QUESTION"


@pytest.mark.usefixtures("_require_llm_key")
def test_unknown_session_returns_404(client):
    resp = client.post(
        "/api/sessions/does-not-exist/questions",
        json={"question": "What is the average revenue?"},
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["code"] == "NOT_FOUND"
