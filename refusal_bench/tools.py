"""Tools the agent can call.

`run_sql` is the only one for now. Three properties matter more than features:

**It cannot modify the database, and that is enforced rather than trusted.**
The SQL is written by a language model, which makes it untrusted input. Two
independent guards: `connect_readonly` opens the file in DuckDB's read-only
mode, and the statement guard below rejects anything that does not begin with
SELECT or WITH.

**This is not a sandbox, and the distinction matters.** DuckDB table functions
are ordinary SELECT expressions, so `select * from read_csv('/etc/passwd')`
passes the guard and reads the file. Scoped to a synthetic warehouse this is
acceptable; pointed at anything real, the tool needs a filesystem policy on top
of these guards, not instead of them.

**Statement splitting uses DuckDB's parser, not a regex.** An earlier version
stripped comments and blanked string literals with two regexes, and
`select '/*' ; drop table products /*' */` walked straight through it: the
comment pattern does not know about quotes, so it swallowed the semicolon and
the DROP. DuckDB read the same string correctly as two statements. Two
hand-rolled regexes cannot soundly tokenise SQL against each other -- string
and comment lexing is one stateful pass -- so the only guard that agrees with
the engine is the engine.

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

# Only used to find the leading keyword, after the parser has already
# guaranteed there is exactly one statement. It cannot be used to smuggle a
# second one past that check.
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _reject(con: duckdb.DuckDBPyConnection, sql: str) -> str | None:
    """Return a refusal reason, or None if the statement may run.

    Splitting is delegated to DuckDB's parser so the guard and the engine
    cannot disagree about where one statement ends. The keyword check is then
    safe on the raw text, because the parser has already established there is
    exactly one statement to read the keyword of.
    """
    if not sql.strip():
        return "empty query"

    try:
        statements = con.extract_statements(sql)
    except duckdb.Error:
        # Unparseable SQL is a mistake the model can fix, not a policy
        # refusal. Fall through and let execution report it, which also
        # attaches the table list. Nothing DuckDB cannot parse can run.
        return None

    if len(statements) != 1:
        return f"only one statement per call, got {len(statements)}"

    # PRAGMA parses as StatementType.SELECT, so the type alone is not enough.
    if statements[0].type != duckdb.StatementType.SELECT:
        return f"only SELECT and WITH are allowed, got {statements[0].type.name}"

    body = _COMMENT.sub(" ", sql).strip().lstrip("( \t\n")
    first = body.split(None, 1)[0].lower() if body.split() else ""
    if first not in _ALLOWED_START:
        return f"only SELECT and WITH are allowed, got {first.upper() or 'nothing'!r}"
    return None


def connect_readonly(path: str) -> duckdb.DuckDBPyConnection:
    """Open the warehouse in DuckDB's read-only mode.

    The statement guard would probably hold on its own. This is the second
    guard, so that relaxing the first one later -- to allow EXPLAIN, say --
    does not silently remove the only protection.
    """
    return duckdb.connect(path, read_only=True)


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
        reason = _reject(con, query)
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
