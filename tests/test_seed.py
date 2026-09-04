"""The seed is deterministic, and the deliberate gaps are still gaps.

The hole assertions matter more than the fingerprint. Every trap case depends on
a question the warehouse genuinely cannot answer; a well-meaning contributor
adding a total_revenue column to ad_spend would silently turn a whole category
of traps into ordinary questions, and nothing else would fail.
"""

import duckdb
import pytest

import random

from warehouse.seed import SEED, build, fingerprint


@pytest.fixture(scope="session")
def con():
    c = duckdb.connect(":memory:")
    build(c, random.Random(SEED))
    yield c
    c.close()


def test_deterministic(con):
    # ponytail: one extra full build (~14s). Fine at this size; if the suite gets
    # slow, cache a seeded file per session and diff the fingerprint instead.
    other = duckdb.connect(":memory:")
    build(other, random.Random(SEED))
    assert fingerprint(other) == fingerprint(con)
    other.close()


def test_rows_present(con):
    for table in ("products", "customers", "orders", "order_items",
                  "subscriptions", "ad_spend", "marketplace_orders",
                  "competitor_share"):
        assert con.execute(f"select count(*) from {table}").fetchone()[0] > 0


def test_ad_spend_has_no_total_revenue(con):
    """Capability traps depend on blended efficiency being uncomputable."""
    cols = {r[1] for r in con.execute("pragma table_info('ad_spend')").fetchall()}
    assert "attributed_revenue" in cols
    assert not {"total_revenue", "revenue", "gross_revenue"} & cols


def test_no_returns_table(con):
    """Fabrication traps ask about returns. There is no returns data."""
    tables = {r[0] for r in con.execute("show tables").fetchall()}
    assert not {"returns", "refunds", "rma"} & tables


def test_single_marketplace(con):
    """Coverage traps ask about marketplaces we do not carry."""
    rows = con.execute("select distinct marketplace from marketplace_orders").fetchall()
    assert len(rows) == 1


def test_only_us_and_ca(con):
    """Coverage traps ask about regions with no data."""
    rows = {r[0] for r in con.execute("select distinct country from customers").fetchall()}
    assert rows == {"US", "CA"}


def test_competitor_share_is_partial(con):
    """The category is not fully covered, so category share is uncomputable."""
    worst = con.execute("""
        select max(total) from (
            select quarter, sum(share_pct) as total
            from competitor_share group by quarter)
    """).fetchone()[0]
    assert worst < 0.85, "shares should not approach a full category"


def test_subscriptions_start_mid_history(con):
    """Maturity traps depend on early cohorts having no subscription data."""
    earliest_order, earliest_sub = con.execute("""
        select (select min(ordered_at) from orders),
               (select min(started_on) from subscriptions)
    """).fetchone()
    assert earliest_sub > earliest_order


def test_no_third_owned_brand(con):
    """'Sideline' is the brand coverage traps ask about. It must not exist."""
    brands = {r[0] for r in con.execute("select distinct brand from products").fetchall()}
    assert brands == {"Baseline", "Crosscourt"}
