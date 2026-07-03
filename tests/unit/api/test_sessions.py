"""Tests for POST /api/sessions and GET /api/sessions/{session_id}.

Uses a router-only test app (no full create_app()/DB wiring — that's owned
by a later slice) per api/sessions.py's router object.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import graph.state as _graph_state  # noqa: E402

if not hasattr(_graph_state, "AgentState"):
    # A parallel, already-in-flight slice ("qa-graph-core") is mid-rewrite on
    # src/graph/state.py and has not yet restored `AgentState` (still used by
    # the legacy src/graph/runner.py -> src/api/runs.py import chain that a
    # later slice, "questions-api-and-wiring", will finish rewiring). That
    # breakage is expected and entirely out of scope for this slice. Importing
    # `api.sessions` unavoidably triggers `src/api/__init__.py`, which eagerly
    # imports `api.runs` -> `graph.runner` -> `graph.state.AgentState` at
    # package-import time -- shim the missing name here, in-memory only (no
    # file on disk is touched), purely so this unrelated test module isn't
    # collateral damage from that other slice's in-progress rewrite.
    _graph_state.AgentState = dict

import api.sessions as sessions_module
from tools import session_store


@pytest.fixture(autouse=True)
def _isolated_session_store(tmp_path, monkeypatch):
    """Each test gets its own empty session store and its own upload dir."""
    monkeypatch.setattr(session_store, "_sessions", {})
    monkeypatch.setattr(session_store, "_UPLOAD_ROOT", tmp_path / "uploads")
    yield
    monkeypatch.setattr(session_store, "_sessions", {})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(sessions_module.router, prefix="/api")
    with TestClient(app) as c:
        yield c


def _sample_df(n_distinct: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["North", "South", "East"],
            "revenue": [100.5, 200.25, 300.0],
        }
    )


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def test_successful_upload_returns_expected_shape(client):
    df = _sample_df()
    csv_bytes = _csv_bytes(df)

    resp = client.post(
        "/api/sessions",
        files={"file": ("sales.csv", csv_bytes, "text/csv")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    data = body["data"]

    assert data["filename"] == "sales.csv"
    assert data["row_count"] == 3
    assert data["column_count"] == 2
    assert data["warnings"] == []
    assert data["schema_profile"]["row_count"] == 3
    assert data["schema_profile"]["column_count"] == 2
    assert isinstance(data["session_id"], str) and data["session_id"]


def test_unsupported_file_type_returns_400_with_clear_message(client):
    resp = client.post(
        "/api/sessions",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )

    assert resp.status_code == 400
    body = resp.json()
    # api_error() raises an HTTPException; FastAPI serializes its `detail`
    # payload (our {"code", "message"} shape) directly under "detail".
    detail = body["detail"]
    assert detail["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "unsupported" in detail["message"].lower() or ".txt" in detail["message"].lower()


def test_second_upload_replaces_first_session_entirely(client):
    df1 = _sample_df()
    resp1 = client.post(
        "/api/sessions",
        files={"file": ("first.csv", _csv_bytes(df1), "text/csv")},
    )
    assert resp1.status_code == 200
    first_session_id = resp1.json()["data"]["session_id"]

    df2 = pd.DataFrame({"city": ["A", "B"], "count": [1, 2]})
    resp2 = client.post(
        "/api/sessions",
        files={"file": ("second.csv", _csv_bytes(df2), "text/csv")},
    )
    assert resp2.status_code == 200
    second_session_id = resp2.json()["data"]["session_id"]

    assert first_session_id != second_session_id

    # The old session is fully evicted -- no trace of the first file remains queryable.
    old_resp = client.get(f"/api/sessions/{first_session_id}")
    assert old_resp.status_code == 404

    # The new session is fully queryable.
    new_resp = client.get(f"/api/sessions/{second_session_id}")
    assert new_resp.status_code == 200
    assert new_resp.json()["data"]["filename"] == "second.csv"


def test_get_unknown_session_returns_404(client):
    resp = client.get("/api/sessions/does-not-exist")
    assert resp.status_code == 404


def test_get_session_after_upload_returns_full_state(client):
    df = _sample_df()
    resp = client.post(
        "/api/sessions",
        files={"file": ("sales.csv", _csv_bytes(df), "text/csv")},
    )
    session_id = resp.json()["data"]["session_id"]

    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()["data"]
    assert data["session_id"] == session_id
    assert data["filename"] == "sales.csv"
    assert data["warnings"] == []
    assert data["conversation_history"] == []
    assert "schema_profile" in data


def test_schema_profile_in_response_never_leaks_raw_row_or_over_20_samples(client):
    # High-cardinality column with a canary value that only ever appears in a
    # raw row -- must never leak into the JSON response body.
    canary = "CANARY-UNIQUE-VALUE-XYZ-99887766"
    n = 30
    df = pd.DataFrame(
        {
            "id": [f"row-{i}" for i in range(n)],
            "note": [canary if i == 0 else f"note-{i}" for i in range(n)],
            "category": ["A", "B", "C"] * 10,
        }
    )

    resp = client.post(
        "/api/sessions",
        files={"file": ("wide.csv", _csv_bytes(df), "text/csv")},
    )
    assert resp.status_code == 200

    raw_body = resp.text
    assert canary not in raw_body

    schema_profile = resp.json()["data"]["schema_profile"]
    for column_samples in schema_profile["categorical_samples"].values():
        assert len(column_samples) <= 20


def test_file_exceeding_max_upload_size_returns_413(client, monkeypatch):
    monkeypatch.setattr(sessions_module, "MAX_UPLOAD_SIZE_MB", 0)
    monkeypatch.setattr(sessions_module, "_MAX_UPLOAD_SIZE_BYTES", 10)

    df = _sample_df()
    resp = client.post(
        "/api/sessions",
        files={"file": ("sales.csv", _csv_bytes(df), "text/csv")},
    )

    assert resp.status_code == 413
