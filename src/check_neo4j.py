"""
Module 0 — Neo4j AuraDB connection check.

Confirms three things:
  1. The NEO4J_* values in .env are correct.
  2. TLS auth to the managed instance succeeds (verify_connectivity).
  3. We can run a Cypher query and read a result.

Run:  uv run python src/check_neo4j.py
"""

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

uri = os.environ["NEO4J_URI"]
user = os.environ["NEO4J_USERNAME"]
password = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(user, password))
try:
    driver.verify_connectivity()  # fails fast on bad URI / auth / TLS
    with driver.session() as session:
        ok = session.run("RETURN 1 AS ok").single()["ok"]
    print(f"NEO4J OK -> RETURN 1 returned {ok}")
    print(f"  connected to: {uri}")
finally:
    driver.close()
