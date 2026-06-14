"""
Module 3, task 3.5 — baseline RAG: retrieve, then generate a cited answer.

Vector search finds the chunks; Groq generates an answer grounded ONLY in those
chunks, citing each claim. This is the end-to-end vector baseline — the thing
Module 4's graph retrieval will be measured against.

Run:  uv run python -m src.retrieval.rag "your question"
"""

import sys

from dotenv import load_dotenv
from groq import Groq

from src.retrieval.search import search

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
MAX_CHARS = 2000  # cap each chunk so one huge paragraph can't dominate the prompt

SYSTEM = (
    "You are a compliance assistant for EU regulation. Answer the question using "
    "ONLY the provided context excerpts from the EU AI Act. Cite the source of "
    "each claim inline using its label, e.g. (Article 6(1)), (Annex III), "
    "(Recital 52). If the answer is not in the context, say exactly: 'Not found "
    "in the provided context.' Never invent articles, numbers, or obligations."
)


def generate_answer(query: str, passages: list[dict]) -> str:
    """Generate a grounded, cited answer from passages [{citation, text}, ...].
    Shared by the vector path (here) and the graph path (compare.py)."""
    context = "\n\n".join(
        f"[{p['citation']}] {p['text'][:MAX_CHARS]}" for p in passages
    )
    client = Groq()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{context}"},
        ],
    )
    return resp.choices[0].message.content


def answer(query: str, k: int = 5) -> tuple[str, list]:
    hits = search(query, k)
    passages = [
        {"citation": h.payload["citation"], "text": h.payload["text"]} for h in hits
    ]
    return generate_answer(query, passages), hits


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    ans, hits = answer(query)

    print(f"Q: {query}\n")
    print("ANSWER:")
    print(ans)
    print("\nRETRIEVED CONTEXT (what the answer was grounded in):")
    for rank, h in enumerate(hits, 1):
        print(f"  {rank}. [{h.score:.3f}] {h.payload['citation']}")
