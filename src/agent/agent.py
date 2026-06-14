"""
Module 5, task 5.3 — the agentic RAG pipeline (LangGraph).

A state graph that routes each question to a retrieval strategy, retrieves, then
generates a cited answer:

    route ──> vector ─┐
          ├> graph  ──┼─> generate ──> END
          └> hybrid ──┘

The LLM only *chooses* the strategy (route) and *writes* the answer (generate).
Retrieval stays deterministic (Qdrant / Cypher).

Run:  uv run python -m src.agent.agent "your question"
"""

import os
import sys

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from neo4j import GraphDatabase
from typing_extensions import TypedDict

from src.agent.router import route
from src.retrieval.graph_search import ensure_fulltext_index, graph_retrieve
from src.retrieval.hybrid import hybrid_retrieve
from src.retrieval.rag import generate_answer
from src.retrieval.search import search

load_dotenv()

_driver = None


def get_driver():
    """Lazy Neo4j driver, reused across calls (graph/hybrid strategies)."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        ensure_fulltext_index(_driver)
    return _driver


class AgentState(TypedDict):
    query: str
    strategy: str
    passages: list
    answer: str


def route_node(state: AgentState) -> dict:
    return {"strategy": route(state["query"])}


def vector_node(state: AgentState) -> dict:
    hits = search(state["query"], 5)
    return {"passages": [
        {"citation": h.payload["citation"], "text": h.payload["text"]} for h in hits
    ]}


def graph_node(state: AgentState) -> dict:
    return {"passages": graph_retrieve(get_driver(), state["query"])}


def hybrid_node(state: AgentState) -> dict:
    return {"passages": hybrid_retrieve(get_driver(), state["query"])}


def generate_node(state: AgentState) -> dict:
    return {"answer": generate_answer(state["query"], state["passages"])}


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("route", route_node)
    g.add_node("vector", vector_node)
    g.add_node("graph", graph_node)
    g.add_node("hybrid", hybrid_node)
    g.add_node("generate", generate_node)

    g.set_entry_point("route")
    g.add_conditional_edges(
        "route", lambda s: s["strategy"],
        {"vector": "vector", "graph": "graph", "hybrid": "hybrid"},
    )
    for node in ("vector", "graph", "hybrid"):
        g.add_edge(node, "generate")
    g.add_edge("generate", END)
    return g.compile()


AGENT = build_agent()


def ask(query: str) -> dict:
    """Run the full agent; returns {query, strategy, passages, answer}."""
    return AGENT.invoke({"query": query})


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    result = ask(query)
    print(f"Q: {query}")
    print(f"strategy chosen: {result['strategy']}")
    print(f"retrieved: {', '.join(dict.fromkeys(p['citation'] for p in result['passages']))}\n")
    print("ANSWER:")
    print(result["answer"])
