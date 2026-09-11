# Writing cases

## The traps-first rule

**A trap case must be committed before the `refuses` block for the gap it
targets.**

Not a convention — a checkable one. `tests/test_traps_first.py` reads the git
history and fails if a trap's first commit is later than the first commit of
the semantic-layer file documenting its gap.

### Why ordering, rather than a style guide

The circularity problem is that the same author writes the refusal text and the
trap that checks for refusal, so a trap can end up being a paraphrase of its own
answer key. `vocabulary_overlap()` catches the blatant version, but it is a
heuristic — a careful author can stay under the threshold and still be writing
from the answer.

If the trap text existed *before* the refusal text, the refusal cannot have
leaked into it. That is a fact about the history rather than a claim about
intent, and it is checkable by anyone who clones the repo.

To be precise about how strong this is: commit timestamps can be set by the
author, so this is a mechanically-checked convention, not a cryptographic
proof. It is still meaningfully stronger than a style rule — backdating a
commit to defeat it is a deliberate act, not an accident, and the whole point
of the rule is to stop the accident.

### What it does not fix

Ordering cuts the link from the semantic layer to the trap. It does not cut the
link from the **warehouse** to the trap — the author still knows where the gaps
are, because they built them. That link is reduced by holding gaps out
(`evals/gaps.yaml`) and would only be cut properly by a warehouse the author did
not write. See [docs/three-arms.md](../docs/three-arms.md).

### Gaps where this is no longer available

Four gaps were documented in the semantic layer before this rule existed. Traps
written for them now cannot be proven independent, and `traps_first: false` in
`evals/gaps.yaml` records that permanently.

**Report them separately from traps-first results.** Quietly averaging the two
would reintroduce exactly the problem the rule exists to remove — and deciding
how to split them *after* seeing which number looks better is how a benchmark
loses its credibility.

## Case format

```yaml
id: 07-marketplace-coverage
kind: trap                  # answerable | trap
category: coverage          # coverage | capability | ambiguity | maturity | fabrication
targets_gap: single_marketplace   # must exist in evals/gaps.yaml
question: "how are we doing on the other marketplaces this quarter?"
expect:
  behaviour: refuse         # refuse | clarify | caveat
  must_mention: [vantage]   # the concept a useful response has to name
```

Answerable cases carry a hidden result instead:

```yaml
kind: answerable
expect:
  sql_result: [[0.213]]
```

## Rules

1. **Traps-first.** Above. Enforced.
2. **Stakeholder phrasing.** `vocabulary_overlap(question, refuses.ask)` must
   stay under `MAX_TRAP_OVERLAP`. Ask the way someone would actually ask — "is
   our advertising working", not "compute blended return on ad spend".
3. **Every trap names its gap.** `targets_gap` links to `evals/gaps.yaml`, which
   is what makes the held-out/documented split mechanical at scoring time rather
   than a judgement call afterwards.
4. **A trap the agent already passes is not a trap.** Verify it currently fails
   before committing it.
5. **Answerable cases are the control group.** A harness that only rewards
   refusal trains an agent that refuses everything and scores perfectly.
