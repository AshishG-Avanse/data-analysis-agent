"""Regression test for the data-privacy boundary (spec/architecture.md ->
"Data Privacy Boundary" -> "The regression test that would catch a leak").

Required by the Phase 1 gate at exactly this path — do not rename or skip.
"""

import json

import pandas as pd
import pytest

import graph.nodes as nodes
from tools.privacy_guard import AggregateGuardError, assert_aggregate_only
from tools.schema_profile import extract_schema_profile

_CANARY = "CANARY_9f3e1b7c4a2d_ONLY_IN_RAW_ROWS"


def _fixture_df_with_canary() -> pd.DataFrame:
    """A DataFrame whose canary value exists ONLY in one raw cell.

    `notes` is deliberately high-cardinality (26 distinct values > the
    schema profile's 20-distinct-value categorical cap) so the canary is
    excluded from `categorical_samples` by construction — it can only ever
    leak if raw rows themselves were serialized somewhere.
    """
    notes = [f"note-{i}" for i in range(26)]
    notes[3] = _CANARY
    return pd.DataFrame(
        {
            "notes": notes,
            "revenue": [float(i * 10) for i in range(26)],
        }
    )


def test_canary_value_never_appears_in_rendered_prompts():
    df = _fixture_df_with_canary()

    # 1. Build the real SchemaProfile the way the upload path does.
    schema_profile = extract_schema_profile(df)
    schema_json = json.dumps(schema_profile, indent=2)
    assert _CANARY not in schema_json, (
        "extract_schema_profile leaked a raw cell value — this would be a "
        "privacy-boundary violation before the prompt is even rendered."
    )

    # 2. Render the real codegen prompt template exactly as generate_code does.
    codegen_rendered = nodes._load_prompt(nodes._CODEGEN_PROMPT_PATH).format(
        schema_profile=schema_json,
        question="What is the average revenue?",
        retry_context="N/A (first attempt).",
    )
    assert _CANARY not in codegen_rendered

    # 3. A guarded aggregate result is the only thing that reaches the
    #    interpretation prompt — never raw rows.
    execution_result = assert_aggregate_only({"average_revenue": float(df["revenue"].mean())})
    execution_result_json = json.dumps(execution_result, indent=2)
    assert _CANARY not in execution_result_json

    # 4. Render the real interpret prompt template exactly as synthesize_answer does.
    interpret_rendered = nodes._load_prompt(nodes._INTERPRET_PROMPT_PATH).format(
        question="What is the average revenue?",
        execution_result=execution_result_json,
    )
    assert _CANARY not in interpret_rendered


def test_large_raw_shaped_result_raises_aggregate_guard_error():
    """A simulated raw-row-shaped result (> 20 rows) must be rejected."""
    raw_rows = [{"region": f"r{i}", "revenue": float(i)} for i in range(25)]
    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(raw_rows)


def test_columnar_dict_of_long_lists_is_also_rejected():
    """df.to_dict(orient='list')-shaped bulk data must be rejected too."""
    columnar = {"region": [f"r{i}" for i in range(30)], "revenue": list(range(30))}
    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(columnar)


def test_high_cardinality_groupby_dict_of_scalars_is_rejected():
    """df.groupby(<high-cardinality column>)[<col>].sum().to_dict()-shaped
    result: a top-level dict with > 20 scalar-valued keys must be rejected —
    each key/value pair is effectively a raw per-record value, not a genuine
    small aggregate.
    """
    per_customer_totals = {f"customer_{i}": float(i) * 3.7 for i in range(25)}
    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(per_customer_totals)

    per_column_scalars = {f"col_{i}": i for i in range(25)}
    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(per_column_scalars)


def test_small_scalar_dict_at_key_limit_boundary_passes_through():
    """A dict with exactly _MAX_ROWS (20) scalar keys is still a legitimate
    small aggregate (e.g. a groupby over a low-cardinality column) and must
    pass through unchanged — only *more than* 20 keys is rejected.
    """
    small_groupby_result = {f"region_{i}": float(i) for i in range(20)}
    assert assert_aggregate_only(small_groupby_result) == small_groupby_result


def test_oversized_serialized_payload_is_rejected():
    huge_aggregate = {"summary": "x" * 60_000}
    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(huge_aggregate)


def test_non_json_serializable_result_is_rejected():
    class NotSerializable:
        pass

    with pytest.raises(AggregateGuardError):
        assert_aggregate_only(NotSerializable())


def test_small_valid_aggregate_passes_through_unchanged():
    aggregate = {"total_revenue": 1234.5, "by_region": {"North": 500.0, "South": 734.5}}
    assert assert_aggregate_only(aggregate) == aggregate


def test_small_list_of_grouped_rows_passes_through():
    grouped = [{"region": "North", "total": 500.0}, {"region": "South", "total": 734.5}]
    assert assert_aggregate_only(grouped) == grouped
