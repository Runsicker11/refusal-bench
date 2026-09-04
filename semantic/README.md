# The semantic layer

One YAML file per topic. A topic is a queryable subject area over the warehouse.

```yaml
topic: ad_efficiency
description: What this topic is for.
grain: [spend_date, campaign]     # columns that make a row unique
tables: [ad_spend]                # tables this topic owns

fields:
  attributed_revenue:
    means: Plain-language definition. Required.
    caveat: Optional. Where the field misleads if read naively.

routes_here:                      # questions this topic should answer
  - return on ad spend by campaign

refuses:                          # questions it must decline
  - ask: blended return on ad spend across all company revenue
    because: The specific missing input. Required.
    instead: The nearest answerable question. Required.
```

## Why `refuses` has three keys

Conventional semantic layers describe what fields mean. They rarely describe
where the data runs out, so an agent reading one has no way to distinguish
"this is hard" from "this is impossible", and it guesses.

`because` must name the *specific* missing input. "We don't have that data" is
not a reason — it tells the person nothing about whether to go find the data,
reframe the question, or drop it.

`instead` is required because a refusal with no alternative is a stonewall.
"I cannot answer that" satisfies a naive refusal check and is nearly useless to
the person who asked. Requiring an alternative makes the difference structural,
so the deterministic grader can tell a good refusal from a bare one without
needing a judge.

## Validation

Field and grain names are checked against the live DuckDB schema, so the
semantic layer cannot drift from the tables it describes. Run:

```bash
uv run pytest tests/test_semantic.py
```
