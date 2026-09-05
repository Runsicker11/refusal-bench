"""Tools the agent can call.

`run_sql` is the only one for now. Three properties matter more than features:

**It is read-only, and that is enforced here rather than trusted.** The SQL is
written by a language model, which makes it untrusted input. A read-only DuckDB
connection is the belt; the statement guard below is the braces. Either alone
would probably hold. Both is cheap.

**A bad query is information, not a crash.** Syntax errors, missing tables and
type mismatches all come back as text the model can read and act on. An
exception ends the run; an error string lets the agent try again with a better
query, which is what a human analyst does.

**Results are capped.** A careless `select *` against a 9,927-row table would
blow the context window and quietly degrade every subsequent turn. The cap is
visible in the output so the model knows it is seeing a slice.
"""

from __future__ import annotations

import re

import duckdb

MAX_ROWS = 50
MAX_CHARS = 4000

# Only these may begin a statement. COPY, ATTACH, INSTALL, PRAGMA and every
# write verb fail this check by construction.
_ALLOWED_START = ("select", "with")

_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _reject(sql: str) -> str | None:
    """Return a refusal reason, or None if the statement may run."""
    stripped = _COMMENT.sub(" ", sql).strip()
    if not stripped:
        return "empty query"

    # A trailing semicolon is fine; a second statement is not.
    body, _, tail = stripped.partition(";")
    if tail.strip():
        return "only one statement per call"

    first = body.lstrip("( \t\n").split(None, 1)[0].lower() if body.split() else ""
    if first not in _ALLOWED_START:
        return f"only SELECT and WITH are allowed, got {first.upper() or 'nothing'!r}"
    return None


def make_run_sql(
    con: duckdb.DuckDBPyConnection,
    max_rows: int = MAX_ROWS,
    max_chars: int = MAX_CHARS,
):
    """Build a `run_sql` tool bound to a connection.

    ponytail: rows are formatted straight into the prompt. Correct at this
    warehouse size, wrong at real scale -- there the tool should summarise, or
    hand back a reference the model can page through.
    """

    def _tables() -> str:
        rows = con.execute("show tables").fetchall()
        return ", ".join(r[0] for r in rows)

    def run_sql(query: str) -> str:
        reason = _reject(query)
        if reason is not None:
            return f"rejected: {reason}"

        try:
            cur = con.execute(query)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
        except duckdb.Error as exc:
            # The table list turns a dead end into a recoverable step.
            return f"error: {exc}\navailable tables: {_tables()}"

        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        lines = [" | ".join(columns)]
        lines += [" | ".join("NULL" if v is None else str(v) for v in r) for r in rows]
        out = "\n".join(lines)

        if len(out) > max_chars:
            out = out[:max_chars] + f"\n... output truncated at {max_chars} characters"
        elif truncated:
            out += f"\n... more rows exist; showing the first {max_rows}"
        elif not rows:
            out += "\n(no rows)"

        return out

    return run_sql
