"""The investigation loop.

Three nodes and one conditional edge:

    think ──▶ act ──▶ think ──▶ ... ──▶ conclude ──▶ END
      │                                    ▲
      └────────── decide ──────────────────┘

`think` asks the model what to do next. `act` runs the tool it asked for.
`decide` is the conditional edge: keep going, or stop. `conclude` writes the
finding.

Deliberately thin. There is no hypothesis generation (#30), no evidence
narrowing (#31), no refusal (#33) and no real tool (#24). The only thing this
has to do is terminate, and be shaped so those can be added without rewriting
the loop.
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import END, StateGraph

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


def build_graph(model: Model, tools: dict[str, Tool]):
    """Compile the investigation graph for a given model and tool set."""

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

    graph = StateGraph(InvestigationState)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("conclude", conclude)

    graph.set_entry_point("think")
    graph.add_conditional_edges("think", decide, {"act": "act", "conclude": "conclude"})
    graph.add_edge("act", "think")
    graph.add_edge("conclude", END)

    return graph.compile()


def investigate(model: Model, tools: dict[str, Tool], anomaly: str, max_steps: int = 8):
    return build_graph(model, tools).invoke(
        {"anomaly": anomaly, "evidence": [], "step": 0, "max_steps": max_steps}
    )
