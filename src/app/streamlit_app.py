"""
EU AI Act GraphRAG — conversational demo UI (Streamlit).

A ChatGPT-style chat over the EU AI Act with a glass-box trace under every
answer: routing decision, what was retrieved (seeds, units, scores, traversal),
the exact context sent to the LLM, and the token + latency cost of each stage.
Follow-up questions are condensed into standalone questions (history-aware
retrieval) so the conversation flows naturally.

Run (from the repo root):  uv run streamlit run src/app/streamlit_app.py
"""

import os
import sys

# Make `src` importable when launched via `streamlit run`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from src.agent.agent import ask_traced, condense_query
from src.retrieval.embed import get_model

st.set_page_config(page_title="EU AI Act GraphRAG", page_icon="⚖️", layout="wide")

STRATEGIES = {
    "Auto (agent decides)": None,
    "Vector (semantic)": "vector",
    "Graph (traversal)": "graph",
    "Hybrid (both)": "hybrid",
}


@st.cache_resource
def _warm():
    get_model()  # load the embedding model once, not per message
    return True


_warm()


def render_trace(tr: dict, condensed: str | None) -> None:
    """Render the per-stage trace under an assistant message."""
    route, retr, gen = tr["route"], tr["retrieve"], tr["generate"]
    route_tokens = route.get("tokens", {}).get("total", 0)
    total_tokens = route_tokens + gen["tokens"]["total"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Strategy", route["strategy"] + (" (manual)" if route.get("manual") else " (auto)"))
    c2.metric("Total time", f"{tr['total_latency']:.2f}s")
    c3.metric("Total tokens", total_tokens)
    c4.metric("Units", retr["n"])

    with st.expander("🔍 Trace — how this answer was produced"):
        if condensed:
            st.caption(f"↻ Retrieved as standalone question: *{condensed}*")

        st.markdown(f"**1. Route → `{route['strategy']}`**")
        if route.get("manual"):
            st.caption("Manual override — router skipped.")
        else:
            st.caption(f"Router chose `{route['strategy']}` · {route['latency']:.2f}s · "
                       f"{route['tokens']['total']} tokens")

        st.markdown(f"**2. Retrieve (`{retr['strategy']}`)** — {retr['n']} units · "
                    f"{retr['latency']:.2f}s · 0 tokens (deterministic)")
        st.dataframe(
            [{"citation": u["citation"], "score": u["score"],
              "via_reference": u["via_reference"], "from_seed": u["from_seed"],
              "snippet": u["snippet"]} for u in retr["units"]],
            width="stretch", hide_index=True,
        )

        st.markdown(f"**3. Generate** — {gen['tokens']['total']} tokens "
                    f"(prompt {gen['tokens']['prompt']} / completion {gen['tokens']['completion']}) · "
                    f"{gen['latency']:.2f}s")
        with st.expander("Exact context sent to the LLM"):
            st.text(gen["context"])


# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Retrieval strategy")
choice = st.sidebar.radio("Pick one, or let the agent decide:", list(STRATEGIES))
st.sidebar.caption("Force a strategy to compare them on the same question.")
if st.sidebar.button("🗑️  Clear chat"):
    st.session_state.messages = []
    st.rerun()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("⚖️ EU AI Act — GraphRAG Compliance Assistant")
st.caption(
    "Chat with the EU AI Act (Regulation 2024/1689). Answers are grounded in the "
    "regulation with citations, retrieved by vector search, knowledge-graph "
    "traversal, or both — every step shown."
)

if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {role, content, trace?, condensed?}

# ── Replay history ───────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("trace"):
            render_trace(msg["trace"], msg.get("condensed"))

# ── New turn ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about the EU AI Act…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Routing, retrieving, generating…"):
            history = [(m["role"], m["content"]) for m in st.session_state.messages[:-1]]
            standalone = condense_query(history, prompt)
            result = ask_traced(standalone, STRATEGIES[choice])
        st.markdown(result["answer"])
        condensed = standalone if standalone.strip() != prompt.strip() else None
        render_trace(result["trace"], condensed)

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "trace": result["trace"],
        "condensed": condensed,
    })
