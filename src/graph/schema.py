"""
Module 2, task 2.1 — knowledge graph schema.

Creates one uniqueness constraint per node key (per docs/graph_model.md). A
uniqueness constraint also builds a backing index, so MERGE during loading is
fast and idempotent. Safe to re-run: every statement uses IF NOT EXISTS.

Run:  uv run python src/graph/schema.py
"""

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# (label, key property) — Document is keyed by celex, everything else by id.
CONSTRAINTS = [
    ("Document", "celex"),
    ("Recital", "id"),
    ("Article", "id"),
    ("Paragraph", "id"),
    ("Annex", "id"),
]


def ensure_constraints(driver) -> None:
    with driver.session() as session:
        for label, key in CONSTRAINTS:
            name = f"{label.lower()}_{key}_unique"
            session.run(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            )
            print(f"  [ok] {label}.{key} UNIQUE")

        print("\nconstraints now in the database:")
        for rec in session.run("SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties"):
            print(f"  {rec['name']}: {rec['labelsOrTypes']} {rec['properties']}")


if __name__ == "__main__":
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        print("connected; ensuring constraints...\n")
        ensure_constraints(driver)
    finally:
        driver.close()
