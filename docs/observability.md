# Observability

Every run emits an OpenTelemetry trace following the
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

```
invoke_agent   "marketplace orders fell 22%"        stop=concluded  $0.0036
├─ chat            claude-sonnet-5   in 1,000  out 100   finish=tool_calls
├─ execute_tool    run_sql           args="select ... from marketplace_orders"
├─ chat            claude-sonnet-5   in 1,000  out 100   finish=stop
└─ ...
```

## Why the conventions matter

They are a naming agreement, not a library. Because the spans carry
`gen_ai.usage.input_tokens` rather than `tokens_in`, any OTel-native backend
renders these as agent traces with no custom configuration.

The attribute names are string constants in `refusal_bench/telemetry.py` rather
than imports from `opentelemetry-semantic-conventions`. The GenAI conventions
are still incubating and those names move between releases; a spec change
should be a visible edit here, not a silent behaviour change on upgrade.

## Nothing is required

With no exporter configured, OpenTelemetry installs a no-op tracer. The library
instruments unconditionally; where the data goes is your decision, and the
default is nowhere. The full test suite runs with no backend and no key.

## Seeing the trace

Print it to the terminal:

```python
from refusal_bench import telemetry
telemetry.configure("console")
```

Ship it to Honeycomb (free tier is enough):

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=YOUR_KEY"
export OTEL_SERVICE_NAME=refusal-bench
```

```python
telemetry.configure("otlp")
```

Any OTLP/HTTP backend works — Grafana Tempo, Jaeger, Datadog, an OTel
Collector. Honeycomb is the example because the free tier needs no card.

## Cost and budgets are not the same thing

Token counts come back on the model response and go two places:

```
model response
  ├─▶ span attributes  ─▶  exported  ─▶  backend
  └─▶ running total    ─▶  budget check  ─▶  halt
```

**Cost accounting is derived and after the fact.** Prices live in
`refusal_bench/pricing.json` — data, so a price change is an edit rather than a
release. An unknown model costs zero rather than a guess: a fabricated price
would halt healthy runs or fail to halt sick ones.

**Budgets are enforced live, in-process.** They cannot read from the telemetry
backend, because span export is batched and asynchronous — by the time the
backend knows a run spent $4, it has spent $6.

```python
investigate(model, tools, anomaly, max_steps=8, max_usd=0.50)
```

A breach halts the run and records *which* ceiling and at what value:

```
stop_reason = "budget"
stop_detail = "cost ceiling reached ($0.5200 of $0.50)"
```

`budget` is a distinct outcome from `concluded`. A truncated investigation must
not be mistakable for an answer.

## One known leak

Tool arguments go onto the span verbatim. Fine for a synthetic warehouse; in a
real system that is exactly where a query containing customer identifiers ends
up in an observability backend. Marked with a `ponytail:` comment in
`graph.py` rather than solved, because the fix is a redaction policy and this
repo has nothing to redact.
