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
    # What the agent was told about the warehouse. Varies by arm, which is how
    # the contribution of the semantic layer gets measured rather than assumed.
    context: str

    # Working memory
    hypotheses: list[str]
    evidence: Annotated[list[Evidence], operator.add]
    step: int

    # Budgets. Checked live, in-process -- telemetry export is batched and
    # asynchronous, so by the time a backend knows the run spent $4 it has
    # spent $6.
    max_steps: int
    max_usd: float | None

    # Running totals. The same token counts go onto spans; these are the copy
    # the budget check reads.
    input_tokens: int
    output_tokens: int
    cost_usd: float

    # Output. `stop_reason` is deliberately separate from `finding` -- an
    # investigation that halted on budget is a different outcome from one that
    # concluded, and Phase 4 grades them differently.
    finding: str | None
    stop_reason: str | None
    # Which ceiling was hit, and at what value. A breach is usually a bug in
    # the agent, not a limit set too low, so say what happened.
    stop_detail: str | None

    # What the reviewer said, kept whether they accepted, rejected or
    # redirected. The decision is part of the record, not just its effect.
    review_note: str

    # Internal: the tool call `think` handed to `act`. Underscore-prefixed
    # because it is plumbing between two nodes, not part of the investigation.
    _pending: object
