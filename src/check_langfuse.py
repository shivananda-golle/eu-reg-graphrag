"""
Module 0 — Langfuse trace verification.

Wraps one real Groq LLM call in a Langfuse 'generation' observation, records
token usage, and flushes. Confirms end-to-end that:
  1. The LANGFUSE_* keys + host (region!) in .env are correct.
  2. A trace with the LLM input/output and token counts reaches the dashboard.

Run:  uv run python src/check_langfuse.py
"""

import os

from dotenv import load_dotenv
from groq import Groq
from langfuse import Langfuse

load_dotenv()

# Langfuse() reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
langfuse = Langfuse()

# Fail fast on bad keys or a region/host mismatch — the #1 "trace never showed up" cause.
assert langfuse.auth_check(), "Langfuse auth failed — check keys and LANGFUSE_HOST region"

groq = Groq(api_key=os.environ["GROQ_API_KEY"])
model = "llama-3.3-70b-versatile"
messages = [{"role": "user", "content": "In one sentence, what is the EU AI Act?"}]

trace_url = None
with langfuse.start_as_current_observation(
    name="smoke-groq-call",
    as_type="generation",
    model=model,
    input=messages,
):
    resp = groq.chat.completions.create(model=model, messages=messages)
    answer = resp.choices[0].message.content
    usage = resp.usage  # prompt_tokens / completion_tokens / total_tokens

    # Attach the output + token usage to the current generation so the dashboard
    # shows cost and token counts, not just a bare span.
    langfuse.update_current_generation(
        output=answer,
        usage_details={
            "input": usage.prompt_tokens,
            "output": usage.completion_tokens,
            "total": usage.total_tokens,
        },
    )
    try:
        trace_url = langfuse.get_trace_url()
    except Exception:
        pass

print("LLM answer:", answer)
if trace_url:
    print("Trace URL:", trace_url)

# Langfuse exports traces in a background batch — flush before exit or it never ships.
langfuse.flush()
print("LANGFUSE OK -> trace flushed; open the dashboard to confirm")
