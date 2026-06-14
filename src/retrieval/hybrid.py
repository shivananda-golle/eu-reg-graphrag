"""
Module 5, task 5.2 — hybrid retrieval: vector-seeded graph expansion.

Vector search finds the semantically-closest chunks (the entry), then their
graph node_ids feed the shared REFERENCES expansion (the structure). This is
the strongest mode: semantic entry + traversal, the best of Modules 3 and 4.

Run:  uv run python -m src.retrieval.hybrid "your question"
"""

import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.retrieval.graph_search import entry_nodes, expand_from_seeds, explicit_seeds
from src.retrieval.search import search

load_dotenv()


def hybrid_retrieve(
    driver, query: str, k_vec: int = 5, k_ft: int = 3, max_units: int = 12
) -> list[dict]:
    """Fuse dense (vector) + sparse (full-text) entry, then REFERENCES expansion.

    Vector-only seeding inherits vector's blind spots, so we also seed from the
    full-text index (catches title/keyword matches like Article 6 that semantics
    misses), union the seeds, then expand through the graph. Hybrid is therefore
    at least as good as either retriever alone.
    """
    vec_seeds = [h.payload["node_id"] for h in search(query, k_vec)]
    ft_seeds = [r["id"] for r in entry_nodes(driver, query, k_ft)]
    # explicit refs first (highest precision), then dense, then sparse.
    seeds = list(dict.fromkeys(explicit_seeds(query) + vec_seeds + ft_seeds))
    return expand_from_seeds(driver, seeds, max_units)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        print(f"query: {query!r}\n")
        print("hybrid context (vector entry -> graph expansion):")
        for u in hybrid_retrieve(driver, query):
            arrow = f"  <- via {u['from_seed']}" if u["via_reference"] else "  (vector seed)"
            print(f"  {u['citation']:<16} {u['text'][:80].strip()[:80]}…{arrow}")
    finally:
        driver.close()
