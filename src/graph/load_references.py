"""
Module 2, task 2.4 — extract cross-references from prose and load them as
REFERENCES edges. This is the GraphRAG differentiator: the AI Act's references
are plain text ("referred to in Annex III"), so we turn them into real edges.

Design (from the 2.3 probe, src/graph/inspect_refs.py):
  - source of an edge = the Paragraph (or Annex) whose text contains the ref.
  - target = Article-level (art_N) or Annex (anx_<roman>); the exact "6(2)" is
    preserved in the edge's `raw` property.
  - EXCLUDE external refs ("Article N of Regulation/Directive/Decision").
  - expand internal ranges ("Articles 8 to 15"); validate targets exist; MERGE
    dedupes repeated mentions.

Run:  uv run python src/graph/load_references.py
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

JSON_PATH = Path("data/processed/ai_act.json")

# "of Regulation/Directive/Decision" right after the number => external, skip.
_EXTERNAL = r"(\s+of\s+(?:Regulation|Directive|Decision))?"
ART = re.compile(r"Article\s+(\d+)(?:\((\d+)\))?(?:,\s*point\s*\([a-z]+\))?" + _EXTERNAL)
ART_RANGE = re.compile(r"Articles\s+(\d+)\s+to\s+(\d+)" + _EXTERNAL)
ANNEX = re.compile(r"Annex\s+([IVXLC]+)" + _EXTERNAL)


def extract_refs(text: str, valid_articles: set, valid_annexes: set,
                 own_article: int | None) -> list[tuple]:
    """Return (target_label, target_id, raw, kind) tuples for one text unit."""
    out = []

    for m in ART.finditer(text):
        if m.group(3):                       # " of Regulation/Directive ..." -> external
            continue
        num = int(m.group(1))
        if num not in valid_articles or num == own_article:
            continue
        out.append(("Article", f"art_{num}", m.group(0).strip(), "article"))

    for m in ART_RANGE.finditer(text):
        if m.group(3):
            continue
        for num in range(int(m.group(1)), int(m.group(2)) + 1):
            if num in valid_articles and num != own_article:
                out.append(("Article", f"art_{num}", m.group(0).strip(), "article-range"))

    for m in ANNEX.finditer(text):
        if m.group(2):
            continue
        roman = m.group(1)
        if roman in valid_annexes:
            out.append(("Annex", f"anx_{roman}", f"Annex {roman}", "annex"))

    return out


def build_edges(doc: dict) -> dict:
    """Group edges by (source_label, target_label) so each can load with explicit
    labels (one UNWIND query per combo)."""
    valid_articles = {a["number"] for a in doc["articles"]}
    valid_annexes = {a["roman"] for a in doc["annexes"]}
    groups = defaultdict(list)

    # Sources: paragraphs (own_article known) and annexes (no own article).
    for a in doc["articles"]:
        for p in a["paragraphs"]:
            for tlabel, tid, raw, kind in extract_refs(
                p["text"], valid_articles, valid_annexes, a["number"]
            ):
                groups[("Paragraph", tlabel)].append(
                    {"source_id": p["para_id"], "target_id": tid, "raw": raw, "kind": kind}
                )
    for x in doc["annexes"]:
        for tlabel, tid, raw, kind in extract_refs(
            x["text"], valid_articles, valid_annexes, None
        ):
            groups[("Annex", tlabel)].append(
                {"source_id": x["id"], "target_id": tid, "raw": raw, "kind": kind}
            )
    return groups


def load_references(driver, groups: dict) -> None:
    with driver.session() as session:
        for (src_label, tgt_label), rows in groups.items():
            session.run(
                f"""
                UNWIND $rows AS row
                  MATCH (s:{src_label} {{id: row.source_id}})
                  MATCH (t:{tgt_label} {{id: row.target_id}})
                  MERGE (s)-[r:REFERENCES]->(t)
                    SET r.raw = row.raw, r.kind = row.kind
                """,
                rows=rows,
            )
            print(f"  {src_label} -> {tgt_label}: {len(rows)} ref mentions")


def report(driver) -> None:
    with driver.session() as session:
        total = session.run("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c").single()["c"]
        print(f"\nREFERENCES edges (deduped): {total}")

        print("\nheadline check — Article 6 reaches Annex III:")
        rec = session.run(
            "MATCH (a:Article {id:'art_6'})-[:CONTAINS]->(:Paragraph)"
            "-[r:REFERENCES]->(x:Annex {id:'anx_III'}) RETURN count(r) AS c"
        ).single()
        print(f"  art_6 -CONTAINS-> Paragraph -REFERENCES-> anx_III : {rec['c']} edge(s)")

        print("\nmost-referenced targets:")
        for r in session.run(
            "MATCH ()-[:REFERENCES]->(t) "
            "RETURN labels(t)[0] AS label, t.id AS id, count(*) AS c "
            "ORDER BY c DESC LIMIT 8"
        ):
            print(f"  {r['label']:<9} {r['id']:<10} <- {r['c']} refs")


if __name__ == "__main__":
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    groups = build_edges(doc)
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        print("connected; loading REFERENCES edges...")
        load_references(driver, groups)
        report(driver)
    finally:
        driver.close()
