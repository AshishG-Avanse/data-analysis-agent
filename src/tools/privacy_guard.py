"""Privacy/size guard applied to every code-execution result before it can
reach the interpretation prompt or the API response.

See spec/architecture.md -> "Data Privacy Boundary" for the exact contract.
This is the last line of defense against a generated code attempt that
accidentally (or by a bad prompt-follow) returns raw row data instead of a
small aggregate.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_SERIALIZED_BYTES = 50_000  # 50 KB
_MAX_ROWS = 20


class AggregateGuardError(Exception):
    """Raised when a result looks like raw/bulk data rather than a small aggregate."""


def assert_aggregate_only(result: Any) -> Any:
    """Validate that `result` is a small, JSON-serializable aggregate.

    Rejects (raises `AggregateGuardError`) when:
      1. `result` is not JSON-serializable at all (e.g. a raw DataFrame/Series
         object slipped through instead of being converted to native types).
      2. The JSON-serialized form is larger than `_MAX_SERIALIZED_BYTES`
         (50 KB) — a genuine aggregate is always small; anything this large
         is almost certainly a bulk/raw dump.
      3. The result structure "looks like more than 20 rows" — defined here,
         defensibly, as any of:
           - a bare list/tuple of records (`[{...}, {...}, ...]`) with
             > `_MAX_ROWS` items, or
           - a dict of parallel columnar lists (`{"region": [...], "revenue": [...]}`)
             each longer than `_MAX_ROWS` items (the shape `df.to_dict(orient="list")`
             would produce for a large frame), or
           - a top-level dict with more than `_MAX_ROWS` keys, even when every
             value is a scalar (the shape
             `df.groupby(<high-cardinality column>)[<col>].sum().to_dict()`
             would produce — each key/value pair is effectively a raw
             per-record value, not a genuine small aggregate).
         A dict of <= `_MAX_ROWS` scalar keys (the normal aggregate shape, e.g.
         `{"total_revenue": 12345.6}`) or a list of <= 20 aggregate rows
         (e.g. a small groupby result) passes through unchanged.

    Returns `result` unchanged when it passes all checks.
    """
    try:
        serialized = json.dumps(result)
    except (TypeError, ValueError) as exc:
        raise AggregateGuardError(
            f"Execution result is not JSON-serializable ({exc}); a raw pandas "
            "object may have leaked out — return a plain dict/list/scalar instead."
        ) from exc

    if len(serialized.encode("utf-8")) > _MAX_SERIALIZED_BYTES:
        raise AggregateGuardError(
            f"Execution result is too large ({len(serialized)} bytes serialized, "
            f"limit {_MAX_SERIALIZED_BYTES}) — return a smaller aggregate, not raw/bulk data."
        )

    if _looks_like_bulk_rows(result):
        raise AggregateGuardError(
            f"Execution result looks like raw/bulk data (more than {_MAX_ROWS} rows) "
            "rather than a small aggregate — group/summarize before returning."
        )

    return result


def _looks_like_bulk_rows(result: Any) -> bool:
    if isinstance(result, (list, tuple)) and len(result) > _MAX_ROWS:
        return True
    if isinstance(result, dict):
        if len(result) > _MAX_ROWS:
            return True
        for value in result.values():
            if isinstance(value, (list, tuple)) and len(value) > _MAX_ROWS:
                return True
    return False
