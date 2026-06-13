"""
Module 2, task 2.3 — measure how cross-references appear in the AI Act text,
before writing the extractor. We scan the clean JSON (article paragraphs +
annex text) and count the real patterns and traps.

Run:  uv run python src/graph/inspect_refs.py
"""

import json
import re
from collections import Counter
from pathlib import Path

doc = json.loads(Path("data/processed/ai_act.json").read_text(encoding="utf-8"))

# Build (source_id, text) units from every paragraph and annex.
units = []
for a in doc["articles"]:
    for p in a["paragraphs"]:
        units.append((a["id"], p["text"]))
for x in doc["annexes"]:
    units.append((x["id"], x["text"]))
blob = "\n".join(t for _, t in units)

# --- Patterns we expect ---
ART = re.compile(r"Article\s+(\d+)")
# External: "Article N of Regulation/Directive/Decision ..." -> NOT an internal edge.
ART_EXTERNAL = re.compile(
    r"Article\s+\d+(?:\(\d+\))?(?:,\s*point\s*\([a-z]+\))?\s+of\s+"
    r"(?:Regulation|Directive|Decision)"
)
ART_PARA = re.compile(r"Article\s+(\d+)\((\d+)\)")          # Article 6(2)
ART_RANGE = re.compile(r"Articles\s+(\d+)\s+to\s+(\d+)")    # Articles 9 to 15
ANNEX = re.compile(r"Annex\s+([IVXLC]+)")
POINT = re.compile(r"point\s*\(([a-z]+)\)")
PARA_REF = re.compile(r"paragraph\s+(\d+)")
THIS_REG = re.compile(r"this Regulation")

def n(p):
    return len(p.findall(blob))

print("=== raw counts across all paragraph + annex text ===")
print(f"  'Article N'          : {n(ART)}")
print(f"    of which EXTERNAL   : {n(ART_EXTERNAL)}   <- 'Article N of Directive/Regulation ...' (exclude!)")
print(f"  'Article N(p)'        : {n(ART_PARA)}")
print(f"  'Articles N to M'     : {n(ART_RANGE)}   <- ranges, expand to each number")
print(f"  'Annex <roman>'       : {n(ANNEX)}")
print(f"  'point (x)'           : {n(POINT)}")
print(f"  'paragraph N'         : {n(PARA_REF)}")
print(f"  'this Regulation'     : {n(THIS_REG)}")

print("\n=== sample EXTERNAL references (must be excluded) ===")
for m in list(ART_EXTERNAL.finditer(blob))[:6]:
    print("   ", repr(blob[m.start():m.start() + 60]))

print("\n=== sample ranges 'Articles N to M' ===")
for m in list(ART_RANGE.finditer(blob))[:6]:
    print("   ", repr(blob[m.start():m.start() + 40]))

print("\n=== which Annexes get referenced, and how often ===")
print("  ", dict(Counter(ANNEX.findall(blob))))

print("\n=== sanity: does Article 6 text actually mention Annex III? ===")
art6_text = "\n".join(p["text"] for a in doc["articles"] if a["id"] == "art_6" for p in a["paragraphs"])
print("   Annex mentions in Art 6:", ANNEX.findall(art6_text))
