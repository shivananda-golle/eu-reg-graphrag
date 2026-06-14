"""
Module 5, task 5.1 — query router.

A small LLM classification call picks the retrieval strategy per question:
  - vector : semantic lookup / definitions / "what does X say"
  - graph  : cross-references / traversal / penalties / linked obligations
  - hybrid : broad or multi-part questions needing both

The router only chooses a strategy; the actual retrieval stays deterministic
(Qdrant / Cypher). Defaults to hybrid if the model returns anything unexpected.

Run:  uv run python -m src.agent.router
"""

import time

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
STRATEGIES = {"vector", "graph", "hybrid"}

ROUTER_SYSTEM = (
    "You route questions about the EU AI Act to ONE retrieval strategy. "
    "Reply with exactly one word — vector, graph, or hybrid — and nothing else.\n"
    "- vector: a definition or simple semantic lookup (e.g. 'what is a provider?', "
    "'what does Article 5 say?').\n"
    "- graph: cross-references or traversal between provisions (e.g. 'what does "
    "Article 6 refer to?', 'what are the penalties for breaching Article 5?', "
    "'which annex lists high-risk systems?').\n"
    "- hybrid: broad or multi-part questions needing both semantic search and "
    "reference traversal (e.g. 'what obligations and penalties apply to high-risk "
    "AI providers?')."
)


def route_with_meta(query: str) -> tuple[str, dict, float]:
    """Route and also return token usage + latency (for the trace UI)."""
    client = Groq()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=4,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": query},
        ],
    )
    latency = time.time() - t0
    word = resp.choices[0].message.content.strip().lower()
    strategy = word if word in STRATEGIES else "hybrid"
    u = resp.usage
    usage = {"prompt": u.prompt_tokens, "completion": u.completion_tokens, "total": u.total_tokens}
    return strategy, usage, latency


def route(query: str) -> str:
    return route_with_meta(query)[0]


if __name__ == "__main__":
    samples = [
        "What is a 'provider' under the AI Act?",
        "What does Article 6 refer to?",
        "What are the penalties for using a prohibited AI practice?",
        "Which annex lists the high-risk AI systems?",
        "What obligations and penalties apply to providers of high-risk AI systems?",
        "What makes an AI system high-risk?",
    ]
    for q in samples:
        print(f"  {route(q):<7} <- {q}")
