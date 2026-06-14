"""
Module 4 — graph retrieval over the Neo4j knowledge graph.

Two steps that vector search can't do together:
  1. entry lookup  — a Neo4j full-text (Lucene) index over node title+text finds
     where to start (task 4.1).
  2. traversal     — follow REFERENCES from the entry nodes to pull in connected
     provisions even when their wording doesn't match the query (task 4.2).

Run:  uv run python -m src.retrieval.graph_search "your question"
"""

import os
import re
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

FULLTEXT_INDEX = "nodeText"


def ensure_fulltext_index(driver) -> None:
    """Lucene index over the text-bearing nodes. Missing props (e.g. Paragraph
    has no title) are simply ignored by the index."""
    driver.execute_query(
        f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX} IF NOT EXISTS "
        "FOR (n:Article|Annex|Paragraph|Recital) ON EACH [n.title, n.text]"
    )


# Generic + domain stopwords: in this corpus "ai"/"system" match almost every
# node, so they're noise for entry lookup.
STOPWORDS = {
    "what", "makes", "make", "made", "which", "that", "this", "the", "and", "for",
    "are", "is", "of", "to", "in", "on", "by", "with", "shall", "be", "an", "as",
    "system", "systems", "ai", "artificial", "intelligence", "use", "used", "any",
    "does", "do", "how", "when", "where", "who", "whom", "a",
}


def _lucene_clean(query: str) -> str:
    """Strip Lucene special chars and stopwords; keep a simple OR-of-words query."""
    words = re.findall(r"[A-Za-z0-9]+", query.lower())
    return " ".join(w for w in words if len(w) > 2 and w not in STOPWORDS)


def entry_nodes(driver, query: str, k: int = 5) -> list[dict]:
    """Top-k entry nodes by full-text relevance."""
    records = driver.execute_query(
        f"CALL db.index.fulltext.queryNodes('{FULLTEXT_INDEX}', $q) "
        "YIELD node, score "
        "RETURN labels(node)[0] AS label, node.id AS id, "
        "       coalesce(node.title, '') AS title, score "
        "ORDER BY score DESC LIMIT $k",
        q=_lucene_clean(query), k=k,
    ).records
    return [dict(r) for r in records]


def cite_from_id(nid: str) -> str:
    """Human citation from a node/paragraph id."""
    if nid.startswith("art_"):
        return f"Article {nid[4:]}"
    if nid.startswith("rct_"):
        return f"Recital {nid[4:]}"
    if nid.startswith("anx_"):
        return f"Annex {nid[4:]}"
    m = re.match(r"(\d+)\.(\d+)$", nid)  # paragraph "006.001" -> Article 6(1)
    if m:
        return f"Article {int(m.group(1))}({int(m.group(2))})"
    return nid


def graph_retrieve(driver, query: str, k_entry: int = 3, max_units: int = 10) -> list[dict]:
    """Entry lookup + 1-hop REFERENCES expansion -> text units with citations.

    The graph's edge over vector search: it pulls in REFERENCES-linked provisions
    (e.g. Article 6 -> Annex III) even when their wording doesn't match the query.
    Article nodes carry only a title, so they're expanded to their paragraph text.
    """
    seeds = [r["id"] for r in entry_nodes(driver, query, k_entry)]

    # Focus set = seeds + the nodes they reference (1 hop out).
    rows = driver.execute_query(
        "UNWIND $ids AS sid MATCH (s {id: sid}) "
        "OPTIONAL MATCH (s)-[:REFERENCES]->(t) "
        "RETURN sid AS seed, collect(DISTINCT t.id) AS refs",
        ids=seeds,
    ).records
    focus, ref_targets = list(seeds), set()
    for r in rows:
        for t in r["refs"]:
            if t and t not in focus:
                focus.append(t)
                ref_targets.add(t)

    # Resolve focus nodes to text units (Article -> its paragraphs; others -> self).
    recs = driver.execute_query(
        """
        UNWIND $ids AS fid
        MATCH (f {id: fid})
        CALL (f) {
            MATCH (f:Article)-[:CONTAINS]->(p:Paragraph)
            RETURN p.id AS id, p.text AS text
            UNION
            WITH f WHERE NOT f:Article
            RETURN f.id AS id, f.text AS text
        }
        RETURN fid, id, text
        """,
        ids=focus,
    ).records

    # Group units by their focus node, then emit in focus order (entries first),
    # capping per source so one big article can't flood the context budget.
    by_fid: dict[str, list] = {}
    for r in recs:
        if r["text"]:
            by_fid.setdefault(r["fid"], []).append((r["id"], r["text"]))

    units, seen, per_source = [], set(), 4
    for fid in focus:
        for uid, text in by_fid.get(fid, [])[:per_source]:
            if uid in seen:
                continue
            seen.add(uid)
            units.append({
                "citation": cite_from_id(uid),
                "text": text,
                "via_reference": fid in ref_targets,
                "from_seed": cite_from_id(fid),
            })
            if len(units) >= max_units:
                return units
    return units


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What makes an AI system high-risk?"
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        driver.verify_connectivity()
        ensure_fulltext_index(driver)
        print(f"query: {query!r}")
        print(f"lucene: {_lucene_clean(query)!r}\n")
        print("entry nodes (full-text):")
        for r in entry_nodes(driver, query, 3):
            print(f"  [{r['score']:.2f}] {r['label']:<9} {r['id']:<10} {r['title'][:50]}")

        print("\nassembled context (-> = pulled in via REFERENCES traversal):")
        for u in graph_retrieve(driver, query):
            arrow = f"  <- via {u['from_seed']}" if u["via_reference"] else ""
            snippet = u["text"][:90].replace("\n", " ")
            print(f"  {u['citation']:<16} {snippet}…{arrow}")
    finally:
        driver.close()
