"""The state carried through one investigation.

State is working memory for a single run. It is not the semantic layer (which
is authored, shared, and static) and it is not telemetry (which records what
happened for humans, and which the agent never reads).

Every node receives the state and returns the keys it changed. `evidence`
accumulates across steps; everything else is replaced.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Evidence(TypedDict):
    """One thing the agent learned, and where it came from."""

    step: int
    tool: str
    args: dict
    result: str


class InvestigationState(TypedDict, total=False):
    # Input
    anomaly: str

    # Working memory
    hypotheses: list[str]
    evidence: Annotated[list[Evidence], operator.add]
    step: int

    # Limits. A step ceiling here is a placeholder for the real budgets in
    # Phase 2; without something, a non-converging loop runs forever.
    max_steps: int

    # Output. `stop_reason` is deliberately separate from `finding` -- an
    # investigation that halted on budget is a different outcome from one that
    # concluded, and Phase 4 grades them differently.
    finding: str | None
    stop_reason: str | None

    # Internal: the tool call `think` handed to `act`. Underscore-prefixed
    # because it is plumbing between two nodes, not part of the investigation.
    _pending: object
