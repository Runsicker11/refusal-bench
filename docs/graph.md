# The investigation graph

Generated from the compiled graph by `scripts_graph.py`. Do not edit by hand.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	think(think)
	act(act)
	conclude(conclude)
	__end__([<p>__end__</p>]):::last
	__start__ --> think;
	act --> think;
	think -.-> act;
	think -.-> conclude;
	conclude --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

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
