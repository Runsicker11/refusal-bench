# Plan

## What this is

An agentic analyst that investigates anomalies in a data warehouse — and the
harness that measures whether it can be trusted.

Given "marketplace orders dropped 22% last week," the agent proposes candidate
explanations, queries the warehouse to support or refute each one, narrows the
field, and produces an explanation with cited evidence. Or it declines to
conclude, and says exactly why.

## Why investigation rather than question-answering

Text-to-SQL is a solved-enough demo. Ask a question, get a number.

Investigation is different in three ways that matter:

1. **It is multi-step**, so there is a *trajectory* to inspect and grade, not
   just a final answer. An agent that reaches a correct conclusion through
   incoherent reasoning got lucky, and a final-answer grader cannot tell.
2. **A wrong explanation is worse than a wrong number.** A number gets checked.
   An explanation tells someone *why* something happened, and they act on the
   why. The cost of a confident wrong answer is higher, so the bar for refusing
   is different.
3. **The interesting failure is silence about uncertainty.** Real anomalies
   often have two plausible causes the data cannot separate. Naming that is the
   correct answer, and almost nothing is built to produce it.

## The design position

Most work on making warehouses legible to models describes what fields *mean*.
Very little describes where the data *runs out* — which questions cannot be
answered, and what the agent should say when it meets one.

This repo treats that boundary as a first-class design surface, and tests it.
The semantic layer's `refuses` blocks require three keys: the question, the
specific missing input, and the nearest answerable alternative. A refusal
without an alternative is a stonewall, and a stonewall passes a naive check
while being useless to whoever asked.

## Two sources of context

The semantic layer describes what fields *mean*. It cannot describe what
*happened* — the promo, the broken feed, the price change, the stockout. Those
are the actual causes of most anomalies, and an agent that only knows field
definitions will confidently attribute a promo-driven spike to organic demand.

So there are two stores, with a stated precedence rule:

| Store | Owns | Example |
|---|---|---|
| **Semantic layer** | mechanics — which table, which grain, which join, what a field means | `attributed_revenue` is platform-claimed and does not reconcile to orders |
| **Knowledge notes** | meaning and history — dated operational facts | "20% off sitewide, 2026-03-14 to 2026-03-17" |

When they disagree about what something means, the notes win. Skills and the
semantic layer own mechanics; notes own meaning and history. Without a stated
precedence rule, two sources of context drift into two different answers and
nobody can tell which is authoritative.

Notes record what things mean and what happened, **never what a metric
currently equals**. A number written into a note is stale within a week and
quietly poisons everything built on it. Live numbers resolve at query time.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Agent framework | **LangGraph** (Python) | We own the loop, the state schema, and every edge. Model-agnostic. Checkpointing and human-in-the-loop interrupts built in. A framework where the vendor owns the loop would make this a configuration exercise. |
| Observability | **OpenTelemetry GenAI semantic conventions** | Vendor-neutral. `invoke_agent` → `chat` → `execute_tool` span tree gives the full reasoning chain. And `gen_ai.usage.*_tokens` are span attributes, so tracing and cost accounting are one instrumentation pass, not two. |
| Warehouse | **DuckDB, synthetic, deterministic seed** | One file, no credentials, no cloud account, runs in CI in seconds. Anything needing a cloud project will not get run by the people evaluating it. |
| Durability | **Deferred** (Phase 5 spike) | LangGraph checkpoints but does not do crash recovery. Temporal is the documented path. Worth trying, not worth starting with. |

## The warehouse has deliberate holes

Baseline Athletic is a fictional D2C and marketplace racquet-sports brand.
Eight tables. Six gaps, each one load-bearing:

| Gap | What it makes untestable |
|---|---|
| `ad_spend` carries attributed revenue only | blended ad efficiency |
| one marketplace, not all channels | total channel mix |
| `competitor_share` covers two rivals | category share |
| customers are US and CA only | any other region |
| subscriptions begin mid-history | early-cohort tenure |
| no returns table exists | return rate, net revenue |

`tests/test_seed.py` asserts every one of these is still a gap. Filling one
would silently turn a whole class of trap cases into ordinary questions, and
nothing else in the repo would fail.

## Phases

Each phase ends with something that runs.

### Phase 0 — Foundation ✅
Warehouse, semantic layer format, validator.
`#1` ✅ · `#2` ✅ · `#3`

### Phase 1 — Agent skeleton
The thinnest LangGraph loop that terminates. State schema, one tool, one
human-in-the-loop interrupt. No hypothesis logic, no refusal, no evals.
Diagram: [docs/graph.md](docs/graph.md), generated from the compiled graph.
`#12` ✅ · `#24` ✅ · `#25` ✅

### Phase 2 — Instrumentation ✅
OTel GenAI spans, token and cost accounting, budgets that halt a runaway loop,
traces exported to a backend. Done before the agent gets complicated, because
debugging an uninstrumented agent is guesswork.
See [docs/observability.md](docs/observability.md).
`#26` ✅ · `#27` ✅ · `#28` ✅ · `#29` ✅

### Phase 3 — The investigator
Hypothesis generation, evidence gathering and narrowing, explanation with
cited evidence, refusal wired into conclusions, reusable domain skills, and the
knowledge notes the semantic layer cannot hold.
`#30` · `#31` · `#32` · `#33` · `#34` · `#38` · `#39`

### Phase 4 — Evals and the ratchet
Golden cases, five trap categories, trajectory grading, LLM-as-judge with a
measured judge/human agreement rate, and `floors.json` — committed per-category
pass rates that CI enforces and that only move up.
`#4`–`#11` · `#13`–`#20` · `#35`

### Phase 5 — Durability *(optional)*
Temporal spike. Can an investigation survive a process restart? Is the
complexity justified at this scale? An honest no is a publishable result.
`#36`

### Phase 6 — Writing
`#21` · `#22` · `#23`

## Running it

```bash
uv sync
uv run python -m warehouse.seed
uv run pytest
```

No API key needed for the warehouse or the deterministic grader. The agent and
the judge need a model key; telemetry export is optional and off by default.
