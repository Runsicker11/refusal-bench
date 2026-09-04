"""Seed the Baseline Athletic synthetic warehouse.

Baseline Athletic is a fictional racquet-sports brand selling direct and through
one marketplace. The warehouse is deliberately incomplete: several questions a
stakeholder would reasonably ask cannot be answered from it. Those gaps are the
point. Each one is exercised by a trap category in evals/.

Deliberate holes, and the trap category each one serves:

  ad_spend has attributed revenue only, never total revenue   -> capability
  marketplace_orders covers one marketplace, not all channels -> coverage
  competitor_share covers two rivals, not the category        -> capability
  customers are US and CA only                                -> coverage
  subscriptions begin mid-history (2025-09-01)                -> maturity
  there is no returns table at all                            -> fabrication

Do not fill these in. Filling one silently invalidates every case that depends
on it. tests/test_seed.py asserts they are still open.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb

SEED = 20260904
DB_PATH = Path(__file__).resolve().parents[1] / "baseline.duckdb"

START = date(2025, 1, 1)
END = date(2026, 6, 30)
SUBS_START = date(2025, 9, 1)

OWNED_BRANDS = ("Baseline", "Crosscourt")
COUNTRIES = ("US", "CA")
MARKETPLACE = "Vantage Market"

N_CUSTOMERS = 4000
N_MARKETPLACE_ORDERS = 6000

# sku, name, brand, category, price, cost
PRODUCTS = [
    ("BL-PAD-100", "Baseline Control Paddle", "Baseline", "Paddles", 129.00, 41.00),
    ("BL-PAD-200", "Baseline Power Paddle", "Baseline", "Paddles", 149.00, 47.00),
    ("CC-PAD-100", "Crosscourt Elite Paddle", "Crosscourt", "Paddles", 179.00, 58.00),
    ("BL-GRP-010", "Baseline Tacky Overgrip 3pk", "Baseline", "Grips", 12.00, 2.60),
    ("BL-GRP-020", "Baseline Cushion Overgrip 3pk", "Baseline", "Grips", 14.00, 3.10),
    ("CC-GRP-010", "Crosscourt Pro Overgrip 3pk", "Crosscourt", "Grips", 15.00, 3.40),
    ("BL-TAP-010", "Baseline Lead Tape Roll", "Baseline", "Weighting", 18.00, 4.20),
    ("BL-TAP-020", "Baseline Edge Guard Tape", "Baseline", "Weighting", 16.00, 3.80),
    ("CC-BAG-100", "Crosscourt Tour Backpack", "Crosscourt", "Bags", 89.00, 29.00),
    ("BL-BAG-050", "Baseline Sling Bag", "Baseline", "Bags", 49.00, 16.00),
    ("BL-BAL-012", "Baseline Outdoor Balls 12pk", "Baseline", "Balls", 32.00, 9.50),
    ("BL-BAL-006", "Baseline Indoor Balls 6pk", "Baseline", "Balls", 19.00, 5.60),
    ("CC-APP-100", "Crosscourt Performance Tee", "Crosscourt", "Apparel", 38.00, 11.00),
    ("BL-APP-200", "Baseline Court Shorts", "Baseline", "Apparel", 44.00, 13.50),
]

CAMPAIGNS = [
    ("search-brand", "Search"),
    ("search-nonbrand", "Search"),
    ("social-prospecting", "Social"),
    ("social-retargeting", "Social"),
]

# Us plus two rivals. The category has more players than this; the shares do not
# sum to 100 and cannot be made to.
SHARE_BRANDS = ("Baseline Athletic", "Rally Sports", "Northcourt")


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _season(d: date) -> float:
    """Spring and summer run hotter for racquet sports."""
    return {1: 0.7, 2: 0.75, 3: 1.0, 4: 1.25, 5: 1.35, 6: 1.3,
            7: 1.2, 8: 1.1, 9: 1.0, 10: 0.9, 11: 1.15, 12: 0.95}[d.month]


def _weighted_date(rng: random.Random) -> date:
    """A date in range, biased toward busier months."""
    while True:
        d = START + timedelta(days=rng.randint(0, (END - START).days))
        if rng.random() < _season(d) / 1.35:
            return d


def build(con: duckdb.DuckDBPyConnection, rng: random.Random) -> None:
    con.execute("""
        create table products (
            product_id integer primary key, sku varchar, name varchar,
            brand varchar, category varchar, unit_price double, unit_cost double)
    """)
    for i, (sku, name, brand, cat, price, cost) in enumerate(PRODUCTS, start=1):
        con.execute("insert into products values (?,?,?,?,?,?,?)",
                    [i, sku, name, brand, cat, price, cost])

    con.execute("""
        create table customers (
            customer_id integer primary key, first_seen_on date,
            country varchar, acquisition_channel varchar)
    """)
    con.execute("""
        create table orders (
            order_id integer primary key, customer_id integer, ordered_at date,
            country varchar, subtotal double, discount double, shipping double,
            total double)
    """)
    con.execute("""
        create table order_items (
            order_item_id integer primary key, order_id integer,
            product_id integer, quantity integer, unit_price double,
            line_total double)
    """)

    channels = ["organic", "paid_search", "paid_social", "email", "referral"]
    channel_w = [34, 26, 20, 14, 6]

    order_id = 0
    item_id = 0
    customer_rows, order_rows, item_rows = [], [], []
    first_order_by_customer: dict[int, date] = {}

    for cid in range(1, N_CUSTOMERS + 1):
        first = _weighted_date(rng)
        country = "US" if rng.random() < 0.87 else "CA"
        channel = rng.choices(channels, weights=channel_w)[0]
        customer_rows.append((cid, first, country, channel))

        n_orders = rng.choices([1, 2, 3, 4, 5, 6],
                               weights=[55, 22, 11, 6, 4, 2])[0]
        d = first
        for _ in range(n_orders):
            if d > END:
                break
            order_id += 1
            first_order_by_customer.setdefault(cid, d)

            n_lines = rng.choices([1, 2, 3], weights=[58, 30, 12])[0]
            picks = rng.sample(range(1, len(PRODUCTS) + 1), n_lines)
            subtotal = 0.0
            for pid in picks:
                qty = rng.choices([1, 2, 3], weights=[80, 15, 5])[0]
                price = PRODUCTS[pid - 1][4]
                line = round(price * qty, 2)
                subtotal += line
                item_id += 1
                item_rows.append((item_id, order_id, pid, qty, price, line))

            subtotal = round(subtotal, 2)
            discount = round(subtotal * 0.20, 2) if rng.random() < 0.22 else 0.0
            shipping = 0.0 if subtotal - discount >= 60 else 6.95
            total = round(subtotal - discount + shipping, 2)
            order_rows.append((order_id, cid, d, country, subtotal, discount,
                               shipping, total))

            d = d + timedelta(days=rng.randint(18, 160))

    con.executemany("insert into customers values (?,?,?,?)", customer_rows)
    con.executemany("insert into orders values (?,?,?,?,?,?,?,?)", order_rows)
    con.executemany("insert into order_items values (?,?,?,?,?,?)", item_rows)

    # Subscriptions start mid-history. Cohorts before SUBS_START have none, and
    # cohorts near END have no tenure yet.
    con.execute("""
        create table subscriptions (
            subscription_id integer primary key, customer_id integer,
            product_id integer, started_on date, cancelled_on date,
            plan_interval varchar, monthly_amount double)
    """)
    consumable = [i for i, p in enumerate(PRODUCTS, start=1)
                  if p[3] in ("Grips", "Balls")]
    eligible = sorted(c for c, d in first_order_by_customer.items()
                      if d >= SUBS_START)
    sub_rows = []
    for sid, cid in enumerate(rng.sample(eligible, min(1200, len(eligible))),
                              start=1):
        started = first_order_by_customer[cid] + timedelta(days=rng.randint(0, 45))
        if started > END:
            continue
        pid = rng.choice(consumable)
        interval = rng.choices(["monthly", "quarterly"], weights=[70, 30])[0]
        amount = round(PRODUCTS[pid - 1][4] * (1 if interval == "monthly" else 0.34), 2)
        cancelled = None
        if rng.random() < 0.31:
            c = started + timedelta(days=rng.randint(25, 300))
            cancelled = c if c <= END else None
        sub_rows.append((sid, cid, pid, started, cancelled, interval, amount))
    con.executemany("insert into subscriptions values (?,?,?,?,?,?,?)", sub_rows)

    # Ad spend. Attributed revenue only -- there is no total-revenue column here
    # and no key that would let you build one at this grain.
    con.execute("""
        create table ad_spend (
            spend_date date, campaign varchar, platform varchar, spend double,
            impressions integer, clicks integer, attributed_orders integer,
            attributed_revenue double)
    """)
    ad_rows = []
    for d in _daterange(START, END):
        s = _season(d)
        for campaign, platform in CAMPAIGNS:
            base = {"search-brand": 90, "search-nonbrand": 240,
                    "social-prospecting": 310, "social-retargeting": 120}[campaign]
            spend = round(base * s * rng.uniform(0.7, 1.3), 2)
            cpc = rng.uniform(0.55, 1.9)
            clicks = max(1, int(spend / cpc))
            impressions = int(clicks * rng.uniform(18, 55))
            cvr = {"search-brand": 0.085, "search-nonbrand": 0.019,
                   "social-prospecting": 0.011, "social-retargeting": 0.038}[campaign]
            orders_ = int(clicks * cvr * rng.uniform(0.7, 1.35))
            revenue = round(orders_ * rng.uniform(48, 94), 2)
            ad_rows.append((d, campaign, platform, spend, impressions, clicks,
                            orders_, revenue))
    con.executemany("insert into ad_spend values (?,?,?,?,?,?,?,?)", ad_rows)

    # One marketplace. There is no table listing the others.
    con.execute("""
        create table marketplace_orders (
            mp_order_id integer primary key, marketplace varchar,
            ordered_at date, sku varchar, quantity integer, item_price double,
            fees double)
    """)
    mp_rows = []
    for i in range(1, N_MARKETPLACE_ORDERS + 1):
        d = _weighted_date(rng)
        sku, _, _, _, price, _ = PRODUCTS[rng.randrange(len(PRODUCTS))]
        qty = rng.choices([1, 2], weights=[88, 12])[0]
        item_price = round(price * rng.uniform(0.95, 1.05), 2)
        fees = round(item_price * qty * rng.uniform(0.14, 0.19), 2)
        mp_rows.append((i, MARKETPLACE, d, sku, qty, item_price, fees))
    con.executemany("insert into marketplace_orders values (?,?,?,?,?,?,?)", mp_rows)

    # Quarterly, three brands. The category has more players; these shares do not
    # sum to 100 and there is no row for "everyone else".
    con.execute("""
        create table competitor_share (
            quarter varchar, brand varchar, share_pct double)
    """)
    share_rows = []
    for year, q in [(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2)]:
        for j, brand in enumerate(SHARE_BRANDS):
            base = [0.181, 0.264, 0.171][j]
            share_rows.append((f"{year}Q{q}", brand,
                               round(base + rng.uniform(-0.012, 0.014), 4)))
    con.executemany("insert into competitor_share values (?,?,?)", share_rows)


def fingerprint(con: duckdb.DuckDBPyConnection) -> str:
    """Stable digest of the seeded data, so drift is loud."""
    parts = []
    for table, col in [("products", "unit_price"), ("customers", "customer_id"),
                       ("orders", "total"), ("order_items", "line_total"),
                       ("subscriptions", "monthly_amount"), ("ad_spend", "spend"),
                       ("marketplace_orders", "item_price"),
                       ("competitor_share", "share_pct")]:
        n, s = con.execute(
            f"select count(*), coalesce(round(sum({col}), 2), 0) from {table}"
        ).fetchone()
        parts.append(f"{table}:{n}:{s}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def seed(path: Path = DB_PATH) -> str:
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    try:
        build(con, random.Random(SEED))
        fp = fingerprint(con)
        for t in ("products", "customers", "orders", "order_items",
                  "subscriptions", "ad_spend", "marketplace_orders",
                  "competitor_share"):
            n = con.execute(f"select count(*) from {t}").fetchone()[0]
            print(f"  {t:<20} {n:>7,}")
        print(f"\n  fingerprint {fp}")
        return fp
    finally:
        con.close()


if __name__ == "__main__":
    print(f"seeding {DB_PATH.name}\n")
    seed()
