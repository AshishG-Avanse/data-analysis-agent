"""Subprocess worker that executes LLM-generated pandas code in isolation.

Convention: the generated code (read from stdin) must define exactly one
function, `analyze(df)`, that returns a small aggregate result — this is
the contract `generate_code`'s prompt (`src/prompts/codegen.md`) instructs
the model to follow. This worker:

  1. Loads the cached DataFrame from the parquet file at argv[1].
  2. `exec`s the generated code (read from stdin) in a fresh namespace with
     `pd`/`np` preloaded.
  3. Calls `analyze(df)`.
  4. Converts the result to native JSON-serializable types.
  5. Runs it through the privacy/size guard (`assert_aggregate_only`).
  6. Prints exactly one JSON line to stdout:
     `{"success": true, "result": ...}` or `{"success": false, "error": "..."}`
     — nothing else is ever written to stdout, so the parent process
     (`code_executor.py`) can parse it directly.

Isolation note (honest limitation, by design): this is a plain OS
subprocess with a parent-enforced timeout, NOT a container/sandbox — there
is no separate filesystem or network jail. For a local, single-user,
experimental-grade tool (see `spec/roadmap.md` -> Key Constraints ->
Reliability bar) this is a proportionate level of isolation: a runaway,
hanging, or crashing analysis attempt cannot take down or block the main
FastAPI process, and it always terminates within
`AGENT_EXEC_TIMEOUT_SECONDS`. It is not a defense against a deliberately
adversarial code attempt — that is not this tool's threat model (the code
comes from an LLM the user themselves is directing, not an untrusted third
party), so a full Docker sandbox would be over-engineering for this scope.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow `tools.privacy_guard` to be imported when this file is launched
# directly as `python exec_worker.py ...` (not via pytest's pythonpath).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.privacy_guard import AggregateGuardError, assert_aggregate_only  # noqa: E402


def _to_jsonable(value):
    """Recursively convert numpy/pandas objects to native JSON-safe types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_to_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.Series):
        return {str(k): _to_jsonable(v) for k, v in value.to_dict().items()}
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="list")
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _emit(payload: dict) -> None:
    print(json.dumps(payload))


def main() -> int:
    if len(sys.argv) < 2:
        _emit({"success": False, "result": None, "error": "usage: exec_worker.py <dataframe_path>"})
        return 0

    dataframe_path = sys.argv[1]
    code = sys.stdin.read()

    try:
        df = pd.read_parquet(dataframe_path)
    except Exception as exc:
        _emit({"success": False, "result": None, "error": f"Failed to load cached data: {exc}"})
        return 0

    namespace: dict = {"pd": pd, "np": np}
    try:
        exec(code, namespace)  # noqa: S102 -- generated code, run inside this isolated subprocess by design
    except Exception as exc:
        _emit({"success": False, "result": None, "error": f"Generated code failed to parse/define: {exc}"})
        return 0

    analyze_fn = namespace.get("analyze")
    if not callable(analyze_fn):
        _emit(
            {
                "success": False,
                "result": None,
                "error": "Generated code did not define a callable analyze(df) function.",
            }
        )
        return 0

    try:
        raw_result = analyze_fn(df)
    except Exception as exc:
        _emit({"success": False, "result": None, "error": f"Generated code raised during execution: {exc}"})
        return 0

    try:
        jsonable = _to_jsonable(raw_result)
        validated = assert_aggregate_only(jsonable)
    except AggregateGuardError as exc:
        _emit({"success": False, "result": None, "error": str(exc)})
        return 0
    except Exception as exc:
        _emit({"success": False, "result": None, "error": f"Result could not be validated: {exc}"})
        return 0

    _emit({"success": True, "result": validated, "error": None})
    return 0


if __name__ == "__main__":
    sys.exit(main())
