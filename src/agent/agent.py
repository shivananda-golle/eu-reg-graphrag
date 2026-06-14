"""
Module 5 / UI — the agentic RAG pipeline (LangGraph), instrumented for tracing.

    route ──> vector ─┐
          ├> graph  ──┼─> generate ──> END
          └> hybrid ──┘

Each node records timing / tokens / intermediate data into a `trace` field
(merged via a reducer), so the Streamlit UI can show exactly what happened at
every stage. `forced_strategy` lets the UI override the router (manual mode).

Run:  uv run python -m src.agent.agent "your question"
"""

import os
import sys
import time
from typing import Annotated

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from neo4j import GraphDatabase
from typing_extensions import TypedDict

from src.agent.router import route_with_meta
from src.retrieval.graph_search import ensure_fulltext_index, graph_retrieve
from src.retrieval.hybrid import hybrid_retrieve
from src.retrieval.rag import generate_with_meta
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


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class AgentState(TypedDict, total=False):
    query: str
    forced_strategy: str | None
    strategy: str
    passages: list
    answer: str
    trace: Annotated[dict, _merge]


def _retrieval_detail(strategy: str, units: list, latency: float) -> dict:
    return {
        "strategy": strategy,
        "latency": latency,
        "n": len(units),
        "context_chars": sum(len(u["text"]) for u in units),
        "units": [
            {
                "citation": u["citation"],
                "score": u.get("score"),
                "via_reference": u.get("via_reference", False),
                "from_seed": u.get("from_seed"),
                "snippet": u["text"][:200].replace("\n", " "),
            }
            for u in units
        ],
    }


def route_node(state: AgentState) -> dict:
    forced = state.get("forced_strategy")
    if forced:
        return {"strategy": forced, "trace": {"route": {"strategy": forced, "manual": True}}}
    strategy, usage, latency = route_with_meta(state["query"])
    return {
        "strategy": strategy,
        "trace": {"route": {"strategy": strategy, "manual": False, "tokens": usage, "latency": latency}},
    }


def vector_node(state: AgentState) -> dict:
    t0 = time.time()
    hits = search(state["query"], 5)
    units = [
        {"citation": h.payload["citation"], "text": h.payload["text"], "score": round(h.score, 3)}
        for h in hits
    ]
    return {"passages": units, "trace": {"retrieve": _retrieval_detail("vector", units, time.time() - t0)}}


def graph_node(state: AgentState) -> dict:
    t0 = time.time()
    units = graph_retrieve(get_driver(), state["query"])
    return {"passages": units, "trace": {"retrieve": _retrieval_detail("graph", units, time.time() - t0)}}


def hybrid_node(state: AgentState) -> dict:
    t0 = time.time()
    units = hybrid_retrieve(get_driver(), state["query"])
    return {"passages": units, "trace": {"retrieve": _retrieval_detail("hybrid", units, time.time() - t0)}}


def generate_node(state: AgentState) -> dict:
    answer, usage, latency, context = generate_with_meta(state["query"], state["passages"])
    return {
        "answer": answer,
        "trace": {"generate": {"tokens": usage, "latency": latency,
                               "context_chars": len(context), "context": context}},
    }


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


def ask_traced(query: str, strategy: str | None = None) -> dict:
    """Run the agent and return full state incl. trace. strategy=None -> agent routes."""
    t0 = time.time()
    state = AGENT.invoke({"query": query, "forced_strategy": strategy, "trace": {}})
    state["trace"]["total_latency"] = time.time() - t0
    return state


def ask(query: str) -> dict:
    return ask_traced(query)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    result = ask_traced(query)
    tr = result["trace"]
    print(f"Q: {query}")
    print(f"strategy: {result['strategy']} ({'manual' if tr['route'].get('manual') else 'auto'})")
    print(f"retrieved {tr['retrieve']['n']} units in {tr['retrieve']['latency']:.2f}s")
    print(f"generate: {tr['generate']['tokens']['total']} tokens in {tr['generate']['latency']:.2f}s")
    print(f"total: {tr['total_latency']:.2f}s\n")
    print(result["answer"])
