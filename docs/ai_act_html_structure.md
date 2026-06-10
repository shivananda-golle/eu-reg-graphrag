# AI Act HTML — structure notes

Empirical map of the source document, produced by inspecting the real HTML
(`src/ingestion/inspect_structure.py` + `inspect_refs.py`). This is the spec the
parser in the next step is written against.

## Source

- **Document:** Regulation (EU) 2024/1689 (the EU AI Act)
- **CELEX:** `32024R1689`, English
- **URL:** `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689`
- **Format:** EUR-Lex HTML generated from **Formex XML** (title is `...fmx.xml`) → markup is standardised and stable (`eli-*` / `oj-*` classes).
- **Size:** ~1.3 MB, 10,292 elements.
- **Download gotcha:** first request can return 0 bytes (session-cookie warm-up); retry succeeds. Send a browser `User-Agent`.
- **Local path:** `data/raw/ai_act_32024R1689.html` (gitignored).

## Hierarchy & the classes that mark it

```
div.eli-subdivision  id="art_6"            ← article container (stable id)
├─ p.oj-ti-art       "Article 6"           ← article number (note: \xa0 nbsp!)
├─ div.eli-title
│  └─ p.oj-sti-art   "Classification ..."  ← article title
└─ div  id="006.001"                       ← paragraph (id encodes art.para)
   ├─ p.oj-normal    "1. ..."              ← paragraph text
   └─ table          (a) ... / (b) ...     ← lettered points are TABLES, not lists
```

| Class | Count | Role |
|-------|------:|------|
| `oj-normal` | 2300 | body paragraph text |
| `eli-subdivision` | 303 | structural containers (articles, chapters, sections, annexes) |
| `oj-ti-art` | 113 | "Article N" headings → **113 articles total** |
| `oj-sti-art` | 113 | article titles (1:1 with articles) |
| `oj-ti-section-1/2`, `oj-ti-grseq-1` | 29/29/21 | section & chapter titles |
| `eli-title` | 142 | title wrappers |

## Gotchas the parser must handle

1. **Non-breaking spaces** in headings: `"Article\xa06"`, not `"Article 6"`. Normalise `\xa0 → space` before matching.
2. **Lettered points `(a)(b)(c)` are 2-column HTML tables** (narrow col = label, wide col = text), not `<ul>`/`<ol>`. Must read table cells, not just `<p>`.
3. **Paragraph IDs encode position**: `id="006.001"` = Article 6, paragraph 1 — usable as a stable key.
4. Document is XHTML — parse with an explicit parser and silence `XMLParsedAsHTMLWarning`.

## Cross-references (important for Module 2)

- **NOT hyperlinked.** All 125 internal `<a href="#...">` are footnotes (`ntr`/`ntc`).
- References live as **plain prose**: 615 "Article" mentions, 122 "Annex" mentions.
- → Module 2 needs a **reference-extractor** (regex for `Article N(p)`, `Annex <roman>`, `point (x)`) to build graph edges. This is expected, standard work.

## Other components still to map

- **Recitals** (the numbered "Whereas" block before Article 1).
- **Annexes I–XIII** (where the high-risk lists live) — likely `eli-subdivision` with annex ids.
- Confirm chapter/section nesting via `oj-ti-grseq-1` / `oj-ti-section-*`.
