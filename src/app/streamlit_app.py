"""
EU AI Act GraphRAG — interactive demo UI (Streamlit).

A glass-box console: ask a compliance question, pick a retrieval strategy (or let
the agent decide), and see the FULL trace — routing decision, what was retrieved
(seeds, units, scores, traversal), the exact context sent to the LLM, and the
token + latency cost of every stage.

Run (from the repo root):  uv run streamlit run src/app/streamlit_app.py
"""

import os
import sys

# Make `src` importable when launched via `streamlit run`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from src.agent.agent import ask_traced
from src.retrieval.embed import get_model

st.set_page_config(page_title="EU AI Act GraphRAG", page_icon="⚖️", layout="wide")


@st.cache_resource
def _warm():
    """Load the embedding model once (not per question)."""
    get_model()
    return True


_warm()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("⚖️ EU AI Act — GraphRAG Compliance Assistant")
st.caption(
    "Ask a compliance question about the EU AI Act (Regulation 2024/1689). "
    "Answers are grounded in the regulation with citations, retrieved by vector "
    "search, knowledge-graph traversal, or both — and every step is shown."
)

with st.expander("ℹ️  What is this?"):
    st.markdown(
        "- **Corpus:** the full EU AI Act, parsed into 113 articles, 180 recitals, "
        "13 annexes.\n"
        "- **Two indexes:** a **vector store** (semantic search) and a **Neo4j "
        "knowledge graph** (articles/annexes as nodes, cross-references as edges).\n"
        "- **The agent** routes each question to the best retrieval strategy, then "
        "an LLM writes a cited answer **only** from what was retrieved.\n"
        "- Retrieval is **deterministic** (no tokens); only routing and answer "
        "generation use the LLM."
    )

# ── Controls ─────────────────────────────────────────────────────────────────
STRATEGIES = {
    "Auto (agent decides)": None,
    "Vector (semantic)": "vector",
    "Graph (traversal)": "graph",
    "Hybrid (both)": "hybrid",
}
st.sidebar.header("Retrieval strategy")
choice = st.sidebar.radio("Pick one, or let the agent decide:", list(STRATEGIES))
st.sidebar.caption(
    "Force a strategy to compare them on the same question — e.g. Vector vs Graph "
    "on *'What makes an AI system high-risk?'*"
)

query = st.text_input("Your question", "What makes an AI system high-risk?")
go = st.button("Ask", type="primary")

# ── Run ──────────────────────────────────────────────────────────────────────
if go and query.strip():
    with st.spinner("Routing, retrieving, generating…"):
        result = ask_traced(query, STRATEGIES[choice])
    tr = result["trace"]
    route, retr, gen = tr["route"], tr["retrieve"], tr["generate"]
    route_tokens = route.get("tokens", {}).get("total", 0)
    total_tokens = route_tokens + gen["tokens"]["total"]

    # Answer
    st.subheader("Answer")
    st.markdown(result["answer"])

    # Headline metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strategy", result["strategy"] + (" (manual)" if route.get("manual") else " (auto)"))
    c2.metric("Total time", f"{tr['total_latency']:.2f}s")
    c3.metric("Total tokens", total_tokens)
    c4.metric("Units retrieved", retr["n"])

    # ── Full trace ───────────────────────────────────────────────────────────
    st.subheader("🔍 Full trace")

    with st.expander(f"1️⃣  Route → **{result['strategy']}**", expanded=True):
        if route.get("manual"):
            st.info("Manual override — the router was skipped.")
        else:
            st.write(f"The router (LLM) chose **{route['strategy']}** in {route['latency']:.2f}s.")
            t = route["tokens"]
            st.write(f"Router tokens — prompt {t['prompt']} / completion {t['completion']} / **total {t['total']}**")

    with st.expander(
        f"2️⃣  Retrieve ({retr['strategy']}) — {retr['n']} units · {retr['latency']:.2f}s · "
        "0 tokens (deterministic)",
        expanded=True,
    ):
        st.caption(
            "Retrieval runs on Qdrant / Neo4j — it costs *time, not tokens*. "
            "`via_reference` = pulled in by graph traversal; `from_seed` = the node it came from."
        )
        st.dataframe(
            [
                {
                    "citation": u["citation"],
                    "score": u["score"],
                    "via_reference": u["via_reference"],
                    "from_seed": u["from_seed"],
                    "snippet": u["snippet"],
                }
                for u in retr["units"]
            ],
            width="stretch",
            hide_index=True,
        )
        st.caption(f"Context assembled: {retr['context_chars']:,} characters.")

    with st.expander(
        f"3️⃣  Generate — {gen['tokens']['total']} tokens · {gen['latency']:.2f}s",
        expanded=True,
    ):
        t = gen["tokens"]
        st.write(f"Generation tokens — prompt {t['prompt']} / completion {t['completion']} / **total {t['total']}**")
        with st.expander("Show the exact context sent to the LLM"):
            st.text(gen["context"])
