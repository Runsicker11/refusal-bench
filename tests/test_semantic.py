"""The semantic layer is coherent, and the validator actually catches drift.

Half these tests check the real layer. The other half feed the validator
deliberately broken topics, because a validator nobody has seen fail is just a
function that returns an empty list.
"""

import pytest

from refusal_bench.semantic import (
    Refusal,
    Topic,
    load_and_validate,
    load_topics,
    validate,
    warehouse_schema,
)


def _topic(**over) -> Topic:
    base = dict(
        topic="t",
        description="d",
        grain=["spend_date"],
        tables=["ad_spend"],
        fields={"spend": {"means": "cost"}},
        routes_here=["cost per click"],
        refuses=[Refusal(ask="a", because="b", instead="c")],
    )
    return Topic(**{**base, **over})


# --- the real layer ---

def test_real_layer_is_valid(con):
    topics = load_and_validate(con)
    assert topics


def test_every_refusal_names_a_reason_and_an_alternative():
    for t in load_topics():
        for r in t.refuses:
            assert r.because.strip(), f"{t.topic}: '{r.ask}' has no reason"
            assert r.instead.strip(), f"{t.topic}: '{r.ask}' has no alternative"


def test_refusal_reasons_are_specific():
    """'We don't have that data' is not a reason. Require some substance."""
    for t in load_topics():
        for r in t.refuses:
            assert len(r.because.split()) >= 12, (
                f"{t.topic}: reason for '{r.ask}' is too thin to be useful"
            )


# --- the validator ---

def test_catches_unknown_table(con):
    errors = validate([_topic(tables=["nope"])], warehouse_schema(con))
    assert any("unknown table" in e for e in errors)


def test_catches_unknown_field(con):
    errors = validate(
        [_topic(fields={"not_a_column": {"means": "x"}})], warehouse_schema(con)
    )
    assert any("is not in" in e for e in errors)


def test_catches_field_with_no_meaning(con):
    errors = validate([_topic(fields={"spend": {}})], warehouse_schema(con))
    assert any("no 'means'" in e for e in errors)


def test_catches_bad_grain(con):
    errors = validate([_topic(grain=["nope"])], warehouse_schema(con))
    assert any("grain column" in e for e in errors)


def test_catches_empty_routing(con):
    errors = validate([_topic(routes_here=[])], warehouse_schema(con))
    assert any("routes_here is empty" in e for e in errors)


def test_catches_refusal_with_no_reason(con):
    bad = _topic(refuses=[Refusal(ask="a", because="  ", instead="c")])
    errors = validate([bad], warehouse_schema(con))
    assert any("no reason" in e for e in errors)


def test_catches_stonewall(con):
    """A refusal with no alternative is the failure this format exists to stop."""
    bad = _topic(refuses=[Refusal(ask="a", because="a real reason", instead="")])
    errors = validate([bad], warehouse_schema(con))
    assert any("stonewall" in e for e in errors)


def test_catches_duplicate_topics(con):
    errors = validate([_topic(), _topic()], warehouse_schema(con))
    assert any("duplicate topic" in e for e in errors)


def test_load_and_validate_raises_on_bad_layer(con, tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "topic: b\ndescription: d\ngrain: [nope]\ntables: [ad_spend]\n"
        "fields: {spend: {means: cost}}\nroutes_here: [x]\n"
    )
    with pytest.raises(ValueError, match="semantic layer is invalid"):
        load_and_validate(con, tmp_path)


def test_a_token_alternative_is_still_a_stonewall(con):
    """Non-empty is not the same as useful.

    Found in the 2026-09-07 adversarial review: `because` was checked for
    substance and `instead` only for non-emptiness, so "see the dashboard"
    passed the very check built to prevent stonewalling.
    """
    bad = _topic(refuses=[Refusal(
        ask="blended return on ad spend",
        because="ad_spend carries platform-attributed revenue only and cannot be joined to orders at this grain",
        instead="see the dashboard",
    )])
    errors = validate([bad], warehouse_schema(con))
    assert any("too thin to act on" in e for e in errors)
