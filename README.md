# EU AI Act GraphRAG

An agentic GraphRAG system that answers compliance questions about the **EU AI Act**
with traceable, article-level citations. It combines a knowledge graph of the
regulation with semantic search, and an agent decides how to retrieve for each
question.

I built this to go deep on the thing generic RAG tools get wrong: **regulation is a
graph, not a bag of paragraphs.** Articles point to annexes, annexes point back to
articles, penalties live three references away from the obligation they punish. Plain
vector search retrieves text that *sounds* relevant; it can't *follow* a reference. For
a compliance assistant, that difference is the whole game.

## The problem, made concrete

Ask *"What makes an AI system high-risk?"*

- **Vector search** returns paragraphs that talk about high-risk systems (resilience
  requirements, risk management) — topically similar, but it misses **Article 6**, which
  actually defines the classification, and **Annex III**, the list it points to.
- **Graph retrieval** finds Article 6 by name and *traverses* its reference to Annex III —
  the real answer a lawyer would cite.

Same question, same model, different retrieval. That contrast is the point of the project,
and it's measured (numbers below), not just claimed.

## How it works

Two phases.

**Build (offline)** — turn the raw law into two complementary indexes:

```
EUR-Lex HTML
   │  parse (handle nbsp, point-tables, unnumbered articles…)
   ▼
ai_act.json          113 articles · 519 paragraphs · 180 recitals · 13 annexes
   ├──────────────► Knowledge graph (Neo4j)
   │                  nodes: Article / Paragraph / Annex / Recital
   │                  edges: CONTAINS (hierarchy) + REFERENCES (cross-refs)
   └──────────────► Vector index (Qdrant)
                      1022 chunks, BGE-small embeddings, each tagged with its graph node id
```

The cross-references aren't hyperlinks in the source — they're prose ("referred to in
Annex III"). A regex extractor turns them into 416 graph edges, skipping references to
*other* laws ("Article 9 of Regulation (EU) 2016/679").

**Answer (per question)** — an agent picks a strategy, retrieves, then generates:

```
question ─► route (LLM picks: vector | graph | hybrid)
              │
              ├─ vector : semantic top-k
              ├─ graph  : full-text entry + REFERENCES traversal
              └─ hybrid : dense + sparse seeds, then traversal
              ▼
        cited answer (grounded only in retrieved text, temp 0)
```

The LLM only **routes** and **writes**. All retrieval is deterministic (Qdrant / Cypher) —
so every edge and every citation is provable from the source, and there are no
hallucinated graph hops. Built with LangGraph.

## Results

A 13-question gold set across five categories (obligation lookup, cross-reference,
comparative, penalty/deadline, definition), each anchored to the correct article/annex.
Scored on whether retrieval found the right provisions (context recall) and, via an
LLM-as-judge on a *different* model, faithfulness and correctness.

| Strategy | Context recall | Faithfulness | Correctness |
|----------|:--------------:|:------------:|:-----------:|
| Vector   | 0.38 | 0.78 | 0.63 |
| Graph    | 0.51 | 0.72 | 0.65 |
| **Hybrid** | **0.82** | **0.88** | **0.83** |

On cross-reference questions, vector recall is ~0 while graph/hybrid recover the right
provisions — the GraphRAG thesis, quantified. Full methodology, plus a worked
measure-fix-remeasure example (definition recall 0.00 → 1.00 after sub-chunking long
articles), is in [`docs/evaluation.md`](docs/evaluation.md).

## Try it

You'll need a `.env` with keys for Groq, Neo4j (AuraDB), and optionally Langfuse — see
`.env.example`. Then:

```bash
uv sync

# build the data layer (embedding runs on CPU, ~15 min, resumable)
uv run python src/ingestion/parse_ai_act.py        # HTML -> ai_act.json
uv run python -m src.graph.build_graph             # -> Neo4j graph
uv run python -m src.retrieval.chunk               # -> chunks
uv run python -m src.retrieval.embed_corpus        # -> embeddings (resumable)
uv run python -m src.retrieval.index               # -> Qdrant

# ask it something
uv run python -m src.agent.agent "What makes an AI system high-risk?"

# or chat in the browser
uv run streamlit run src/app/streamlit_app.py
```

The Streamlit app is a glass-box console: pick a retrieval strategy (or let the agent
decide) and watch the full trace — routing decision, what got retrieved, the exact
context sent to the model, and the token/latency cost of each step.

## Project layout

```
src/
  ingestion/   parse the EUR-Lex HTML into clean JSON
  graph/       build the Neo4j knowledge graph (+ reference extractor)
  retrieval/   chunk, embed, Qdrant index, vector/graph/hybrid search, generation
  agent/       LangGraph router, the agent, Langfuse logging
  app/         Streamlit chat UI
  eval/        gold set, eval harness, LLM judge
docs/          structure spec, graph model, evaluation writeup
```

## Stack

Neo4j (knowledge graph) · Qdrant (vectors) · fastembed / BGE-small (CPU embeddings) ·
Groq (Llama 3.3 70B) with a Mistral fallback · LangGraph (orchestration) · Langfuse
(tracing) · Streamlit (UI) · uv (packaging). Everything runs on free tiers / CPU — no GPU.

## Status

The core is done end to end: ingestion, graph, retrieval, the agent, the chat UI,
evaluation, and observability all work and are reproducible. Still on the list: a
deployed version (FastAPI + AWS), a write-up, and extending the corpus to DORA and GDPR
(the pipeline is corpus-agnostic by design).

## Notes and honest limitations

- The corpus is the AI Act only so far.
- Graph retrieval still under-performs on bare definition lookups — it seeds from a
  full-text index, which the chunking improvements don't help; that needs better entry
  ranking.
- Comparative questions ("providers vs deployers") need multi-target retrieval, which
  isn't in yet.
- Embedding runs on CPU and is the slow step; it's checkpointed so it resumes if
  interrupted.

The regulation text is public (EUR-Lex, CELEX 32024R1689). This is a personal project for
learning and portfolio purposes, not legal advice.
