"""Driving a run that pauses for a human.

LangGraph's interrupt is a first-class pause: the run stops mid-graph, its
state is checkpointed, and resuming continues from that exact point rather than
replaying from the start. That is what makes waiting cheap -- a reviewer can
take a day and the run costs nothing while it waits.

    session = ReviewSession(model, tools)
    pending = session.start("marketplace orders fell 22%")
    # pending is the proposed finding plus the evidence behind it
    result = session.respond("redirect", "the feed was broken that week")
"""

from __future__ import annotations

from itertools import count
from typing import Any

from langgraph.types import Command

from refusal_bench import telemetry as tel
from refusal_bench.graph import Tool, build_graph, start_state
from refusal_bench.model import Model

_threads = count(1)


class ReviewSession:
    def __init__(
        self,
        model: Model,
        tools: dict[str, Tool],
        max_steps: int = 8,
        max_usd: float | None = None,
    ):
        self._graph = build_graph(model, tools, review=True)
        self._config = {"configurable": {"thread_id": f"run-{next(_threads)}"}}
        self._max_steps = max_steps
        self._max_usd = max_usd

    @property
    def state(self) -> dict[str, Any]:
        return self._graph.get_state(self._config).values

    def start(self, anomaly: str) -> dict[str, Any] | None:
        """Run until a human is needed. Returns what they are being asked about."""
        with tel.tracer.start_as_current_span("invoke_agent") as span:
            span.set_attribute(tel.OPERATION_NAME, "invoke_agent")
            out = self._graph.invoke(
                {
                    **start_state(),
                    "anomaly": anomaly,
                    "max_steps": self._max_steps,
                    "max_usd": self._max_usd,
                },
                self._config,
            )
        return self._pending(out)

    def respond(self, action: str, note: str = "") -> dict[str, Any] | None:
        """Accept, reject, or redirect.

        Returns the next pause if the agent went back to work after a redirect,
        or None when the run is finished.
        """
        # A resumed run is its own unit of work, so it gets its own root span.
        # A single trace cannot span a pause that may last days.
        with tel.tracer.start_as_current_span("invoke_agent") as span:
            span.set_attribute(tel.OPERATION_NAME, "invoke_agent")
            out = self._graph.invoke(
                Command(resume={"action": action, "note": note}), self._config
            )
        return self._pending(out)

    @staticmethod
    def _pending(out: dict[str, Any]) -> dict[str, Any] | None:
        interrupts = out.get("__interrupt__")
        return interrupts[0].value if interrupts else None
