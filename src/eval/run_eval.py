"""
Module 6, task 6.2 — run the gold set through each retrieval strategy.

For every (question, strategy) we record the answer, the citations retrieved,
and an interpretable retrieval metric: context_recall = fraction of the
expected articles/annexes that retrieval actually surfaced. This is what
directly shows graph/hybrid beating vector on cross-reference questions.

Resumable: results are saved after each run, so a timeout just resumes.

Run (repeat until DONE):  uv run python -m src.eval.run_eval
"""

import json
import re
from pathlib import Path

from src.agent.agent import ask_traced

GOLD_PATH = Path("data/eval/gold.json")
RESULTS_PATH = Path("data/eval/results.json")
STRATEGIES = ["vector", "graph", "hybrid"]

_ART = re.compile(r"Article\s+(\d+)")
_ANX = re.compile(r"Annex\s+([IVXLC]+)")


def cited(citations: list[str]) -> tuple[set, set]:
    """Extract referenced article numbers + annex romans from citation strings."""
    arts, annexes = set(), set()
    for c in citations:
        arts.update(int(m.group(1)) for m in _ART.finditer(c))
        annexes.update(m.group(1) for m in _ANX.finditer(c))
    return arts, annexes


def main() -> None:
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    results = []
    if RESULTS_PATH.exists():
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    done = {(r["id"], r["strategy"]) for r in results}

    todo = [(q, s) for q in gold for s in STRATEGIES if (q["id"], s) not in done]
    print(f"{len(done)} done, {len(todo)} to run")

    for q, strategy in todo:
        res = ask_traced(q["question"], strategy)
        units = res["trace"]["retrieve"]["units"]
        citations = [u["citation"] for u in units]
        got_art, got_anx = cited(citations)

        exp_art, exp_anx = set(q["expected_articles"]), set(q["expected_annexes"])
        hits = len(exp_art & got_art) + len(exp_anx & got_anx)
        need = len(exp_art) + len(exp_anx)
        recall = hits / need if need else None

        results.append({
            "id": q["id"],
            "category": q["category"],
            "strategy": strategy,
            "question": q["question"],
            "reference_answer": q["reference_answer"],
            "answer": res["answer"],
            "retrieved_citations": citations,
            "contexts": [p["text"] for p in res.get("passages", [])],
            "expected_articles": q["expected_articles"],
            "expected_annexes": q["expected_annexes"],
            "context_recall": recall,
            "retrieve_latency": res["trace"]["retrieve"]["latency"],
            "gen_tokens": res["trace"]["generate"]["tokens"]["total"],
        })
        RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        rc = "n/a" if recall is None else f"{recall:.2f}"
        print(f"  [{q['id']:<5} {strategy:<7}] recall={rc}")

    print(f"DONE — {len(results)} runs -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
