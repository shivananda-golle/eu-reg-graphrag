# Evaluation

How the three retrieval strategies compare on a curated gold set. The goal is to
*quantify* the GraphRAG-vs-vector contrast, not just assert it.

## Setup

- **Gold set:** `data/eval/gold.json` — 13 hand-written questions across 5 categories
  (obligation lookup, cross-reference, comparative, penalty/deadline, definition).
  Each has a reference answer and the **expected articles/annexes** (verified against
  the corpus).
- **Harness:** `src/eval/run_eval.py` runs every question through all three strategies
  (vector / graph / hybrid) via the same agent, forcing each strategy.
- **Metrics:**
  - **context_recall** — fraction of the expected provisions that retrieval actually
    surfaced. Interpretable and deterministic (no LLM): directly measures *did we fetch
    the right law?*
  - **faithfulness** — is every claim in the answer supported by the retrieved context?
    (LLM judge, 0–1.)
  - **correctness** — does the answer match the reference answer? (LLM judge, 0–1.)
- **Judge:** `src/eval/judge.py` uses `llama-3.1-8b-instant` — deliberately a *different*
  model than the `llama-3.3-70b` generator, to avoid self-preference bias.

> **Why a custom judge instead of RAGAS?** RAGAS computes the same ideas (faithfulness,
> answer correctness, context recall), but its current release hard-imports a
> `langchain_community` path removed in the langchain **v1** stack that `langgraph`
> (this project's agent) depends on. Satisfying RAGAS would mean downgrading langchain
> and breaking the agent — so we implemented the metrics directly. Same substance,
> no dependency conflict, and full control over the rubric.

## Results (mean over 13 questions)

| Strategy | Context recall | Faithfulness | Correctness |
|----------|:--------------:|:------------:|:-----------:|
| Vector   | 0.12 | 0.78 | 0.63 |
| Graph    | 0.51 | 0.72 | 0.65 |
| **Hybrid** | **0.67** | **0.88** | **0.83** |

### Correctness by category

| Category | Vector | Graph | Hybrid |
|----------|:------:|:-----:|:------:|
| obligation_lookup | 0.70 | 0.88 | 0.90 |
| cross_reference   | 0.67 | 0.87 | 0.93 |
| comparative       | 0.75 | 0.80 | 0.65 |
| penalty_deadline  | 0.50 | 0.40 | 0.90 |
| definition        | 0.60 | 0.00 | 0.40 |

## What this shows

1. **Hybrid is the best overall strategy** — it wins on all three axes. Fusing dense
   (vector) and sparse (full-text) entry, then graph traversal, gives both the right
   provisions *and* enough context for a faithful, correct answer. This justifies the
   agent defaulting to hybrid for broad questions.
2. **Graph fixes retrieval where vector is blind.** Context recall jumps 0.12 → 0.51,
   and on **cross-reference** questions vector recall is **0.00** while graph/hybrid are
   ~0.89 — the core GraphRAG thesis, measured.
3. **Vector is "faithful but wrong."** Its faithfulness is fine (0.78) — it grounds in
   what it retrieves — but it retrieves the wrong provisions, so correctness lags. The
   bottleneck is retrieval, not generation.
4. **Graph alone isn't always enough for answer quality.** It nails retrieval but its
   faithfulness dips (0.72): traversal pulls in many linked paragraphs, and the model
   occasionally synthesizes across them. Hybrid's fused, focused context scores best.

## Known failure modes (and their fixes)

- **definition (graph 0.00):** "What is a 'provider'?" lives in Article 3, whose 68
  definitions are one ~17k-char chunk that BGE truncates at 512 tokens — and full-text
  on "provider" matches everything. **Fix:** sub-chunk long list-articles by point.
- **comparative (hybrid 0.65):** two-sided questions ("providers vs deployers") need
  *both* target articles; single-query retrieval finds one. **Fix:** multi-query /
  query decomposition. (Also a small sample — 2 questions.)
- **penalty_deadline graph (0.40):** date-phrased questions ("key application dates")
  don't lexically match Article 113's wording; vector/hybrid semantics help.

## Reproduce

```bash
uv run python -m src.eval.run_eval   # answers + context_recall (resumable)
uv run python -m src.eval.judge      # faithfulness + correctness (resumable)
```
