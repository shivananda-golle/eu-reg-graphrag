# Knowledge graph model

The graph the AI Act corpus is loaded into (Neo4j). Spec for `src/graph/`.

## Type of graph — and why

A **property-rich structural graph with explicit reference edges**, not a lexical
(LLM-extracted) graph and not a full domain ontology.

- **Why not lexical (LightRAG / MS-GraphRAG style):** those use an LLM to *discover*
  entities and relations in messy, unstructured text. Statute is the opposite — its
  structure (articles, paragraphs, annexes) is ground-truth and deterministic, and its
  cross-references are written verbatim ("referred to in Annex III"). LLM extraction
  would add cost, non-determinism, and hallucinated edges where none are needed.
- **Why structural:** every node is a real document unit and every edge is provable
  from the source → *citation-grade*, which is the whole point of a compliance tool.
- **Domain overlay** (`Obligation`, `Actor`, `Penalty`) is a **v2 stretch** layered on
  top later; it needs interpretation, so it's out of v1 scope.

## Nodes

Universal key property: **`id`** (already present in `ai_act.json`). One key → clean
`MERGE` and one uniqueness constraint per label. Labels carry type; properties carry
citable text + provenance.

| Label | Key | Properties |
|-------|-----|------------|
| `Document` | `celex` ("32024R1689") | `title`, `source_url` |
| `Recital` | `id` ("rct_1") | `number`, `text` |
| `Article` | `id` ("art_6") | `number`, `title`, `label` |
| `Paragraph` | `id` ("006.001") | `number`, `text` |
| `Annex` | `id` ("anx_III") | `roman`, `title`, `text` |

**Points `(a)(b)(c)` and annex items stay as properties/inline text** (the paragraph/
annex `text` already includes them). Promote to `Point`/`AnnexItem` nodes only if the
reference-extractor later proves point-level targets are needed. Lean now, extend if
measured-necessary.

## Relationships

**Structural** (deterministic, from the JSON tree). One generic name so traversal
Cypher stays clean — `(a:Article)-[:CONTAINS*]->(x)`:

```
(Document) -[:CONTAINS]-> (Recital)
(Document) -[:CONTAINS]-> (Article)
(Document) -[:CONTAINS]-> (Annex)
(Article)  -[:CONTAINS]-> (Paragraph)
```

**Reference** (extracted from prose in tasks 2.3–2.4 — the GraphRAG differentiator).
Edge carries provenance so we can always show *why* it exists:

```
(Article|Paragraph) -[:REFERENCES {raw:"Annex III", kind:"annex"}]-> (Annex|Article)
```

Total: **5 node labels, 2 edge types.**

## Constraints / indexes (task 2.1)

One uniqueness constraint per node key (also creates a backing index, so `MERGE`
and lookups are fast):

```
Document.celex, Recital.id, Article.id, Paragraph.id, Annex.id  → UNIQUE
```

## Loading discipline

- **Idempotent:** use `MERGE`, never `CREATE`, so re-running the loader is safe.
- **Validate by counts** after each load (nodes per label, edges per type), the same
  measure-then-trust habit used in ingestion.
- Source of truth is `data/processed/ai_act.json`; the graph is rebuildable from it.
