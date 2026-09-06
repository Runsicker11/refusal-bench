"""What a run cost, and when to stop it.

Two things that share a source and nothing else.

**Cost accounting** is derived: token counts come back on the model response,
and a price table turns them into dollars. Reporting.

**Budgets** are enforced live, in-process. They cannot read from the telemetry
backend, because span export is batched and asynchronous -- by the time
Honeycomb knows the run spent $4, it has spent $6. So the same token counts
feed two consumers: one exported, one checked on every turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PRICES = json.loads((Path(__file__).parent / "pricing.json").read_text())


def price_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD for one call. An unknown model costs nothing rather than guessing.

    A wrong number here is worse than no number -- a budget built on a
    fabricated price halts runs that were fine, or fails to halt ones that
    were not.
    """
    rates = _PRICES.get(model)
    if rates is None:
        return 0.0
    return (
        input_tokens * rates["input"] + output_tokens * rates["output"]
    ) / 1_000_000


@dataclass(frozen=True)
class Budget:
    """Ceilings. Whichever is hit first stops the run.

    A breach is usually a bug in the agent rather than a limit set too low, so
    the halt reports which ceiling and at what value.
    """

    max_steps: int = 8
    max_usd: float | None = None

    def breach(self, step: int, spent_usd: float) -> str | None:
        if step >= self.max_steps:
            return f"step ceiling reached ({self.max_steps} steps)"
        if self.max_usd is not None and spent_usd >= self.max_usd:
            return f"cost ceiling reached (${spent_usd:.4f} of ${self.max_usd:.2f})"
        return None


def summarize(state: dict) -> str:
    """One line at the end of a run."""
    return (
        f"steps={state.get('step', 0)} "
        f"tokens_in={state.get('input_tokens', 0)} "
        f"tokens_out={state.get('output_tokens', 0)} "
        f"cost=${state.get('cost_usd', 0.0):.4f} "
        f"stop={state.get('stop_reason')}"
    )
