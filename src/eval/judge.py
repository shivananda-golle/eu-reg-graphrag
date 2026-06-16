"""
Module 6, task 6.3a — lightweight LLM-as-judge for answer quality.

Scores each result (in data/eval/results.json) on two axes, 0.0–1.0:
  - faithfulness: is every claim in the answer supported by the retrieved context?
  - correctness : does the answer match the key facts of the reference answer?

Uses a DIFFERENT model than the generator (llama-3.1-8b-instant vs the 70b that
wrote the answers) to avoid self-preference, and to keep off the 70b token cap.
Resumable: skips results already scored; saves after each.

Run (repeat until DONE):  uv run python -m src.eval.judge
"""

import json
import re
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

RESULTS_PATH = Path("data/eval/results.json")
JUDGE_MODEL = "llama-3.1-8b-instant"
CTX_CHARS = 4000  # cap context in the judge prompt to stay token-safe

SYSTEM = (
    "You are a strict evaluator of answers about the EU AI Act. Score two things, "
    "each a number from 0.0 to 1.0:\n"
    "- faithfulness: is every factual claim in the ANSWER supported by the CONTEXT? "
    "1.0 = fully grounded, 0.0 = mostly unsupported/hallucinated.\n"
    "- correctness: does the ANSWER match the key facts in the REFERENCE answer? "
    "1.0 = matches the reference, 0.0 = wrong or missing the point.\n"
    'Respond with ONLY JSON: {"faithfulness": <float>, "correctness": <float>}'
)


def score(client: Groq, row: dict) -> dict:
    context = "\n".join(row["contexts"])[:CTX_CHARS] or "(no context retrieved)"
    user = (
        f"QUESTION:\n{row['question']}\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"ANSWER:\n{row['answer']}\n\n"
        f"REFERENCE:\n{row['reference_answer']}"
    )
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        max_tokens=40,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    )
    text = resp.choices[0].message.content
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}
    return {
        "faithfulness": float(data.get("faithfulness", 0.0)),
        "correctness": float(data.get("correctness", 0.0)),
    }


def main() -> None:
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    todo = [r for r in results if "faithfulness" not in r]
    print(f"{len(results) - len(todo)} scored, {len(todo)} to judge")

    client = Groq()
    for row in todo:
        s = score(client, row)
        row.update(s)
        RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{row['id']:<5} {row['strategy']:<7}] faith={s['faithfulness']:.2f} corr={s['correctness']:.2f}")

    print(f"DONE — judged {len(results)} runs")


if __name__ == "__main__":
    main()
