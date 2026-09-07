"""Load and validate the semantic layer.

A topic is a queryable subject area: the tables it owns, the grain it answers
at, what its fields mean, the questions it should be routed for, and the
questions it must decline.

The `refuses` block is the part that does not appear in conventional semantic
layers. Every entry requires two things beyond the question itself:

  because -- the specific missing input, not "we don't have that data"
  instead -- the nearest question this topic *can* answer

`instead` is required on purpose. A refusal without an alternative is a
stonewall, and a stonewall passes a naive refusal check while being nearly
useless to the person who asked. Making it structural means the harness can
tell the two apart without a judge.

Field names are validated against the live warehouse schema, so the semantic
layer cannot silently drift away from the tables it describes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

SEMANTIC_DIR = Path(__file__).resolve().parents[1] / "semantic"

REQUIRED_KEYS = {"topic", "description", "grain", "tables", "fields", "routes_here"}
REFUSAL_KEYS = {"ask", "because", "instead"}


@dataclass
class Refusal:
    ask: str
    because: str
    instead: str


@dataclass
class Topic:
    topic: str
    description: str
    grain: list[str]
    tables: list[str]
    fields: dict[str, dict]
    routes_here: list[str]
    refuses: list[Refusal] = field(default_factory=list)
    source: Path | None = None


def load_topics(directory: Path = SEMANTIC_DIR) -> list[Topic]:
    topics = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        refuses = [Refusal(**r) for r in raw.pop("refuses", [])]
        topics.append(Topic(**raw, refuses=refuses, source=path))
    return topics


def warehouse_schema(con: duckdb.DuckDBPyConnection) -> dict[str, set[str]]:
    schema = {}
    for (table,) in con.execute("show tables").fetchall():
        cols = con.execute(f"pragma table_info('{table}')").fetchall()
        schema[table] = {c[1] for c in cols}
    return schema


def validate(topics: list[Topic], schema: dict[str, set[str]]) -> list[str]:
    """Return a list of problems. Empty list means the layer is coherent."""
    errors: list[str] = []
    seen: set[str] = set()

    for t in topics:
        where = t.source.name if t.source else t.topic

        if t.topic in seen:
            errors.append(f"{where}: duplicate topic name '{t.topic}'")
        seen.add(t.topic)

        known: set[str] = set()
        for table in t.tables:
            if table not in schema:
                errors.append(f"{where}: unknown table '{table}'")
            else:
                known |= schema[table]

        for name, meta in t.fields.items():
            if known and name not in known:
                errors.append(f"{where}: field '{name}' is not in {t.tables}")
            if not isinstance(meta, dict) or not meta.get("means"):
                errors.append(f"{where}: field '{name}' has no 'means'")

        for col in t.grain:
            if known and col not in known:
                errors.append(f"{where}: grain column '{col}' is not in {t.tables}")

        if not t.routes_here:
            errors.append(f"{where}: routes_here is empty")

        for r in t.refuses:
            if not r.because.strip():
                errors.append(f"{where}: refusal '{r.ask}' has no reason")
            if not r.instead.strip():
                errors.append(
                    f"{where}: refusal '{r.ask}' has no 'instead' — a refusal "
                    f"with no alternative is a stonewall"
                )
            elif len(r.instead.split()) < 8:
                # Presence of the key is not the same as usefulness of its
                # content. "see the dashboard" satisfies a non-empty check and
                # is still a stonewall to the person who asked.
                errors.append(
                    f"{where}: the alternative for '{r.ask}' is too thin to "
                    f"act on — name a question this topic can actually answer"
                )

    return errors


def load_and_validate(
    con: duckdb.DuckDBPyConnection, directory: Path = SEMANTIC_DIR
) -> list[Topic]:
    topics = load_topics(directory)
    errors = validate(topics, warehouse_schema(con))
    if errors:
        raise ValueError("semantic layer is invalid:\n  " + "\n  ".join(errors))
    return topics
