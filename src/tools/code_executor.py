"""Parent-side isolation boundary for running LLM-generated pandas code.

Spawns `exec_worker.py` (see that module's docstring for the honest
isolation-limitation note) as a subprocess per attempt, passes the generated
code via stdin, and enforces a hard timeout. Never raises — always returns a
dict shape the `execute_code` graph node can consume directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_WORKER_PATH = Path(__file__).parent / "exec_worker.py"


def execute_pandas_code(code: str, dataframe_path: str | Path, timeout_seconds: int) -> dict:
    """Run `code` (must define `def analyze(df): ...`) against the cached
    DataFrame at `dataframe_path`, isolated in a subprocess with a hard
    timeout.

    Returns `{"success": bool, "result": Any | None, "error": str | None}`.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(_WORKER_PATH), str(dataframe_path)],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "result": None,
            "error": f"Analysis code timed out after {timeout_seconds}s and was terminated.",
        }
    except OSError as exc:
        return {
            "success": False,
            "result": None,
            "error": f"Failed to launch the execution subprocess: {exc}",
        }

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return {
            "success": False,
            "result": None,
            "error": f"Execution subprocess exited with code {proc.returncode}: {detail[-2000:]}",
        }

    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "success": False,
            "result": None,
            "error": f"Execution subprocess produced unparseable output: {stdout[:2000]!r}",
        }

    if payload.get("success"):
        return {"success": True, "result": payload.get("result"), "error": None}

    return {
        "success": False,
        "result": None,
        "error": payload.get("error") or "Unknown execution error.",
    }
