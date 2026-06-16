"""
Module 7 — Langfuse observability.

Emits every agent run to Langfuse as a nested trace:

    rag-query (span)
    ├─ route        (span)   strategy + router tokens/latency
    ├─ retrieve:<s> (span)   citations + units/latency
    └─ generate     (generation)  answer + token usage  -> cost/latency dashboards

The agent already captures all of this in result["trace"] (the same data the UI
shows), so we just replay it to Langfuse. Logging is best-effort: any Langfuse
error is swallowed so observability never breaks the app.
"""

import os

from dotenv import load_dotenv

load_dotenv()

GEN_MODEL = "llama-3.3-70b-versatile"
_client = None


def _langfuse():
    global _client
    if _client is None:
        from langfuse import Langfuse
        _client = Langfuse()
    return _client


def log_run(query: str, result: dict) -> None:
    """Best-effort: push one agent run to Langfuse as a nested trace."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        lf = _langfuse()
        tr = result["trace"]
        route, retr, gen = tr["route"], tr["retrieve"], tr["generate"]

        with lf.start_as_current_observation(
            name="rag-query", as_type="span", input={"query": query}
        ):
            with lf.start_as_current_observation(
                name="route", as_type="span",
                input={"query": query}, output={"strategy": route["strategy"]},
            ):
                lf.update_current_span(metadata={
                    "manual": route.get("manual", False),
                    "latency_s": route.get("latency"),
                    "tokens": route.get("tokens"),
                })

            with lf.start_as_current_observation(
                name=f"retrieve:{retr['strategy']}", as_type="span",
                output={"citations": [u["citation"] for u in retr["units"]]},
            ):
                lf.update_current_span(metadata={
                    "units": retr["n"],
                    "latency_s": retr["latency"],
                    "context_chars": retr["context_chars"],
                })

            with lf.start_as_current_observation(
                name="generate", as_type="generation",
                model=GEN_MODEL, input={"query": query},
            ):
                lf.update_current_generation(
                    output=result["answer"],
                    usage_details={
                        "input": gen["tokens"]["prompt"],
                        "output": gen["tokens"]["completion"],
                        "total": gen["tokens"]["total"],
                    },
                    metadata={"latency_s": gen["latency"]},
                )

            lf.update_current_span(output={
                "answer": result["answer"],
                "strategy": result["strategy"],
                "total_latency_s": tr["total_latency"],
            })
        lf.flush()
    except Exception as e:  # noqa: BLE001 — observability must never break the app
        print(f"[langfuse] log skipped: {e}")
