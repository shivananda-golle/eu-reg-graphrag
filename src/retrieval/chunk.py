"""
Module 3, task 3.1 — chunk the structured AI Act into retrieval units.

Granularity = the natural legal unit:
  - article paragraph -> one chunk (points stay inline)
  - recital           -> one chunk (tagged, never cited as a binding rule)
  - annex item        -> one chunk (so Annex III's 8 categories aren't one blob)

Every chunk carries `node_id` = the graph node it maps to (paragraph id,
recital id, or annex id). That shared id is the bridge to the knowledge graph
for hybrid retrieval later. Output is gitignored JSONL for inspection.

Run:  uv run python -m src.retrieval.chunk
"""

import json
from pathlib import Path

JSON_PATH = Path("data/processed/ai_act.json")
OUT_PATH = Path("data/processed/ai_act_chunks.jsonl")


def build_chunks(doc: dict) -> list[dict]:
    celex, url = doc["celex"], doc["source_url"]
    base = {"celex": celex, "source_url": url}
    chunks = []

    # Article paragraphs.
    for a in doc["articles"]:
        for p in a["paragraphs"]:
            if not p["text"].strip():
                continue
            chunks.append({
                **base,
                "chunk_id": p["para_id"],
                "node_id": p["para_id"],
                "node_type": "paragraph",
                "article": a["number"],
                "article_title": a["title"],
                "paragraph": p["number"],
                "citation": f"Article {a['number']}" + (f"({p['number']})" if p["number"] else ""),
                "text": p["text"],
            })

    # Recitals.
    for r in doc["recitals"]:
        chunks.append({
            **base,
            "chunk_id": f"rct_{r['number']}",
            "node_id": f"rct_{r['number']}",
            "node_type": "recital",
            "citation": f"Recital {r['number']}",
            "text": r["text"],
        })

    # Annexes: one chunk per item; whole annex when it has no items.
    for x in doc["annexes"]:
        if x["items"]:
            for i, it in enumerate(x["items"], 1):
                chunks.append({
                    **base,
                    "chunk_id": f"{x['id']}#{i}",
                    "node_id": x["id"],
                    "node_type": "annex_item",
                    "annex": x["roman"],
                    "annex_title": x["title"],
                    "citation": f"Annex {x['roman']}, {it['label']}",
                    "text": f"{it['label']} {it['text']}",
                })
        else:
            chunks.append({
                **base,
                "chunk_id": x["id"],
                "node_id": x["id"],
                "node_type": "annex",
                "annex": x["roman"],
                "annex_title": x["title"],
                "citation": f"Annex {x['roman']}",
                "text": x["text"],
            })

    return chunks


if __name__ == "__main__":
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    chunks = build_chunks(doc)

    OUT_PATH.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8"
    )

    by_type: dict[str, int] = {}
    lengths = []
    for c in chunks:
        by_type[c["node_type"]] = by_type.get(c["node_type"], 0) + 1
        lengths.append(len(c["text"]))

    print(f"chunks: {len(chunks)}  ->  {OUT_PATH}")
    print("by type:", by_type)
    print(f"text length chars: min={min(lengths)} max={max(lengths)} "
          f"avg={sum(lengths) // len(lengths)}")

    longest = max(chunks, key=lambda c: len(c["text"]))
    print(f"\nlongest chunk: {longest['citation']} ({len(longest['text'])} chars) "
          f"[{longest['node_type']}]")
    print("\nsample chunk:")
    print(json.dumps({**chunks[0], "text": chunks[0]["text"][:90] + "…"}, indent=2, ensure_ascii=False))
