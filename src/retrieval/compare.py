"""
Module 4, task 4.3 — vector RAG vs graph RAG, head to head.

Same question, same generator, two retrievers:
  - vector: semantic top-k over Qdrant (Module 3)
  - graph:  full-text entry + REFERENCES traversal over Neo4j (Module 4)

The point: graph retrieval surfaces the authoritative provisions (Article 6 +
Annex III) that semantic search misses.

Run:  uv run python -m src.retrieval.compare "your question"
"""

import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.retrieval.graph_search import ensure_fulltext_index, graph_retrieve
from src.retrieval.rag import answer as vector_answer
from src.retrieval.rag import generate_answer

load_dotenv()


def graph_answer(query: str) -> tuple[str, list[dict]]:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        ensure_fulltext_index(driver)
        units = graph_retrieve(driver, query)
    finally:
        driver.close()
    return generate_answer(query, units), units


def _cites(items, key) -> str:
    return ", ".join(dict.fromkeys(key(i) for i in items))  # dedup, keep order


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    print(f"Q: {query}\n" + "=" * 70)

    v_ans, v_hits = vector_answer(query)
    print("\n--- VECTOR RAG ---")
    print("retrieved:", _cites(v_hits, lambda h: h.payload["citation"]))
    print(v_ans)

    g_ans, g_units = graph_answer(query)
    print("\n--- GRAPH RAG ---")
    print("retrieved:", _cites(g_units, lambda u: u["citation"]))
    print(g_ans)
