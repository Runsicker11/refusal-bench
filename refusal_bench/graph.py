"""The investigation loop.

    think ──▶ act ──▶ think ──▶ ... ──▶ review ──▶ conclude ──▶ END
      │                            ▲        │
      └────────── decide ──────────┴────────┘

`think` asks the model what to do next. `act` runs the tool it asked for.
`decide` is the conditional edge: keep going, or stop. `review` pauses for a
human. `conclude` writes the finding.

**Review is opt-in.** With `review=False` the graph runs straight through, which
is what the eval suite needs -- pausing for a human on each of a hundred cases
is not a review process, it is a hostage situation. With `review=True` the run
freezes before the finding is published and waits.

The invariant is the one from the orchestration harness this borrows from:
**workers propose, humans dispose.** The agent never publishes a conclusion
that a person has not seen.

Deliberately thin otherwise. No hypothesis generation (#30), no evidence
narrowing (#31), no refusal (#33).
"""

from __future__ import annotations

from typing import Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from refusal_bench.model import Model
from refusal_bench.state import InvestigationState

# A tool is a named callable taking kwargs and returning text the model can read.
Tool = Callable[..., str]


def _prompt(state: InvestigationState) -> str:
    lines = [f"Anomaly under investigation: {state['anomaly']}", ""]
    if state.get("evidence"):
        lines.append("Evidence so far:")
        for e in state["evidence"]:
            lines.append(f"  [{e['step']}] {e['tool']}({e['args']}) -> {e['result']}")
    else:
        lines.append("No evidence gathered yet.")
    return "\n".join(lines)


def build_graph(model: Model, tools: dict[str, Tool], review: bool = False):
    """Compile the investigation graph.

    `review=True` inserts a human checkpoint before the finding is published,
    and compiles with a checkpointer so the run can be paused and resumed.
    """

    def think(state: InvestigationState) -> dict:
        response = model.complete(_prompt(state))
        step = state.get("step", 0) + 1
        if response.tool_call is None:
            return {"step": step, "finding": response.text, "stop_reason": "concluded"}
        return {"step": step, "_pending": response.tool_call}

    def act(state: InvestigationState) -> dict:
        call = state["_pending"]
        tool = tools.get(call.name)
        if tool is None:
            # An unknown tool is information the model can recover from, not a
            # crash. Same principle as a malformed query in #24.
            result = f"error: no tool named {call.name!r}. available: {sorted(tools)}"
        else:
            result = tool(**call.args)
        return {
            "evidence": [
                {
                    "step": state["step"],
                    "tool": call.name,
                    "args": dict(call.args),
                    "result": result,
                }
            ],
            "_pending": None,
        }

    def review_node(state: InvestigationState) -> dict:
        """Pause. A person decides what happens to this finding.

        Resumed with {"action": "accept" | "reject" | "redirect", "note": str}.
        """
        decision = interrupt(
            {
                "anomaly": state.get("anomaly"),
                "finding": state.get("finding"),
                "evidence": state.get("evidence", []),
                "steps": state.get("step"),
            }
        )
        action = (decision or {}).get("action", "accept")
        note = (decision or {}).get("note", "")

        if action == "reject":
            return {"finding": None, "stop_reason": "rejected", "review_note": note}

        if action == "redirect":
            # The note becomes evidence, so the next `think` sees it the same
            # way it sees a query result. Human input is not a separate channel.
            return {
                "finding": None,
                "stop_reason": None,
                "review_note": note,
                "evidence": [
                    {
                        "step": state.get("step", 0),
                        "tool": "human",
                        "args": {},
                        "result": note,
                    }
                ],
            }

        return {"stop_reason": "accepted", "review_note": note}

    def conclude(state: InvestigationState) -> dict:
        if state.get("stop_reason"):
            return {}
        return {
            "stop_reason": "budget",
            "finding": None,
        }

    def decide(state: InvestigationState) -> str:
        """Keep going, or stop. The only edge that can end the run."""
        if state.get("stop_reason"):
            return "conclude"
        if state.get("step", 0) >= state.get("max_steps", 8):
            return "conclude"
        return "act"

    def after_review(state: InvestigationState) -> str:
        """A redirected finding goes back into the loop; anything else ends."""
        return "think" if state.get("stop_reason") is None else "conclude"

    graph = StateGraph(InvestigationState)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("conclude", conclude)

    graph.set_entry_point("think")
    graph.add_edge("act", "think")
    graph.add_edge("conclude", END)

    if review:
        graph.add_node("review", review_node)
        graph.add_conditional_edges("think", decide, {"act": "act", "conclude": "review"})
        graph.add_conditional_edges("review", after_review, {"think": "think", "conclude": "conclude"})
        return graph.compile(checkpointer=InMemorySaver())

    graph.add_conditional_edges("think", decide, {"act": "act", "conclude": "conclude"})
    return graph.compile()


START_STATE = {"evidence": [], "step": 0}


def investigate(model: Model, tools: dict[str, Tool], anomaly: str, max_steps: int = 8):
    """Run to completion with no human in the loop."""
    return build_graph(model, tools).invoke(
        {**START_STATE, "anomaly": anomaly, "max_steps": max_steps}
    )
