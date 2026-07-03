from graph.state import QAState


def after_generate_code(state: QAState) -> str:
    """Fatal Gemini/SDK failure routes to handle_error; otherwise always execute."""
    if state.get("error"):
        return "handle_error"
    return "execute_code"


def after_execute_code(state: QAState) -> str:
    """Success -> synthesize; failure -> retry loop or give_up; fatal -> handle_error."""
    if state.get("error"):
        return "handle_error"
    if state.get("execution_error") is None:
        return "synthesize_answer"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count < max_retries:
        return "generate_code"
    return "give_up"


def after_synthesize_answer(state: QAState) -> str:
    """Fatal Gemini/SDK failure routes to handle_error; otherwise finalize."""
    if state.get("error"):
        return "handle_error"
    return "finalize"
