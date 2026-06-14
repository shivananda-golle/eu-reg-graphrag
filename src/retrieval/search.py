"""
Module 3, task 3.4 — vector search over the Qdrant index.

Embed a query, find the nearest chunks by cosine similarity, return them with
their citation + text. This is the retrieval half of the baseline RAG; task 3.5
feeds these hits to the LLM to generate a cited answer.

Run:  uv run python -m src.retrieval.search "your question here"
"""

import sys

from qdrant_client import QdrantClient

from src.retrieval.embed import embed_query
from src.retrieval.index import COLLECTION, QDRANT_PATH


def search(query: str, k: int = 5) -> list:
    """Return the top-k chunk hits (each has .score and .payload)."""
    client = QdrantClient(path=QDRANT_PATH)
    try:
        qv = embed_query(query)
        return client.query_points(
            COLLECTION, query=qv.tolist(), limit=k, with_payload=True
        ).points
    finally:
        client.close()


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    print(f"query: {query!r}\n")
    for rank, hit in enumerate(search(query), 1):
        p = hit.payload
        snippet = p["text"][:160].replace("\n", " ")
        print(f"{rank}. [{hit.score:.3f}] {p['citation']}  ({p['node_type']})")
        print(f"   {snippet}…\n")
