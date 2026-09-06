"""Traces, cost accounting, and budgets.

The trace is what Phase 4 grades: every hypothesis, tool call and decision is
already a span. So the shape of the tree is not cosmetic -- it is the recording
that trajectory grading reads.
"""

import pytest

from refusal_bench import telemetry as tel
from refusal_bench.cost import Budget, price_of, summarize
from refusal_bench.graph import investigate
from refusal_bench.model import ModelResponse, ScriptedModel, ToolCall, Usage


def echo(**kwargs) -> str:
    return "ok"


TOOLS = {"echo": echo}


def _priced(text="", tool_call=None, tin=1000, tout=100):
    return ModelResponse(
        text=text, tool_call=tool_call,
        usage=Usage(input_tokens=tin, output_tokens=tout),
        model="claude-sonnet-5",
    )


# --- span tree ---

def test_span_tree_matches_the_genai_conventions():
    with tel.capture() as spans:
        investigate(
            ScriptedModel([
                _priced(tool_call=ToolCall("echo", {"q": "x"})),
                _priced(text="done"),
            ]),
            TOOLS, "orders fell 22%",
        )
    names = [s.name for s in spans.get_finished_spans()]
    assert names == ["chat", "execute_tool", "chat", "invoke_agent"]


def test_chat_spans_carry_the_convention_attributes():
    with tel.capture() as spans:
        investigate(ScriptedModel([_priced(text="done")]), TOOLS, "x")
    chat = next(s for s in spans.get_finished_spans() if s.name == "chat")
    assert chat.attributes[tel.REQUEST_MODEL] == "claude-sonnet-5"
    assert chat.attributes[tel.USAGE_INPUT_TOKENS] == 1000
    assert chat.attributes[tel.USAGE_OUTPUT_TOKENS] == 100
    assert chat.attributes[tel.RESPONSE_FINISH_REASONS] == ("stop",)
    assert chat.attributes[tel.OPERATION_NAME] == "chat"


def test_finish_reason_distinguishes_a_tool_call_from_a_conclusion():
    with tel.capture() as spans:
        investigate(
            ScriptedModel([
                _priced(tool_call=ToolCall("echo", {})),
                _priced(text="done"),
            ]),
            TOOLS, "x",
        )
    reasons = [
        s.attributes[tel.RESPONSE_FINISH_REASONS]
        for s in spans.get_finished_spans() if s.name == "chat"
    ]
    assert reasons == [("tool_calls",), ("stop",)]


def test_tool_spans_record_the_call_and_the_result_size():
    with tel.capture() as spans:
        investigate(
            ScriptedModel([
                _priced(tool_call=ToolCall("echo", {"q": "orders by sku"})),
                _priced(text="done"),
            ]),
            TOOLS, "x",
        )
    tool = next(s for s in spans.get_finished_spans() if s.name == "execute_tool")
    assert tool.attributes[tel.TOOL_NAME] == "echo"
    assert "orders by sku" in tool.attributes[tel.TOOL_ARGS]
    assert tool.attributes[tel.TOOL_RESULT_CHARS] == 2


def test_root_span_carries_the_run_totals():
    with tel.capture() as spans:
        investigate(
            ScriptedModel([
                _priced(tool_call=ToolCall("echo", {})),
                _priced(text="done"),
            ]),
            TOOLS, "x",
        )
    root = next(s for s in spans.get_finished_spans() if s.name == "invoke_agent")
    assert root.attributes[tel.USAGE_INPUT_TOKENS] == 2000
    assert root.attributes[tel.STOP_REASON] == "concluded"
    assert root.attributes[tel.COST_USD] > 0


def test_tracing_is_free_when_nothing_is_configured():
    """No exporter, no backend, no key. The library must still run."""
    out = investigate(ScriptedModel([_priced(text="done")]), TOOLS, "x")
    assert out["stop_reason"] == "concluded"


# --- cost ---

def test_price_table_is_applied():
    # 1M in + 1M out on sonnet = $3 + $15
    assert price_of("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_unknown_model_costs_nothing_rather_than_guessing():
    """A fabricated price would halt healthy runs or fail to halt sick ones."""
    assert price_of("some-model-we-have-never-heard-of", 10**9, 10**9) == 0.0


def test_run_accumulates_cost_and_tokens():
    out = investigate(
        ScriptedModel([
            _priced(tool_call=ToolCall("echo", {})),
            _priced(text="done"),
        ]),
        TOOLS, "x",
    )
    assert out["input_tokens"] == 2000
    assert out["output_tokens"] == 200
    assert out["cost_usd"] == pytest.approx(2 * (1000 * 3 + 100 * 15) / 1e6)


def test_summary_line():
    out = investigate(ScriptedModel([_priced(text="done")]), TOOLS, "x")
    line = summarize(out)
    assert "steps=1" in line and "tokens_in=1000" in line and "stop=concluded" in line


# --- budgets ---

def test_cost_ceiling_halts_the_run():
    model = ScriptedModel([_priced(tool_call=ToolCall("echo", {}))] * 20)
    out = investigate(model, TOOLS, "x", max_steps=50, max_usd=0.01)
    assert out["stop_reason"] == "budget"
    assert "cost ceiling" in out["stop_detail"]
    assert out["cost_usd"] >= 0.01


def test_step_ceiling_says_which_ceiling_it_was():
    model = ScriptedModel([_priced(tool_call=ToolCall("echo", {}))] * 20)
    out = investigate(model, TOOLS, "x", max_steps=3)
    assert out["stop_reason"] == "budget"
    assert "step ceiling" in out["stop_detail"]


def test_a_healthy_run_records_no_breach():
    out = investigate(ScriptedModel([_priced(text="done")]), TOOLS, "x")
    assert out.get("stop_detail") is None


def test_budget_reports_which_limit_and_at_what_value():
    assert Budget(max_steps=5).breach(5, 0.0) == "step ceiling reached (5 steps)"
    detail = Budget(max_steps=99, max_usd=0.5).breach(1, 0.52)
    assert "$0.5200 of $0.50" in detail


def test_budgets_are_checked_in_process_not_from_telemetry():
    """No exporter configured, yet the cost ceiling still fires."""
    model = ScriptedModel([_priced(tool_call=ToolCall("echo", {}))] * 20)
    out = investigate(model, TOOLS, "x", max_steps=50, max_usd=0.005)
    assert out["stop_reason"] == "budget"
