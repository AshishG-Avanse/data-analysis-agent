"""Unit tests for the QA graph's retry loop.

These tests never call the real Gemini API — `LLMClient` and
`execute_pandas_code` are monkeypatched at the `graph.nodes` module level so
the graph's control-flow (generate -> execute -> retry -> give_up/success)
can be verified deterministically and cheaply. The real-Gemini,
real-subprocess end-to-end path is covered by a later slice's integration
test (`tests/integration/test_phase1_qa.py`).
"""

import graph.nodes as nodes


def test_graph_compiles():
    """Graph compiles without requiring any env vars."""
    from graph.agent import agentic_ai
    assert agentic_ai is not None


def _base_state(max_retries: int = 3) -> dict:
    return {
        "session_id": "session-1",
        "question": "What is the total revenue?",
        "schema_profile": {"row_count": 10, "columns": [{"name": "revenue", "dtype": "float64"}]},
        "conversation_history": [],
        "dataframe_path": "unused.parquet",
        "retry_count": 0,
        "max_retries": max_retries,
    }


class _FakeLLMClient:
    """Stand-in for llm.client.LLMClient — routes by prompt shape, never hits the network."""

    def __init__(self, model=None):
        # Instances are constructed by node code as `LLMClient(model=...)`;
        # per-test behaviour is provided by subclassing, not constructor args.
        pass

    def call_model(self, prompt: str, *, system: str | None = None) -> str:
        if "## Schema profile" in prompt:
            return self.codegen_response(prompt)
        return self.interpret_response(prompt)

    # Overridden per-test via subclassing (simpler than instance state, since
    # LLMClient is constructed fresh by node code on every call).
    def codegen_response(self, prompt: str) -> str:
        raise NotImplementedError

    def interpret_response(self, prompt: str) -> str:
        raise NotImplementedError


def test_retry_loop_gives_up_after_exactly_max_retries(monkeypatch):
    call_counts = {"generate": 0, "execute": 0}

    class _AlwaysFailsToGenerateCorrectly(_FakeLLMClient):
        def codegen_response(self, prompt: str) -> str:
            call_counts["generate"] += 1
            return "```python\ndef analyze(df):\n    return 1\n```"

        def interpret_response(self, prompt: str) -> str:
            raise AssertionError("synthesize_answer should never be reached on a give-up path")

    def _fake_execute(code, dataframe_path, timeout_seconds):
        call_counts["execute"] += 1
        return {"success": False, "result": None, "error": "simulated execution failure"}

    monkeypatch.setattr(nodes, "LLMClient", _AlwaysFailsToGenerateCorrectly)
    monkeypatch.setattr(nodes, "execute_pandas_code", _fake_execute)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=2))

    assert final["status"] == "gave_up"
    assert final["retry_count"] == 2
    assert call_counts["generate"] == 2
    assert call_counts["execute"] == 2
    # No partial code/result/attempt-trail is ever surfaced on give-up.
    assert final["final_answer"]
    assert "def analyze" not in final["final_answer"]
    assert "simulated execution failure" not in final["final_answer"]


def test_retry_loop_recovers_after_one_failed_attempt(monkeypatch):
    call_counts = {"execute": 0}

    class _SucceedsEventually(_FakeLLMClient):
        def codegen_response(self, prompt: str) -> str:
            return "```python\ndef analyze(df):\n    return {'total': 7}\n```"

        def interpret_response(self, prompt: str) -> str:
            return "The total is 7."

    def _fake_execute(code, dataframe_path, timeout_seconds):
        call_counts["execute"] += 1
        if call_counts["execute"] == 1:
            return {"success": False, "result": None, "error": "first attempt: bad column"}
        return {"success": True, "result": {"total": 7}, "error": None}

    monkeypatch.setattr(nodes, "LLMClient", _SucceedsEventually)
    monkeypatch.setattr(nodes, "execute_pandas_code", _fake_execute)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=3))

    assert final["status"] == "completed"
    assert call_counts["execute"] == 2
    assert final["retry_count"] == 1
    assert final["final_answer"] == "The total is 7."
    assert final["execution_result"] == {"total": 7}


def test_full_graph_succeeds_on_forced_success_path(monkeypatch):
    class _AlwaysSucceeds(_FakeLLMClient):
        def codegen_response(self, prompt: str) -> str:
            return "```python\ndef analyze(df):\n    return {'total': 42}\n```"

        def interpret_response(self, prompt: str) -> str:
            return "The total is 42."

    def _fake_execute(code, dataframe_path, timeout_seconds):
        return {"success": True, "result": {"total": 42}, "error": None}

    monkeypatch.setattr(nodes, "LLMClient", _AlwaysSucceeds)
    monkeypatch.setattr(nodes, "execute_pandas_code", _fake_execute)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=3))

    assert final["status"] == "completed"
    assert final["final_answer"] == "The total is 42."
    assert final["execution_result"] == {"total": 42}
    assert final.get("error") is None
    # Phase 2 fields stay explicitly None in Phase 1.
    assert final["chart_spec"] is None
    assert final["table_data"] is None
    assert final["cost_estimate_usd"] is None


def test_fatal_llm_error_in_generate_code_routes_to_handle_error(monkeypatch):
    class _RaisingLLMClient:
        def __init__(self, model=None):
            pass

        def call_model(self, prompt: str, *, system=None):
            raise RuntimeError("Gemini API unreachable")

    monkeypatch.setattr(nodes, "LLMClient", _RaisingLLMClient)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=3))

    assert final["status"] == "failed"
    assert final.get("error")


def test_fatal_llm_error_in_synthesize_answer_routes_to_handle_error(monkeypatch):
    class _FailsOnlyOnInterpret(_FakeLLMClient):
        def codegen_response(self, prompt: str) -> str:
            return "```python\ndef analyze(df):\n    return {'total': 1}\n```"

        def interpret_response(self, prompt: str) -> str:
            raise RuntimeError("Gemini API unreachable")

    def _fake_execute(code, dataframe_path, timeout_seconds):
        return {"success": True, "result": {"total": 1}, "error": None}

    monkeypatch.setattr(nodes, "LLMClient", _FailsOnlyOnInterpret)
    monkeypatch.setattr(nodes, "execute_pandas_code", _fake_execute)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=3))

    assert final["status"] == "failed"
    assert final.get("error")


def test_no_extractable_code_block_is_treated_as_retryable_not_fatal(monkeypatch):
    """A codegen response with no fenced python block must retry, not crash."""
    call_counts = {"generate": 0}

    class _NoCodeBlockThenValid(_FakeLLMClient):
        def codegen_response(self, prompt: str) -> str:
            call_counts["generate"] += 1
            if call_counts["generate"] == 1:
                return "Sorry, I can't help with that."
            return "```python\ndef analyze(df):\n    return {'total': 5}\n```"

        def interpret_response(self, prompt: str) -> str:
            return "The total is 5."

    def _fake_execute(code, dataframe_path, timeout_seconds):
        return {"success": True, "result": {"total": 5}, "error": None}

    monkeypatch.setattr(nodes, "LLMClient", _NoCodeBlockThenValid)
    monkeypatch.setattr(nodes, "execute_pandas_code", _fake_execute)

    from graph.agent import agentic_ai

    final = agentic_ai.invoke(_base_state(max_retries=3))

    assert final["status"] == "completed"
    assert final.get("error") is None
    assert call_counts["generate"] == 2
