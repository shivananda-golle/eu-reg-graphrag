"""
Module 1 — AI Act parser.

Walks the structure documented in docs/ai_act_html_structure.md and turns the
raw EUR-Lex HTML into clean, labeled records:

    article -> {id, number, title, paragraphs[
                  {para_id, number, text, points[{label, text}]} ]}

Built in verifiable layers: piece 1 = article headers, piece 2 = paragraphs
and their lettered points. Each point is its own little 2-cell table, and
points sit *between* text blocks, so we walk children in document order to
keep "intro -> (a)(b) -> continuation" intact.

Run:  uv run python src/ingestion/parse_ai_act.py
"""

import json
import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# The doc is XHTML (gotcha #4 in docs/ai_act_html_structure.md); lxml parses it
# fine but warns. We've made the choice deliberately, so silence the noise.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

HTML_PATH = Path("data/raw/ai_act_32024R1689.html")

# Paragraph containers carry ids like "006.001" = article 6, paragraph 1.
PARA_ID_RE = re.compile(r"^\d{3}\.\d{3}$")
# Recitals: div.eli-subdivision id="rct_1".."rct_180".
RCT_ID_RE = re.compile(r"^rct_(\d+)$")
# Annexes: div.eli-container id="anx_I".."anx_XIII".
ANX_ID_RE = re.compile(r"^anx_")


def norm(s: str) -> str:
    """Collapse the non-breaking spaces (\xa0) EUR-Lex uses, then trim."""
    return s.replace("\xa0", " ").strip()


def cell_label_text(cells) -> tuple[str, str] | None:
    """Split a point/item row into (label, text) by CONTENT, not position.

    Some tables are 2-cell (`['1.', 'text']`, e.g. Annex III) and some have a
    leading empty spacer cell (`['', '1.', 'text']`, e.g. Annex I). Dropping
    empty cells first makes both layouts work: first non-empty = label, rest =
    text. Returns None if there isn't a label + text pair.
    """
    vals = [norm(c.get_text(" ")) for c in cells]
    vals = [v for v in vals if v]
    if len(vals) < 2:
        return None
    return vals[0], " ".join(vals[1:])


def _extract_blocks(children) -> tuple[list[str], list[dict]]:
    """Walk a list of sibling elements in document order, separating prose from
    points. Returns (ordered_text_blocks, structured_points).

    Each lettered/numbered point is its own small table (cell 0 = label like
    "(a)" or "(1)", cell 1 = text). We read only each table's OWN top-level
    rows so nested sub-points stay inside their parent's text instead of being
    counted as separate points.
    """
    ordered, points = [], []
    for child in children:
        classes = child.get("class") or []
        if child.name == "p" and "oj-normal" in classes:
            ordered.append(norm(child.get_text(" ")))
        elif child.name == "table":
            own_rows = [r for r in child.find_all("tr") if r.find_parent("table") is child]
            for row in own_rows:
                lt = cell_label_text(row.find_all(["td", "th"], recursive=False))
                if lt:
                    label, ptext = lt
                    points.append({"label": label, "text": ptext})
                    ordered.append(f"{label} {ptext}")
    return ordered, points


def parse_paragraphs(container) -> list[dict]:
    """Extract paragraphs (and their points) from an article container.

    Two shapes exist in the AI Act:
      - Numbered: body is a series of <div id="006.001"> paragraph wrappers.
      - Unnumbered: a single paragraph whose prose + point-tables sit directly
        in the article container (e.g. Art 3 Definitions, Art 4, Art 16).
    """
    para_divs = [
        d for d in container.find_all("div", recursive=False)
        if PARA_ID_RE.match(d.get("id", ""))
    ]

    if para_divs:
        paragraphs = []
        for div in para_divs:
            number = int(div["id"].split(".")[1])  # "006.001" -> 1
            ordered, points = _extract_blocks(div.find_all(recursive=False))
            text = re.sub(r"^\d+\.\s+", "", "\n".join(ordered))  # drop "1. " marker
            paragraphs.append(
                {"para_id": div["id"], "number": number, "text": text, "points": points}
            )
        return paragraphs

    # Unnumbered: skip the heading and title wrapper, take the rest as one para.
    children = [
        c for c in container.find_all(recursive=False)
        if not ({"oj-ti-art", "eli-title"} & set(c.get("class") or []))
    ]
    ordered, points = _extract_blocks(children)
    text = "\n".join(ordered)
    if not text:
        return []
    return [{"para_id": container.get("id"), "number": None, "text": text, "points": points}]


def parse_articles(html: str) -> list[dict]:
    """Return one record per article (with nested paragraphs), in document order."""
    soup = BeautifulSoup(html, "lxml")
    articles = []

    # Each "Article N" heading is a p.oj-ti-art (exactly 113 of them).
    for heading in soup.find_all(class_="oj-ti-art"):
        # Climb to the div.eli-subdivision that wraps the whole article.
        container = heading.find_parent(class_="eli-subdivision")
        if container is None:
            continue

        label = norm(heading.get_text())             # "Article 6"
        m = re.search(r"Article\s+(\d+)", label)      # pull the integer
        number = int(m.group(1)) if m else None

        # Title is the sibling p.oj-sti-art inside the same container.
        # Known EUR-Lex artifact: Article 1's title ends in a stray backtick
        # (measured: it's the only one). Strip trailing backticks only.
        title_el = container.find(class_="oj-sti-art")
        title = norm(title_el.get_text()).rstrip("`").strip() if title_el else None

        articles.append(
            {
                "id": container.get("id"),  # e.g. "art_6" — our stable key
                "number": number,
                "label": label,
                "title": title,
                "paragraphs": parse_paragraphs(container),
            }
        )

    return articles


def parse_recitals(soup) -> list[dict]:
    """The ~180 numbered 'Whereas' clauses. Non-binding context — tagged so the
    system can use them for interpretation but never cite them as obligations."""
    recitals = []
    for div in soup.find_all("div", class_="eli-subdivision", id=RCT_ID_RE):
        number = int(RCT_ID_RE.match(div["id"]).group(1))
        text = re.sub(r"^\(\d+\)\s*", "", norm(div.get_text(" ")))  # drop "(1)"
        recitals.append({"number": number, "text": text, "type": "recital"})
    return recitals


def parse_annexes(soup) -> list[dict]:
    """The annexes (I–XIII) — the lists articles point to (e.g. Annex III =
    high-risk systems). Each is a div.eli-container#anx_<roman> holding two
    oj-doc-ti (label + title) then body content.

    Annex bodies vary (tables, enumeration divs, section headers), so rather
    than enumerate every markup, we take the text of every direct child except
    the two headers — robust to whatever shape an annex uses. Structured
    `items` are a best-effort bonus for the table-based annexes (e.g. III)."""
    annexes = []
    for cont in soup.find_all("div", class_="eli-container", id=ANX_ID_RE):
        doctis = cont.find_all("p", class_="oj-doc-ti")
        label = norm(doctis[0].get_text()) if doctis else ""          # "ANNEX III"
        title = norm(doctis[1].get_text()) if len(doctis) > 1 else None
        roman = label.replace("ANNEX", "").strip() or None

        parts, items = [], []
        for ch in cont.find_all(recursive=False):
            if "oj-doc-ti" in (ch.get("class") or []):
                continue  # skip the label + title headers
            text = norm(ch.get_text(" "))
            if text:
                parts.append(text)
            if ch.name == "table":  # structured item (label, text) when present
                row = ch.find("tr")
                lt = cell_label_text(row.find_all(["td", "th"], recursive=False)) if row else None
                if lt:
                    items.append({"label": lt[0], "text": lt[1]})

        annexes.append(
            {"id": cont.get("id"), "label": label, "roman": roman, "title": title,
             "text": "\n".join(parts), "items": items}
        )
    return annexes


def parse_document(html: str) -> dict:
    """Full structured AI Act: recitals, articles (with paragraphs/points), annexes.

    Top-level provenance (celex/title/source_url) travels with the data so every
    downstream citation can trace back to the authoritative EUR-Lex source.
    """
    soup = BeautifulSoup(html, "lxml")
    return {
        "celex": "32024R1689",
        "title": "Regulation (EU) 2024/1689 (Artificial Intelligence Act)",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689",
        "recitals": parse_recitals(soup),
        "articles": parse_articles(html),
        "annexes": parse_annexes(soup),
    }


if __name__ == "__main__":
    articles = parse_articles(HTML_PATH.read_text(encoding="utf-8"))

    print(f"articles found: {len(articles)} (expected 113)")

    total_paras = sum(len(a["paragraphs"]) for a in articles)
    total_points = sum(len(p["points"]) for a in articles for p in a["paragraphs"])
    print(f"paragraphs: {total_paras}   points: {total_points}")

    # Validation flag: which articles parsed to zero paragraphs? (worth a look)
    empty = [a["number"] for a in articles if not a["paragraphs"]]
    print(f"articles with 0 paragraphs: {empty}")

    # Spot-check Article 6: expect 8 paragraphs; para 1 has points (a)(b),
    # para 3 is the interleaved intro -> points -> continuation case.
    art6 = next((a for a in articles if a["number"] == 6), None)
    print(f"\nArticle 6 — {art6['title']} — {len(art6['paragraphs'])} paragraphs")

    for n in (1, 3):
        p = next(pp for pp in art6["paragraphs"] if pp["number"] == n)
        print(f"\n--- 6({n}) [{p['para_id']}]  points={len(p['points'])} ---")
        print(p["text"][:600])

    # The unnumbered-article fallback: Art 3 (68 defs), 16 (12 obligations), 4 (0).
    print("\n=== unnumbered-article fallback ===")
    for num in (3, 16, 4):
        a = next(x for x in articles if x["number"] == num)
        pts = sum(len(p["points"]) for p in a["paragraphs"])
        print(f"  Art {num:>3} ({a['title'][:40]}): paras={len(a['paragraphs'])} points={pts}")

    # Piece 3: recitals + annexes via the full-document parser.
    doc = parse_document(HTML_PATH.read_text(encoding="utf-8"))
    print("\n=== full document ===")
    print(f"  recitals: {len(doc['recitals'])} (expected ~180)")
    print(f"  articles: {len(doc['articles'])} (expected 113)")
    print(f"  annexes:  {len(doc['annexes'])} (expected 13)")

    r1 = doc["recitals"][0]
    print(f"\nrecital {r1['number']} [{r1['type']}]: {r1['text'][:90]}")

    print("\n=== annexes ===")
    for a in doc["annexes"]:
        print(f"  {a['label']:>10} ({a['roman']}): items={len(a['items'])}  {a['title'][:45]}")

    a3 = next(a for a in doc["annexes"] if a["roman"] == "III")
    print(f"\nAnnex III — {a3['title']}")
    print(f"  first 3 items: {[it['label'] for it in a3['items'][:3]]}")
    print("  text head:", a3["text"][:140])

    # Serialize the structured corpus. ensure_ascii=False keeps EU-law unicode
    # (’ “ ” etc.) human-readable in the JSON instead of \u-escaped.
    out = Path("data/processed/ai_act.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out}  ({out.stat().st_size / 1024:.0f} KB)")
