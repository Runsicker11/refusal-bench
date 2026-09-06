"""OpenTelemetry instrumentation, following the GenAI semantic conventions.

The conventions are a naming agreement, not a library: the OTel GenAI working
group published attribute names so that tools can read each other's traces.
Because we emit `gen_ai.usage.input_tokens` rather than `tokens_in`, any
OTel-native backend renders these as agent traces with no custom configuration.

Span tree per run:

    invoke_agent
    ├── chat            one per model call
    ├── execute_tool    one per tool call
    ├── chat
    └── ...

**No backend is required.** With no exporter configured, OpenTelemetry installs
a no-op tracer and the spans cost almost nothing. The library instruments
unconditionally; where the data goes is the caller's decision, and the default
is nowhere.

The constants below are string literals on purpose. The GenAI conventions are
still incubating and the names in `opentelemetry-semantic-conventions` move
between releases; a spec change should be a visible edit here, not a silent
behaviour change on upgrade.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export import ConsoleSpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# --- GenAI semantic conventions ---
OPERATION_NAME = "gen_ai.operation.name"
REQUEST_MODEL = "gen_ai.request.model"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
TOOL_NAME = "gen_ai.tool.name"

# Not in the spec. Ours, namespaced so it is obviously not a convention.
COST_USD = "refusal_bench.cost_usd"
STEP = "refusal_bench.step"
TOOL_ARGS = "refusal_bench.tool.args"
TOOL_RESULT_CHARS = "refusal_bench.tool.result_chars"
STOP_REASON = "refusal_bench.stop_reason"

tracer = trace.get_tracer("refusal_bench")

_memory = InMemorySpanExporter()


def _own_provider() -> TracerProvider | None:
    provider = trace.get_tracer_provider()
    return provider if isinstance(provider, TracerProvider) else None


_memory_attached = False


def _install() -> TracerProvider:
    provider = _own_provider()
    if provider is None:
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    return provider


def _attach_memory() -> None:
    """Attach the in-memory exporter once. Processors cannot be removed, so
    adding one per `capture()` call would stack up across a test session."""
    global _memory_attached
    if not _memory_attached:
        _install().add_span_processor(SimpleSpanProcessor(_memory))
        _memory_attached = True


def configure(exporter: str = "console") -> None:
    """Point the traces somewhere. Optional; nothing calls this by default.

    `console` prints the span tree to the terminal -- no key, no network.
    `otlp` ships to any OTLP/HTTP backend. For Honeycomb, set:

        OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
        OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<your key>
    """
    provider = _install()
    if exporter == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            raise ValueError(
                "OTEL_EXPORTER_OTLP_ENDPOINT is not set. For Honeycomb use "
                "https://api.honeycomb.io with OTEL_EXPORTER_OTLP_HEADERS="
                "x-honeycomb-team=<key>"
            )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        raise ValueError(f"unknown exporter {exporter!r}; use 'console' or 'otlp'")


@contextmanager
def capture():
    """Collect spans in memory. For tests and for asserting on trace shape.

    Cleared on entry, not on exit -- the spans stay readable after the block,
    which is where assertions naturally live.
    """
    _attach_memory()
    _memory.clear()
    yield _memory
