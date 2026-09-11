"""What the agent is told about the warehouse, and how much of it.

The eval this repo is built around has a circularity problem: the same author
writes the `refuses` blocks *and* the trap cases that check whether the agent
refuses. Graded only on the full layer, the benchmark risks measuring whether
the agent can paraphrase a sentence it was handed.

The answer is not to argue that it is fine. It is to measure it. Three arms:

    RAW_SCHEMA   table and column names only
    NO_REFUSALS  field meanings and routing, refusal policy stripped
    FULL         everything

`RAW_SCHEMA` vs `FULL` measures the whole semantic layer. **`NO_REFUSALS` vs
`FULL` isolates the refusal policy**, which is the thing actually being argued
about -- dropping the entire layer also removes field meanings and routing, so
a two-arm comparison cannot tell which part did the work.

Circularity is not eliminated by this. It is quantified, which is a claim that
survives someone pushing back on it.
"""

from __future__ import annotations

from enum import Enum

import duckdb

from refusal_bench.semantic import Topic


class Arm(str, Enum):
    RAW_SCHEMA = "raw_schema"
    NO_REFUSALS = "no_refusals"
    FULL = "full"


def schema_text(con: duckdb.DuckDBPyConnection) -> str:
    """Table and column names. What an agent could discover for itself."""
    lines = []
    for (table,) in con.execute("show tables").fetchall():
        cols = con.execute(f"pragma table_info('{table}')").fetchall()
        lines.append(f"{table}({', '.join(c[1] for c in cols)})")
    return "\n".join(lines)


def _topic_text(topic: Topic, include_refusals: bool) -> str:
    lines = [f"## {topic.topic}", topic.description.strip(), ""]
    lines.append(f"grain: {', '.join(topic.grain)}")
    lines.append(f"tables: {', '.join(topic.tables)}")
    lines.append("fields:")
    for name, meta in topic.fields.items():
        lines.append(f"  {name}: {meta['means'].strip()}")
        if meta.get("caveat"):
            lines.append(f"    caveat: {meta['caveat'].strip()}")
    lines.append("answers questions about:")
    lines += [f"  - {q}" for q in topic.routes_here]

    if include_refusals and topic.refuses:
        lines.append("cannot answer:")
        for r in topic.refuses:
            lines.append(f"  - {r.ask}")
            lines.append(f"    because: {r.because.strip()}")
            lines.append(f"    ask instead: {r.instead.strip()}")
    return "\n".join(lines)


def build_context(
    con: duckdb.DuckDBPyConnection, topics: list[Topic], arm: Arm = Arm.FULL
) -> str:
    """Assemble the context block for one arm."""
    schema = f"# Warehouse schema\n{schema_text(con)}"
    if arm is Arm.RAW_SCHEMA:
        return schema

    include_refusals = arm is Arm.FULL
    bodies = [_topic_text(t, include_refusals) for t in topics]
    return schema + "\n\n# Topics\n" + "\n\n".join(bodies)


# --- trap vocabulary ---

_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "at", "by",
    "is", "are", "was", "were", "be", "our", "we", "us", "this", "that",
    "what", "which", "how", "why", "any", "all", "from", "with", "across",
}


def _content_words(text: str) -> set[str]:
    return {
        w.strip(".,?:;()").lower()
        for w in text.split()
        if w.strip(".,?:;()").lower() not in _STOPWORDS and len(w) > 2
    }


def vocabulary_overlap(question: str, refusal_ask: str) -> float:
    """How much a trap question reuses the wording of the refusal it targets.

    A trap written from the answer key tends to echo its phrasing, and an agent
    that matches on that phrasing scores well without having reasoned about
    anything. Real stakeholders do not ask "what is the blended return on ad
    spend across all company revenue" -- they ask "is our advertising working".

    Jaccard over content words. Crude, and enough to catch a trap that was
    written by rephrasing the `refuses.ask` rather than by imagining someone
    asking the question.
    """
    a, b = _content_words(question), _content_words(refusal_ask)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


#: Above this, a trap reads as a restatement of its own answer key.
MAX_TRAP_OVERLAP = 0.5
