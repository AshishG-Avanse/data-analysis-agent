"""In-process, single-session store for the one active uploaded file.

This is PURE IN-PROCESS MEMORY — a plain module-level dict guarded by a
lock. Nothing here is ever written to SQLite or otherwise persisted beyond
the parquet cache file this module writes for the DataFrame itself; a
server restart loses every session record (`spec/architecture.md` ->
"Memory & Context", `spec/data.md` -> "SessionState"). Callers must expect
`get_session` to return `None` after a restart and prompt the user to
re-upload.

The agent is single-session/single-file, always: creating a new session
discards any previously active one (`spec/data.md` -> "uploading again
replaces it in place rather than creating a second concurrent session").
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_UPLOAD_ROOT = Path("data/uploads")

_lock = threading.Lock()
_sessions: dict[str, "SessionRecord"] = {}


@dataclass
class SessionRecord:
    """The full in-memory record for one active uploaded file.

    `dataframe` is the live pandas DataFrame (used by anything running
    in-process); `dataframe_path` is a parquet cache of the same data
    written to disk so the isolated subprocess executor (`code_executor.py`
    / `exec_worker.py`) can load it without any coupling to this in-memory
    store.
    """

    session_id: str
    filename: str
    dataframe: pd.DataFrame
    dataframe_path: str
    schema_profile: dict
    warnings: list[str] = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def create_session(filename: str, df: pd.DataFrame, schema_profile: dict) -> SessionRecord:
    """Start a fresh session for a newly uploaded/parsed file.

    Generates a new `session_id`, writes a parquet cache of `df` to
    `data/uploads/<session_id>/cache.parquet`, and replaces the entire
    store with this single new session — discarding any previously active
    session (this agent is single-session/single-file, always).
    """
    session_id = str(uuid.uuid4())

    session_dir = _UPLOAD_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    dataframe_path = session_dir / "cache.parquet"
    df.to_parquet(dataframe_path)

    record = SessionRecord(
        session_id=session_id,
        filename=filename,
        dataframe=df,
        dataframe_path=str(dataframe_path),
        schema_profile=schema_profile,
        warnings=[],
        conversation_history=[],
    )

    with _lock:
        _sessions.clear()
        _sessions[session_id] = record

    return record


def get_session(session_id: str) -> SessionRecord | None:
    """Look up the active session, or `None` if it's unknown/expired.

    Returns `None` both for a truly unknown id and for any id that
    belonged to a session that has since been replaced by a newer upload
    or lost to a server restart.
    """
    with _lock:
        return _sessions.get(session_id)
