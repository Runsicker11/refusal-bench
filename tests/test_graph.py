"""The loop terminates.

That is the whole job of Phase 1. An investigation agent has no natural
stopping point -- it can always run one more query -- so "does it stop" is the
property worth pinning down before anything interesting is built on top.

All of these run with no API key and no network. ScriptedModel is the point.
"""

import pytest

from refusal_bench.graph import investigate
from refusal_bench.model import ModelResponse, ScriptedModel, ToolCall, Usage


def echo_tool(**kwargs) -> str:
    return f"ok: {kwargs}"


TOOLS = {"echo": echo_tool}


def test_terminates_when_the_model_concludes():
    model = ScriptedModel([ModelResponse(text="marketplace feed broke on the 4th")])
    out = investigate(model, TOOLS, "orders fell 22%")
    assert out["stop_reason"] == "concluded"
    assert out["finding"] == "marketplace feed broke on the 4th"
    assert out["evidence"] == []


def test_gathers_evidence_before_concluding():
    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("echo", {"q": "orders by sku"})),
        ModelResponse(tool_call=ToolCall("echo", {"q": "stock by sku"})),
        ModelResponse(text="BL-PAD-200 went out of stock"),
    ])
    out = investigate(model, TOOLS, "orders fell 22%")
    assert out["stop_reason"] == "concluded"
    assert [e["tool"] for e in out["evidence"]] == ["echo", "echo"]
    assert out["evidence"][0]["args"] == {"q": "orders by sku"}
    assert out["step"] == 3


def test_halts_on_step_ceiling_rather_than_looping_forever():
    """A model that never concludes must not run forever."""
    model = ScriptedModel([ModelResponse(tool_call=ToolCall("echo", {}))] * 20)
    out = investigate(model, TOOLS, "orders fell 22%", max_steps=3)
    assert out["stop_reason"] == "budget"
    assert out["finding"] is None
    assert out["step"] == 3


def test_budget_halt_is_distinct_from_a_conclusion():
    """Phase 4 grades these differently, so they must be distinguishable."""
    concluded = investigate(
        ScriptedModel([ModelResponse(text="done")]), TOOLS, "x"
    )
    halted = investigate(
        ScriptedModel([ModelResponse(tool_call=ToolCall("echo", {}))] * 10),
        TOOLS, "x", max_steps=2,
    )
    assert concluded["stop_reason"] != halted["stop_reason"]
    assert concluded["finding"] is not None and halted["finding"] is None


def test_unknown_tool_is_recoverable_not_fatal():
    """A bad tool name is information the model can act on, not a crash."""
    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("nope", {})),
        ModelResponse(text="recovered"),
    ])
    out = investigate(model, TOOLS, "x")
    assert "error: no tool named" in out["evidence"][0]["result"]
    assert out["stop_reason"] == "concluded"


def test_evidence_is_visible_to_the_next_turn():
    """Without this the loop is not an investigation, just repeated guessing."""
    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("echo", {"q": "first"})),
        ModelResponse(text="done"),
    ])
    investigate(model, TOOLS, "orders fell 22%")
    assert "No evidence gathered yet" in model.calls[0]
    assert "first" in model.calls[1]


def test_scripted_model_exhaustion_is_a_loud_failure():
    model = ScriptedModel([ModelResponse(tool_call=ToolCall("echo", {}))])
    with pytest.raises(AssertionError, match="ran out of responses"):
        investigate(model, TOOLS, "x", max_steps=50)


# --- regressions from the 2026-09-06 review ---

def test_bad_tool_arguments_are_recoverable():
    """The commonest tool-call mistake a model makes, and one it can fix."""
    def run_sql(query: str) -> str:
        return "rows"

    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("run_sql", {"sql": "select 1"})),
        ModelResponse(tool_call=ToolCall("run_sql", {"query": "select 1"})),
        ModelResponse(text="done"),
    ])
    out = investigate(model, {"run_sql": run_sql}, "x")
    assert "bad arguments" in out["evidence"][0]["result"]
    assert out["evidence"][1]["result"] == "rows"
    assert out["stop_reason"] == "concluded"


def test_a_raising_tool_does_not_kill_the_run():
    def boom(**kwargs):
        raise RuntimeError("connection closed")

    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("boom", {})),
        ModelResponse(text="recovered"),
    ])
    out = investigate(model, {"boom": boom}, "x")
    assert "RuntimeError: connection closed" in out["evidence"][0]["result"]
    assert out["stop_reason"] == "concluded"


def test_start_state_hands_out_a_fresh_list_every_time():
    """The earlier version of this test was vacuous.

    It ran two investigations and asserted each saw one piece of evidence --
    which passed even with the shared module-level dict restored, because no
    node currently appends in place. Assert the actual property instead:
    successive callers must not receive the same list object.
    """
    from refusal_bench.graph import start_state

    a, b = start_state(), start_state()
    assert a["evidence"] is not b["evidence"]

    a["evidence"].append({"step": 0, "tool": "x", "args": {}, "result": "y"})
    assert b["evidence"] == [], "a mutation by one run reached another"
    assert start_state()["evidence"] == []


def test_a_tool_with_an_internal_type_error_is_not_blamed_on_the_model():
    """"Bad arguments" invites a retry that cannot fix a broken tool."""
    def buggy(**kwargs):
        return 1 + None  # TypeError from inside the tool

    model = ScriptedModel([
        ModelResponse(tool_call=ToolCall("buggy", {})),
        ModelResponse(text="done"),
    ])
    out = investigate(model, {"buggy": buggy}, "x")
    result = out["evidence"][0]["result"]
    assert "failed: TypeError" in result
    assert "bad arguments" not in result
