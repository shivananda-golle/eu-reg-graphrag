"""
Module 0 connectivity smoke test.

Pings each LLM provider with a one-token prompt to confirm three things at once:
  1. The API key in .env is valid.
  2. The SDK is installed and importable.
  3. The network path to the provider works.

Each provider is checked independently, so one failure never hides the others.

Run:  uv run python src/smoke_test.py
"""

import os

from dotenv import load_dotenv

load_dotenv()  # reads .env from the project root into environment variables


def check_mistral() -> str:
    from mistralai import Mistral

    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    resp = client.chat.complete(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    return resp.choices[0].message.content.strip()


def check_groq() -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )
    return resp.choices[0].message.content.strip()


if __name__ == "__main__":
    checks = [
        ("Mistral", check_mistral),
        ("Groq   ", check_groq),
    ]
    print("Module 0 smoke test - LLM connectivity\n" + "-" * 40)
    for name, fn in checks:
        try:
            out = fn()
            print(f"[ OK ] {name}  -> {out!r}")
        except Exception as e:
            print(f"[FAIL] {name}  -> {type(e).__name__}: {e}")
