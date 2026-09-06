"""The human checkpoint.

Workers propose, humans dispose. These tests cover the three things a reviewer
can do, and the one property that makes review worth having at all: a rejected
or redirected finding must not survive as if it were accepted.
"""

from refusal_bench.graph import investigate
from refusal_bench.model import ModelResponse, ScriptedModel, ToolCall
from refusal_bench.session import ReviewSession


def echo(**kwargs) -> str:
    return f"ok: {kwargs}"


TOOLS = {"echo": echo}


def test_review_is_off_by_default():
    """The eval suite runs hundreds of cases. It must not stop for a human."""
    out = investigate(ScriptedModel([ModelResponse(text="done")]), TOOLS, "x")
    assert out["stop_reason"] == "concluded"


def test_pauses_before_publishing_and_shows_its_work():
    session = ReviewSession(
        ScriptedModel([
            ModelResponse(tool_call=ToolCall("echo", {"q": "orders by sku"})),
            ModelResponse(text="BL-PAD-200 went out of stock"),
        ]),
        TOOLS,
    )
    pending = session.start("orders fell 22%")

    assert pending is not None, "the run should have paused"
    assert pending["finding"] == "BL-PAD-200 went out of stock"
    assert pending["evidence"][0]["args"] == {"q": "orders by sku"}
    assert pending["steps"] == 2


def test_accept_publishes_the_finding():
    session = ReviewSession(ScriptedModel([ModelResponse(text="stockout")]), TOOLS)
    session.start("orders fell 22%")
    assert session.respond("accept", "matches what ops told me") is None

    state = session.state
    assert state["stop_reason"] == "accepted"
    assert state["finding"] == "stockout"
    assert state["review_note"] == "matches what ops told me"


def test_reject_discards_the_finding():
    """A rejected conclusion must not survive as though it were accepted."""
    session = ReviewSession(ScriptedModel([ModelResponse(text="demand softened")]), TOOLS)
    session.start("orders fell 22%")
    session.respond("reject", "that is a promo artifact")

    state = session.state
    assert state["stop_reason"] == "rejected"
    assert state["finding"] is None
    assert state["review_note"] == "that is a promo artifact"


def test_redirect_sends_the_agent_back_with_new_context():
    model = ScriptedModel([
        ModelResponse(text="demand softened"),
        ModelResponse(tool_call=ToolCall("echo", {"q": "feed health"})),
        ModelResponse(text="the marketplace feed was down"),
    ])
    session = ReviewSession(model, TOOLS)
    session.start("orders fell 22%")

    second = session.respond("redirect", "the feed was broken that week, check it")
    assert second is not None, "a redirect should produce a new finding to review"
    assert second["finding"] == "the marketplace feed was down"

    session.respond("accept")
    assert session.state["stop_reason"] == "accepted"


def test_the_reviewers_note_reaches_the_agent_as_evidence():
    """Human input is not a separate channel; it is evidence like any other."""
    model = ScriptedModel([
        ModelResponse(text="demand softened"),
        ModelResponse(text="revised"),
    ])
    session = ReviewSession(model, TOOLS)
    session.start("orders fell 22%")
    session.respond("redirect", "the feed was broken that week")

    assert "the feed was broken that week" in model.calls[1]
    assert session.state["evidence"][-1]["tool"] == "human"


def test_waiting_costs_nothing():
    """No model calls happen while a run is paused."""
    model = ScriptedModel([ModelResponse(text="stockout")])
    session = ReviewSession(model, TOOLS)
    session.start("orders fell 22%")
    calls_while_paused = len(model.calls)

    assert session.state["finding"] == "stockout"
    assert len(model.calls) == calls_while_paused
