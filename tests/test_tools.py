"""run_sql is read-only, recoverable, and capped.

The write-rejection tests are the load-bearing ones. The SQL reaching this tool
is written by a language model, so it is untrusted input, and "we opened the
connection read-only" is a claim that should be checked rather than assumed.
"""

import pytest

from refusal_bench.tools import make_run_sql


@pytest.fixture
def run_sql(con):
    return make_run_sql(con)


# --- it works ---

def test_returns_columns_and_rows(run_sql):
    out = run_sql("select brand, count(*) as n from products group by brand order by brand")
    assert "brand | n" in out
    assert "Baseline" in out and "Crosscourt" in out


def test_with_clause_is_allowed(run_sql):
    out = run_sql("with x as (select 1 as a) select a from x")
    assert "a" in out and "1" in out


def test_empty_result_says_so(run_sql):
    assert "(no rows)" in run_sql("select * from products where brand = 'Sideline'")


# --- it refuses to write ---

@pytest.mark.parametrize("sql", [
    "insert into products values (99,'x','x','x','x',1,1)",
    "update products set unit_price = 0",
    "delete from products",
    "drop table products",
    "create table evil (a int)",
    "attach 'other.duckdb' as other",
    "copy products to '/tmp/leak.csv'",
    "pragma database_list",
])
def test_rejects_anything_that_is_not_a_read(run_sql, sql):
    assert run_sql(sql).startswith("rejected:")


def test_rejects_a_second_statement(run_sql):
    out = run_sql("select 1; drop table products")
    assert out.startswith("rejected:")
    assert "one statement" in out


def test_trailing_semicolon_is_fine(run_sql):
    assert not run_sql("select 1 as a;").startswith("rejected:")


def test_comment_smuggling_is_rejected(run_sql):
    """A leading comment must not disguise the real first keyword."""
    assert run_sql("-- select\ndrop table products").startswith("rejected:")


def test_products_table_survived_all_of_that(con):
    assert con.execute("select count(*) from products").fetchone()[0] == 14


# --- errors are recoverable ---

def test_syntax_error_returns_text_rather_than_raising(run_sql):
    out = run_sql("select from where")
    assert out.startswith("error:")


def test_unknown_table_error_lists_the_real_tables(run_sql):
    """A dead end becomes a recoverable step."""
    out = run_sql("select * from nonexistent_table")
    assert out.startswith("error:")
    assert "available tables:" in out
    assert "products" in out


# --- results are capped ---

def test_row_cap_is_enforced_and_disclosed(con):
    out = make_run_sql(con, max_rows=5)("select order_id from orders")
    assert len([l for l in out.splitlines() if l and not l.startswith("...")]) == 6
    assert "showing the first 5" in out


def test_char_cap_is_enforced_and_disclosed(con):
    out = make_run_sql(con, max_rows=1000, max_chars=200)("select * from orders")
    assert len(out) < 400
    assert "output truncated" in out


# --- regressions from the 2026-09-06 review ---

def test_semicolon_inside_a_string_literal_is_allowed(run_sql):
    """Splitting on a raw ';' rejected valid queries filtering on text."""
    assert run_sql("select 'a;b' as x").splitlines()[1] == "a;b"


def test_escaped_quotes_do_not_confuse_the_guard(run_sql):
    assert not run_sql("select 'it''s fine' as x").startswith("rejected:")


def test_a_write_hidden_in_a_string_is_still_rejected(run_sql):
    """Blanking literals must not open a hole."""
    assert run_sql("select 'x'; drop table products").startswith("rejected:")


def test_connect_readonly_actually_blocks_writes(tmp_path):
    """The second guard the docstring promises now exists."""
    import duckdb
    from refusal_bench.tools import connect_readonly

    path = str(tmp_path / "w.duckdb")
    seed = duckdb.connect(path)
    seed.execute("create table t (a int)")
    seed.close()

    con = connect_readonly(path)
    assert con.execute("select current_setting('access_mode')").fetchone()[0] .lower() == "read_only"
    with pytest.raises(duckdb.Error):
        con.execute("insert into t values (1)")
    con.close()
