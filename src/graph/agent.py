from langgraph.graph import StateGraph, END

from graph.state import QAState
from graph.nodes import generate_code, execute_code, synthesize_answer, give_up, handle_error, finalize
from graph.edges import after_generate_code, after_execute_code, after_synthesize_answer


def _build_graph() -> StateGraph:
    g = StateGraph(QAState)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("synthesize_answer", synthesize_answer)
    g.add_node("give_up", give_up)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_code")

    g.add_conditional_edges(
        "generate_code", after_generate_code,
        {"execute_code": "execute_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code", after_execute_code,
        {
            "synthesize_answer": "synthesize_answer",
            "generate_code": "generate_code",   # retry loop
            "give_up": "give_up",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "synthesize_answer", after_synthesize_answer,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("give_up", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
