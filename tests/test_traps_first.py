"""A trap must predate the refusal text it targets.

The circularity problem is that one author writes both the refusal and the trap
checking for it, so a trap can end up paraphrasing its own answer key.
`vocabulary_overlap` catches the blatant version and is a heuristic; a careful
author stays under the threshold and still writes from the answer.

Ordering is not a heuristic. If the trap existed before the refusal text, the
refusal could not have leaked into it, and git proves that rather than the
author asserting it.

No cases exist yet, so most of this is currently vacuous. That is the point:
the rule has to be in place *before* the first case is written, because it
cannot be applied retroactively -- which is exactly what happened to the four
gaps already marked `traps_first: false`.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
GAPS = yaml.safe_load((ROOT / "evals" / "gaps.yaml").read_text())["gaps"]
BY_ID = {g["id"]: g for g in GAPS}
CASES = sorted((ROOT / "evals" / "cases").glob("*.yaml"))


def _first_commit_time(path: Path) -> int | None:
    """When this file was first added. None if it is not committed yet."""
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ct", "--", str(path)],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    return int(out[-1]) if out else None


def test_every_gap_records_whether_traps_first_is_available():
    for gap in GAPS:
        assert "traps_first" in gap, f"{gap['id']} has not declared traps_first"
    assert sum(g["traps_first"] for g in GAPS) == 2


def test_held_out_gaps_are_the_ones_still_eligible():
    """Holding a gap out is what keeps traps-first available for it."""
    for gap in GAPS:
        assert gap["traps_first"] == (gap["status"] == "held_out")


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_trap_predates_the_refusal_it_targets(case_path):
    case = yaml.safe_load(case_path.read_text())
    if case.get("kind") != "trap":
        pytest.skip("not a trap")

    gap = BY_ID.get(case["targets_gap"])
    assert gap, f"{case['targets_gap']} is not in evals/gaps.yaml"

    if not gap["traps_first"]:
        pytest.skip(
            f"{gap['id']} was documented before the rule existed; this trap is "
            "reported separately rather than checked"
        )

    trap_time = _first_commit_time(case_path)
    if trap_time is None:
        pytest.skip("case not committed yet")

    topic_file = ROOT / "semantic" / f"{gap.get('documented_in', '')}.yaml"
    if not topic_file.exists():
        return  # held out and still undocumented, which is the intended state

    layer_time = _first_commit_time(topic_file)
    assert layer_time is None or trap_time <= layer_time, (
        f"{case_path.name} was committed after {topic_file.name}, so it cannot "
        f"be shown independent of the refusal text it targets. Either the gap's "
        f"traps_first flag is wrong, or this trap needs rewriting from the "
        f"warehouse rather than from the semantic layer."
    )


def test_the_ordering_check_actually_catches_a_violation(tmp_path):
    """Proof the rule is enforceable, not just declared.

    The parametrised checks above are vacuous until cases exist, and a test
    that cannot fail is worse than no test -- it is false confidence. This one
    builds a throwaway repo where a trap is committed after the layer, and
    asserts the comparison notices.
    """
    import os

    def run(*a, when=None):
        env = dict(os.environ)
        if when:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when
        subprocess.run(a, cwd=tmp_path, capture_output=True, text=True,
                       check=True, env=env)
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")

    (tmp_path / "trap.yaml").write_text("id: t")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "trap", when="2020-01-01T00:00:00")

    (tmp_path / "layer.yaml").write_text("topic: t")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "layer", when="2021-01-01T00:00:00")

    def first(name):
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ct", "--", name],
            cwd=tmp_path, capture_output=True, text=True,
        ).stdout.split()
        return int(out[-1])

    good_trap, layer = first("trap.yaml"), first("layer.yaml")
    assert good_trap <= layer, "a trap committed first must pass"

    # Now the violation: a trap added after the layer.
    (tmp_path / "late.yaml").write_text("id: late")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "late trap", when="2022-01-01T00:00:00")
    assert first("late.yaml") > layer, "a trap committed after the layer must fail"


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_every_trap_names_a_known_gap(case_path):
    case = yaml.safe_load(case_path.read_text())
    if case.get("kind") == "trap":
        assert case.get("targets_gap") in BY_ID
