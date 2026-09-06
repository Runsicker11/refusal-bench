"""Regenerate docs/graph.md from the compiled graph.

    uv run python scripts_graph.py

The diagram is generated, never hand-drawn. A hand-drawn diagram is accurate
on the day it is committed and wrong within a month; tests/test_graph_doc.py
fails if the committed file drifts from the code.
"""

from pathlib import Path

from refusal_bench.graph import build_graph
from refusal_bench.model import ScriptedModel

DOC = Path(__file__).parent / "docs" / "graph.md"

HEADER = """# The investigation graph

Generated from the compiled graphs by `scripts_graph.py`. Do not edit by hand.

## Unattended

How the eval suite runs it. No human, no pauses.

```mermaid
"""

MIDDLE = """```

## With review

`review=True`. The run freezes before the finding is published and waits for a
person. A redirect sends it back into the loop with the reviewer's note added
as evidence; accept and reject both end the run.

```mermaid
"""

FOOTER = """```

## Reading it

Solid arrows are unconditional. **Dotted arrows are the conditional edge** —
`decide` chooses between them after every `think`.

| Node | Does |
|---|---|
| `think` | Asks the model what to do next. Returns either a tool call or a finding. |
| `act` | Runs the requested tool and appends the result to `evidence`. |
| `review` | Pauses for a person. Accept, reject, or redirect. Only present when `review=True`. |
| `conclude` | Writes the finding, or records that the run hit its budget. |

The loop is `think → act → think`. It leaves only through `conclude`, and
`decide` is the only thing that can send it there — either because the model
stopped asking for tools, or because the step ceiling was reached.

Those exits are recorded differently in `stop_reason` — `concluded`,
`accepted`, `rejected`, or `budget`. A run that ran out of budget is not a run
that reached a conclusion, and a rejected finding is not an accepted one.
Nothing downstream should be able to confuse them.
"""


def _mermaid(review: bool) -> str:
    return build_graph(ScriptedModel([]), {}, review=review).get_graph().draw_mermaid().strip()


def render() -> str:
    return (
        HEADER + _mermaid(review=False) + "\n"
        + MIDDLE + _mermaid(review=True) + "\n"
        + FOOTER
    )


if __name__ == "__main__":
    DOC.parent.mkdir(exist_ok=True)
    DOC.write_text(render())
    print(f"wrote {DOC}")
