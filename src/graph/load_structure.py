"""
Module 2, task 2.2 — load the structural skeleton into Neo4j.

Reads data/processed/ai_act.json and creates the nodes (Document, Recital,
Article, Paragraph, Annex) and the CONTAINS hierarchy. No REFERENCES edges yet
(that's 2.3/2.4). Everything is MERGE-based on the node key, so re-running is
idempotent. Batched with UNWIND: one query per node-type, not per node.

Run:  uv run python src/graph/load_structure.py
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

JSON_PATH = Path("data/processed/ai_act.json")


def load_structure(driver, doc: dict) -> None:
    with driver.session() as session:
        celex = doc["celex"]

        # 1. Document root.
        session.run(
            "MERGE (d:Document {celex:$celex}) "
            "SET d.title=$title, d.source_url=$url",
            celex=celex, title=doc["title"], url=doc["source_url"],
        )

        # 2. Recitals — synthesize id 'rct_<n>'; Document-CONTAINS->Recital.
        recitals = [
            {"id": f"rct_{r['number']}", "number": r["number"], "text": r["text"]}
            for r in doc["recitals"]
        ]
        session.run(
            """
            MATCH (d:Document {celex:$celex})
            UNWIND $rows AS row
              MERGE (n:Recital {id: row.id})
                SET n.number = row.number, n.text = row.text
              MERGE (d)-[:CONTAINS]->(n)
            """,
            celex=celex, rows=recitals,
        )

        # 3. Annexes — Document-CONTAINS->Annex.
        annexes = [
            {"id": a["id"], "roman": a["roman"], "title": a["title"], "text": a["text"]}
            for a in doc["annexes"]
        ]
        session.run(
            """
            MATCH (d:Document {celex:$celex})
            UNWIND $rows AS row
              MERGE (n:Annex {id: row.id})
                SET n.roman = row.roman, n.title = row.title, n.text = row.text
              MERGE (d)-[:CONTAINS]->(n)
            """,
            celex=celex, rows=annexes,
        )

        # 4. Articles — Document-CONTAINS->Article.
        articles = [
            {"id": a["id"], "number": a["number"], "title": a["title"], "label": a["label"]}
            for a in doc["articles"]
        ]
        session.run(
            """
            MATCH (d:Document {celex:$celex})
            UNWIND $rows AS row
              MERGE (n:Article {id: row.id})
                SET n.number = row.number, n.title = row.title, n.label = row.label
              MERGE (d)-[:CONTAINS]->(n)
            """,
            celex=celex, rows=articles,
        )

        # 5. Paragraphs — Article-CONTAINS->Paragraph.
        paragraphs = [
            {"id": p["para_id"], "art_id": a["id"], "number": p["number"], "text": p["text"]}
            for a in doc["articles"]
            for p in a["paragraphs"]
        ]
        session.run(
            """
            UNWIND $rows AS row
              MATCH (a:Article {id: row.art_id})
              MERGE (n:Paragraph {id: row.id})
                SET n.number = row.number, n.text = row.text
              MERGE (a)-[:CONTAINS]->(n)
            """,
            rows=paragraphs,
        )


def report(driver) -> None:
    with driver.session() as session:
        print("\nnode counts:")
        for label, expected in [("Document", 1), ("Recital", 180), ("Article", 113),
                                ("Paragraph", 519), ("Annex", 13)]:
            n = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            flag = "" if n == expected else f"  <-- expected {expected}"
            print(f"  {label:<10} {n:>4}{flag}")

        rels = session.run(
            "MATCH ()-[r:CONTAINS]->() RETURN count(r) AS c"
        ).single()["c"]
        print(f"\nCONTAINS edges: {rels}  (expected 825)")


if __name__ == "__main__":
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        print("connected; loading structure...")
        load_structure(driver, doc)
        report(driver)
    finally:
        driver.close()
