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

## What's in here

- A synthetic warehouse for **Baseline Athletic**, a fictional D2C and
  marketplace sporting-goods brand. One DuckDB file, deterministic seed, no
  cloud account and no credentials required.
- An annotated semantic layer over it — field meanings, topic routing, and
  explicit coverage boundaries.
- A golden question bank with hidden answers, plus the trap cases above.
- Deterministic grading, and an LLM-as-judge layer for refusal *quality*
  (does the agent explain what is missing, or just stonewall?) with a measured
  judge/human agreement rate.
- **A CI ratchet.** `floors.json` holds a committed pass rate per category.
  Passing raises the floor; regressing fails the build. Quality is structurally
  monotonic — it cannot get worse without someone noticing.

## Status

Early. Building in public, one issue at a time. See the
[issues](https://github.com/Runsicker11/refusal-bench/issues) for the plan.

## Running it

```bash
uv sync
uv run python -m warehouse.seed      # builds baseline.duckdb
uv run pytest                        # deterministic grading
uv run python -m refusal_bench.ratchet --check
```

The deterministic suite needs no API key. The judge layer needs
`ANTHROPIC_API_KEY`.

## Built with its own tooling

`.claude/skills/` contains the Claude Code skills used to build and maintain
this repo — adding a trap case, annotating a semantic topic, triaging a failing
eval. The harness is developed with the same kind of agent tooling it exists to
measure.

## License

MIT
