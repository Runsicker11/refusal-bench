# refusal-bench

**An eval harness for AI analysts that measures what they refuse to answer.**

Most benchmarks for natural-language-to-SQL and AI analyst tools ask a simple
question: did the agent get the right answer? That is the easy half. The
questions that actually break these systems in production are the ones where
*there is no right answer* — and the agent answers anyway.

This repo is a small, self-contained harness for measuring the other half.

```
Coverage      Asks about a brand or channel not in the data
Capability    Asks for a metric the data cannot support
Ambiguity     Asks for a metric with several valid definitions
Maturity      Asks about a cohort too young to have the window
Fabrication   Asks using a field that does not exist
```

Five categories. In each one, a confident answer *is* the failure.

## Why this exists

A wrong number, stated confidently by an AI to someone who then acts on it, is
the failure mode that quietly ends AI-analytics programs. Not hallucinated
prose — a plausible number, correctly formatted, in a dashboard, wrong.

Semantic layers help. Most semantic-layer work describes what a field *means*.
Very little of it describes where the data *runs out*: which questions the
warehouse genuinely cannot answer, and what the agent should say when it meets
one. That boundary is a design surface, and it is testable.

## What works today

- A synthetic warehouse for **Baseline Athletic**, a fictional D2C and
  marketplace sporting-goods brand. One DuckDB file, deterministic seed, no
  cloud account and no credentials required. Six deliberate gaps, each pinned
  by a test so it cannot be quietly filled in.
- An annotated semantic layer over it — field meanings, topic routing, and
  explicit coverage boundaries, validated against the live warehouse schema.
- A LangGraph investigation loop with one tool (`run_sql`), budgets that halt
  it, and an optional human review checkpoint.
- OpenTelemetry tracing on the GenAI semantic conventions, with token and cost
  accounting. See [docs/observability.md](docs/observability.md).

## Not built yet

The trap taxonomy above is the design, not the implementation. None of this
exists in the repo today:

- The golden question bank and the trap cases
- The investigating agent — hypothesis generation, evidence narrowing,
  explanation with cited evidence
- Deterministic grading and the LLM-as-judge layer
- The CI ratchet and `floors.json`

Tracked in [PLAN.md](PLAN.md) and the
[issues](https://github.com/Runsicker11/refusal-bench/issues).

## Status

Early, and built in the open. Phases 0–2 of six are done. If a claim in this
README is not in the list above, it has not been written yet — for a project
about systems that overstate what they know, a README that does the same thing
would be a poor start.

## Running it

```bash
uv sync
uv run python -m warehouse.seed   # builds baseline.duckdb
uv run pytest                     # 80 tests, no API key, no network
```

Nothing here needs a model key yet. The agent runs against a scripted model in
tests; a real provider adapter arrives with the investigator.

## Built with its own tooling

Planned, not present. Skills for adding a trap case, annotating a semantic
topic, and triaging a failing eval are
[issues #18–#20](https://github.com/Runsicker11/refusal-bench/issues/18) — they
will land alongside the eval suite they operate on.

## License

MIT
