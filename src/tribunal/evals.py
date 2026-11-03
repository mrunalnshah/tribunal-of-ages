"""Offline evaluation.

Retrieval metrics need no LLM, so CI runs them on every push. The verdict check runs the
whole pipeline and uses LLM quota, so run it by hand (or nightly).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type hints only, so the metrics import without loading any models
    from tribunal.court import Tribunal
    from tribunal.search import LawIndex

RETRIEVAL_CASES = Path("data/eval/retrieval.jsonl")
VERDICT_CASES = Path("data/eval/verdicts.jsonl")


def hit_at_k(ranked: list[str], relevant: set[str], k: int = 5) -> float:
    """1.0 if any relevant law is in the top k, else 0.0."""
    return float(any(law_id in relevant for law_id in ranked[:k]))


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    """1/rank of the first relevant law (1.0 when it's first), or 0.0 if none is found."""
    for rank, law_id in enumerate(ranked, start=1):
        if law_id in relevant:
            return 1 / rank
    return 0.0


def retrieval_eval(index: LawIndex, path: Path = RETRIEVAL_CASES) -> dict:
    """Hit@5 and MRR over the cases whose laws exist; the others are listed, not scored."""
    cases = load_cases(path)
    problems = {}  # relevant IDs that can't be found: a typo, a PASTE, or a sensitive law
    for law_id in sorted({i for case in cases for i in case["relevant"]}):
        law = index.get(law_id)
        if law is None or law.sensitive:
            problems[law_id] = "missing" if law is None else "sensitive"
    missing = {law_id for law_id, why in problems.items() if why == "missing"}
    scored = [case for case in cases if not set(case["relevant"]) <= missing]
    hits = mrr = 0.0
    misses = []
    for case in scored:
        themes = case.get("themes", ["ancient"])
        ranked = [hit.law.law_id for hit in index.search(case["query"], themes, limit=10)]
        relevant = set(case["relevant"])
        hits += hit_at_k(ranked, relevant)
        mrr += reciprocal_rank(ranked, relevant)
        if not hit_at_k(ranked, relevant):
            misses.append({"query": case["query"], "top3": ranked[:3]})
    n = len(scored) or 1
    return {
        "cases": len(scored),
        "skipped": [case["query"] for case in cases if case not in scored],
        "hit@5": hits / n,
        "mrr": mrr / n,
        "misses": misses,
        "label_problems": problems,
    }


def verdict_eval(tribunal: Tribunal, path: Path = VERDICT_CASES) -> dict:
    """Checks we can automate: the right scope decision, and a tier near the dial."""
    from tribunal.models import Case

    cases = load_cases(path)
    failures = []
    for case in cases:
        themes = case.get("themes", ["ancient"])
        ruling = tribunal.judge(Case(crime=case["crime"], outrage=case["outrage"], themes=themes))
        ok = ruling.kind == case["expect"]
        if ok and ruling.kind == "verdict" and ruling.law and ruling.law.tier:
            ok = abs(ruling.law.tier - case["outrage"]) <= 2
        if not ok:
            law = ruling.law.law_id if ruling.law else None
            failures.append({"crime": case["crime"], "kind": ruling.kind, "law": law})
    return {
        "cases": len(cases),
        "pass_rate": 1 - len(failures) / len(cases),
        "failures": failures,
    }


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
