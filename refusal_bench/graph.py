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

from refusal_bench import telemetry as tel
from refusal_bench.cost import Budget, price_of
from refusal_bench.model import Model, ToolCall
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
        step = state.get("step", 0) + 1
        with tel.tracer.start_as_current_span("chat") as span:
            span.set_attribute(tel.OPERATION_NAME, "chat")
            span.set_attribute(tel.STEP, step)
            response = model.complete(_prompt(state))

            cost = price_of(
                response.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            span.set_attribute(tel.REQUEST_MODEL, response.model)
            span.set_attribute(tel.USAGE_INPUT_TOKENS, response.usage.input_tokens)
            span.set_attribute(tel.USAGE_OUTPUT_TOKENS, response.usage.output_tokens)
            span.set_attribute(tel.RESPONSE_FINISH_REASONS, [response.finish_reason])
            span.set_attribute(tel.COST_USD, cost)

        totals = {
            "step": step,
            "input_tokens": state.get("input_tokens", 0) + response.usage.input_tokens,
            "output_tokens": state.get("output_tokens", 0) + response.usage.output_tokens,
            "cost_usd": state.get("cost_usd", 0.0) + cost,
        }
        if response.tool_call is None:
            return {**totals, "finding": response.text, "stop_reason": "concluded"}
        # Stored as a plain dict: LangGraph checkpoints this state, and
        # serialising a custom dataclass is a deprecated path it warns about
        # and will block in a future version.
        return {
            **totals,
            "_pending": {"name": response.tool_call.name, "args": dict(response.tool_call.args)},
        }

    def act(state: InvestigationState) -> dict:
        call = ToolCall(**state["_pending"])
        with tel.tracer.start_as_current_span("execute_tool") as span:
            span.set_attribute(tel.OPERATION_NAME, "execute_tool")
            span.set_attribute(tel.TOOL_NAME, call.name)
            span.set_attribute(tel.STEP, state.get("step", 0))
            # ponytail: full arguments on the span. Fine for synthetic data;
            # in a real system this is where a query containing customer
            # identifiers leaks into an observability backend.
            span.set_attribute(tel.TOOL_ARGS, str(dict(call.args))[:1000])

            tool = tools.get(call.name)
            if tool is None:
                # An unknown tool is information the model can recover from,
                # not a crash. Same principle as a malformed query in #24.
                result = f"error: no tool named {call.name!r}. available: {sorted(tools)}"
            else:
                try:
                    result = tool(**call.args)
                except TypeError as exc:
                    # Wrong argument names are the most common tool-call
                    # mistake a model makes, and the one it can fix if told.
                    result = f"error: bad arguments for {call.name!r}: {exc}"
                except Exception as exc:  # noqa: BLE001 - the boundary is the point
                    result = f"error: {call.name!r} failed: {type(exc).__name__}: {exc}"
                    span.record_exception(exc)
            result = str(result)
            span.set_attribute(tel.TOOL_RESULT_CHARS, len(result))
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
        budget = Budget(
            max_steps=state.get("max_steps", 8), max_usd=state.get("max_usd")
        )
        return {
            "stop_reason": "budget",
            "stop_detail": budget.breach(
                state.get("step", 0), state.get("cost_usd", 0.0)
            ),
            "finding": None,
        }

    def decide(state: InvestigationState) -> str:
        """Keep going, review, or stop outright.

        A budget breach goes straight to `conclude`, never through `review`.
        There is nothing for a person to accept -- the run produced no finding
        -- and routing it through review let an exhausted run be recorded as
        'accepted', which is exactly the confusion this repo exists to prevent.
        """
        budget = Budget(
            max_steps=state.get("max_steps", 8), max_usd=state.get("max_usd")
        )
        if budget.breach(state.get("step", 0), state.get("cost_usd", 0.0)):
            return "conclude"
        if state.get("stop_reason"):
            return "review" if review else "conclude"
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
        graph.add_conditional_edges(
            "think", decide, {"act": "act", "review": "review", "conclude": "conclude"}
        )
        graph.add_conditional_edges(
            "review", after_review, {"think": "think", "conclude": "conclude"}
        )
        return graph.compile(checkpointer=InMemorySaver())

    graph.add_conditional_edges("think", decide, {"act": "act", "conclude": "conclude"})
    return graph.compile()


def start_state() -> dict:
    """A fresh starting state.

    A function, not a module constant: a shared `evidence` list would be the
    same object in every run, so the first node that appends in place instead
    of returning a new list would cross-contaminate every subsequent
    investigation in the process.
    """
    return {
        "evidence": [],
        "step": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


def investigate(
    model: Model,
    tools: dict[str, Tool],
    anomaly: str,
    max_steps: int = 8,
    max_usd: float | None = None,
):
    """Run to completion with no human in the loop."""
    with tel.tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute(tel.OPERATION_NAME, "invoke_agent")
        out = build_graph(model, tools).invoke(
            {
                **start_state(),
                "anomaly": anomaly,
                "max_steps": max_steps,
                "max_usd": max_usd,
            }
        )
        span.set_attribute(tel.USAGE_INPUT_TOKENS, out.get("input_tokens", 0))
        span.set_attribute(tel.USAGE_OUTPUT_TOKENS, out.get("output_tokens", 0))
        span.set_attribute(tel.COST_USD, out.get("cost_usd", 0.0))
        span.set_attribute(tel.STOP_REASON, out.get("stop_reason") or "unknown")
        return out
