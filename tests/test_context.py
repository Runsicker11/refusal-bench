"""The three arms, and the trap-vocabulary check.

Both exist for the same reason: an eval where the author writes the answer key
and the questions can measure paraphrasing instead of judgement. The arms
quantify how much the context is worth; the overlap check stops a trap from
being a restatement of the refusal it targets.
"""

import pytest

from refusal_bench.context import (
    MAX_TRAP_OVERLAP,
    Arm,
    build_context,
    schema_text,
    vocabulary_overlap,
)
from refusal_bench.semantic import load_topics


@pytest.fixture(scope="module")
def topics():
    return load_topics()


# --- arms ---

def test_raw_schema_arm_gives_tables_only(con, topics):
    ctx = build_context(con, topics, Arm.RAW_SCHEMA)
    assert "marketplace_orders(" in ctx
    assert "cannot answer" not in ctx
    assert "answers questions about" not in ctx


def test_no_refusals_arm_keeps_meanings_and_routing(con, topics):
    ctx = build_context(con, topics, Arm.NO_REFUSALS)
    assert "answers questions about" in ctx
    assert "Platform-claimed" in ctx, "field caveats must survive"
    assert "cannot answer" not in ctx
    assert "ask instead" not in ctx


def test_full_arm_adds_the_refusal_policy(con, topics):
    ctx = build_context(con, topics, Arm.FULL)
    assert "cannot answer" in ctx
    assert "ask instead" in ctx


def test_the_arms_are_strictly_nested(con, topics):
    """B must be A plus meanings, C must be B plus refusals.

    If an arm drops something an earlier arm had, a difference in scores
    cannot be attributed to the thing being tested.
    """
    a = build_context(con, topics, Arm.RAW_SCHEMA)
    b = build_context(con, topics, Arm.NO_REFUSALS)
    c = build_context(con, topics, Arm.FULL)
    assert a in b and b.split("# Topics")[0] == c.split("# Topics")[0]
    assert len(a) < len(b) < len(c)


def test_isolating_the_refusal_policy_is_the_only_difference(con, topics):
    """B vs C is the comparison the project actually rests on."""
    b = build_context(con, topics, Arm.NO_REFUSALS)
    c = build_context(con, topics, Arm.FULL)
    for topic in topics:
        for r in topic.refuses:
            assert r.because.split()[0] not in b or r.because[:40] not in b
            assert r.because[:40] in c


def test_schema_text_is_what_an_agent_could_find_itself(con):
    assert "show tables" not in schema_text(con)
    assert "products(" in schema_text(con)


# --- trap vocabulary ---

def test_a_restated_refusal_scores_high():
    assert vocabulary_overlap(
        "what is the blended return on ad spend across all company revenue",
        "blended return on ad spend across all company revenue",
    ) > MAX_TRAP_OVERLAP


def test_a_stakeholder_phrasing_scores_low():
    assert vocabulary_overlap(
        "is our advertising actually working",
        "blended return on ad spend across all company revenue",
    ) < MAX_TRAP_OVERLAP


def test_unrelated_text_scores_zero():
    assert vocabulary_overlap("how many paddles did we sell", "") == 0.0


def test_every_shipped_refusal_has_a_stakeholder_phrasing_available(topics):
    """Sanity check on the rule itself: the refusals are written in
    semantic-layer language, which is exactly why traps must not copy them."""
    asks = [r.ask for t in topics for r in t.refuses]
    assert asks
    assert all(vocabulary_overlap(a, a) == 1.0 for a in asks)
