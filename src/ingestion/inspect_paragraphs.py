"""
Module 1 probe — look INSIDE one article (Article 6) to see exactly how
paragraphs and lettered points (a)(b)(c) are marked up, before we write the
piece-2 parser. Measure, don't guess.

Run:  uv run python src/ingestion/inspect_paragraphs.py
"""

import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def norm(s: str) -> str:
    return s.replace("\xa0", " ").strip()


soup = BeautifulSoup(
    Path("data/raw/ai_act_32024R1689.html").read_text(encoding="utf-8"), "lxml"
)

container = soup.find(id="art_6")

# 1. What are the DIRECT children of the article container, and their ids?
print("=== direct children of div#art_6 ===")
for child in container.find_all(recursive=False):
    cls = child.get("class")
    cid = child.get("id")
    print(f"  <{child.name}> id={cid!r} class={cls}")

# 2. The paragraph divs: id pattern, the oj-normal text, and any table.
print("\n=== paragraph-level divs (id like 006.00x) ===")
for div in container.find_all("div", id=True):
    if div.get("id", "").startswith("006."):
        normals = div.find_all("p", class_="oj-normal", recursive=False)
        tables = div.find_all("table", recursive=False)
        first_text = norm(normals[0].get_text()) if normals else "(no oj-normal)"
        print(f"  id={div['id']!r}  oj-normal={len(normals)}  tables={len(tables)}")
        print(f"     text: {first_text[:90]!r}")

# 3. Inside the FIRST table we find: how are the (a)/(b) cells laid out?
print("\n=== first points-table cell layout ===")
table = container.find("table")
if table:
    for i, row in enumerate(table.find_all("tr")[:3]):
        cells = row.find_all(["td", "th"])
        rendered = [norm(c.get_text(" "))[:60] for c in cells]
        print(f"  row {i}: {len(cells)} cells -> {rendered}")
else:
    print("  (no table in Article 6)")
