"""
Module 2 — rebuild the whole knowledge graph from data/processed/ai_act.json in
one command: constraints -> structural nodes/CONTAINS -> REFERENCES edges.
Every step is idempotent (MERGE + IF NOT EXISTS), so this is safe to re-run.

Run:  uv run python -m src.graph.build_graph
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.graph.load_references import build_edges, load_references
from src.graph.load_references import report as report_refs
from src.graph.load_structure import load_structure
from src.graph.load_structure import report as report_structure
from src.graph.schema import ensure_constraints

load_dotenv()


def main() -> None:
    doc = json.loads(Path("data/processed/ai_act.json").read_text(encoding="utf-8"))
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        print("== 1. constraints ==")
        ensure_constraints(driver)
        print("\n== 2. structural nodes + CONTAINS ==")
        load_structure(driver, doc)
        report_structure(driver)
        print("\n== 3. REFERENCES edges ==")
        load_references(driver, build_edges(doc))
        report_refs(driver)
        print("\ngraph build complete.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
