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

# Paragraphs longer than this (chars) risk truncation at BGE's 512-token limit,
# so if they have points we split them into one chunk per point. ~1500 chars is
# comfortably under the limit; short paragraphs stay whole.
LONG_PARA = 1500
LEAD_CHARS = 200  # how much of the paragraph's lead to prepend for context


def _lead(text: str, points: list[dict]) -> str:
    """The paragraph's prose with its point bodies removed — the intro/context
    we prepend to each point chunk so it still embeds well on its own."""
    lead = text
    for pt in points:
        lead = lead.replace(f"{pt['label']} {pt['text']}", " ")
    return " ".join(lead.split())


def build_chunks(doc: dict) -> list[dict]:
    celex, url = doc["celex"], doc["source_url"]
    base = {"celex": celex, "source_url": url}
    chunks = []

    # Article paragraphs. Long, point-heavy paragraphs (e.g. Article 3's 68
    # definitions) get split into one chunk per point so each is independently
    # searchable instead of one blob the embedder truncates at 512 tokens.
    for a in doc["articles"]:
        for p in a["paragraphs"]:
            if not p["text"].strip():
                continue
            cite = f"Article {a['number']}" + (f"({p['number']})" if p["number"] else "")
            common = {
                **base, "node_id": p["para_id"], "article": a["number"],
                "article_title": a["title"], "paragraph": p["number"],
            }
            if p["points"] and len(p["text"]) > LONG_PARA:
                lead = _lead(p["text"], p["points"])[:LEAD_CHARS]
                for i, pt in enumerate(p["points"], 1):
                    chunks.append({
                        **common,
                        "chunk_id": f"{p['para_id']}#p{i}",
                        "node_type": "point",
                        "citation": f"{cite} {pt['label']}".strip(),
                        # prepend article title + lead so the point has context
                        "text": f"{a['title']}. {lead} {pt['label']} {pt['text']}".strip(),
                    })
            else:
                chunks.append({
                    **common,
                    "chunk_id": p["para_id"],
                    "node_type": "paragraph",
                    "citation": cite,
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
