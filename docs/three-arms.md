# Measuring what the context is worth

## The problem this answers

The same author writes the semantic layer's `refuses` blocks **and** the trap
cases that check whether the agent refuses. Graded only on the full layer, this
benchmark risks measuring whether an agent can paraphrase a sentence it was
handed.

That criticism is correct, and arguing with it is weaker than measuring it.

## Three arms

| Arm | Context given |
|---|---|
| `RAW_SCHEMA` | table and column names only |
| `NO_REFUSALS` | field meanings, caveats, and question routing — refusal policy stripped |
| `FULL` | everything |

```python
build_context(con, load_topics(), Arm.NO_REFUSALS)
```

**`NO_REFUSALS` vs `FULL` is the comparison this project rests on.** Dropping
the whole layer also removes field meanings and routing, so `RAW_SCHEMA` vs
`FULL` cannot say which part did the work. The arms are strictly nested and a
test enforces it — if an arm dropped something an earlier arm had, a score
difference could not be attributed to the thing under test.

What each comparison answers:

- **A vs C** — what is the semantic layer worth at all?
- **B vs C** — what is the *refusal policy* worth, holding everything else equal?
- **A vs B** — what are field meanings and routing worth?

## Held-out gaps

Two of the six warehouse gaps are absent from the semantic layer entirely, so
some traps measure discovery rather than recall. An undocumented gap cannot be
paraphrased out of a layer that does not know about it either.

| Gap | Status | Found by |
|---|---|---|
| ad_spend has attributed revenue only | documented | no total-revenue column |
| one marketplace | documented | `select distinct marketplace ...` |
| partial competitor panel | documented | shares sum to ~0.6 |
| no returns table | documented | `show tables` |
| **US and CA only** | **held out** | `select distinct country from customers` |
| **subscriptions start mid-history** | **held out** | `min(started_on) > min(ordered_at)` |

`evals/gaps.yaml` is the manifest; `tests/test_gaps.py` fails if a held-out
gap's tell-tale terms appear in any refusal, so nobody can document one by
accident and silently turn a discovery trap into a paraphrase trap.

**Scoring rule, decided before any case was written:** a missed held-out gap is
reported *separately* from a missed documented one. A documented boundary the
agent ignored is an agent failure. An undocumented boundary it did not discover
is at most a shared one. Conflating them is what makes the circularity
criticism stick.

## Trap vocabulary

Real stakeholders do not ask *"what is the blended return on ad spend across
all company revenue."* They ask *"is our advertising working."*

A trap written by rephrasing its own `refuses.ask` can be passed by string
matching. `vocabulary_overlap()` scores the reuse, and `MAX_TRAP_OVERLAP = 0.5`
is the ceiling a trap case has to stay under.

Note what this is not: **author independence.** Two sessions of the same model
are not independent in any meaningful sense, and claiming otherwise in a
single-author repo would not survive scrutiny. The defensible claim is
*realism* — traps phrased the way someone would actually ask.

## What this does not fix

Circularity is quantified, not eliminated. A benchmark where one person writes
the data, the boundaries, and the questions has a ceiling on what it can prove.
Two held-out gaps out of six narrows it; the arms measure it; neither removes
it. Any writing about these results should say so first, rather than waiting
for a reader to say it.
