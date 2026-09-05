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

Generated from the compiled graph by `scripts_graph.py`. Do not edit by hand.

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
| `conclude` | Writes the finding, or records that the run hit its budget. |

The loop is `think → act → think`. It leaves only through `conclude`, and
`decide` is the only thing that can send it there — either because the model
stopped asking for tools, or because the step ceiling was reached.

Those two exits are recorded differently in `stop_reason`. A run that ran out
of budget is not a run that reached a conclusion, and nothing downstream should
be able to confuse them.
"""


def render() -> str:
    graph = build_graph(ScriptedModel([]), {})
    return HEADER + graph.get_graph().draw_mermaid().strip() + "\n" + FOOTER


if __name__ == "__main__":
    DOC.parent.mkdir(exist_ok=True)
    DOC.write_text(render())
    print(f"wrote {DOC}")
