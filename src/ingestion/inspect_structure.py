"""
Module 1 — discover the structure of the EUR-Lex AI Act HTML.

We never guess a site's markup. We measure it: which CSS classes mark
articles, paragraphs, recitals, annexes? And are cross-references already
hyperlinked (free graph edges)? Run this, read the output, and we write
parsers against the REAL tags instead of assumptions.

Run:  uv run python src/ingestion/inspect_structure.py
"""

from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

HTML_PATH = Path("data/raw/ai_act_32024R1689.html")

# "lxml" is the fast C parser we installed; it builds the DOM tree from raw bytes.
soup = BeautifulSoup(HTML_PATH.read_text(encoding="utf-8"), "lxml")

# 1. Basic shape of the document.
print("=== document ===")
print("title:", soup.title.get_text(strip=True) if soup.title else "(none)")
print("total elements:", len(soup.find_all(True)))

# 2. The structural vocabulary: which CSS classes appear, and how often.
class_counter = Counter()
for el in soup.find_all(True):
    for cls in el.get("class", []):
        class_counter[cls] += 1
print("\n=== top 15 CSS classes ===")
for cls, n in class_counter.most_common(15):
    print(f"  {n:5d}  {cls}")

# 3. Confirm oj-ti-art marks "Article N" headings.
art_titles = soup.find_all(class_="oj-ti-art")
print(f"\n=== oj-ti-art elements: {len(art_titles)} ===")
for el in art_titles[:5]:
    print("   ", el.name, "|", repr(el.get_text(" ", strip=True)))

# 4. Show the full markup of ONE article (Article 6).
#    .replace('\xa0',' ') normalises the non-breaking space that broke the
#    exact-match earlier — a classic HTML parsing gotcha.
def norm(s: str) -> str:
    return s.replace("\xa0", " ").strip()

art6 = next((el for el in art_titles if norm(el.get_text()) == "Article 6"), None)
print("\n=== Article 6 subdivision ===")
if art6:
    sub = art6.find_parent(class_="eli-subdivision")
    if sub:
        print("subdivision id:", sub.get("id"))
        print(sub.prettify()[:1400])
    else:
        print("(no eli-subdivision parent)")
        print(art6.parent.prettify()[:900])
else:
    print("headings seen:", [norm(el.get_text()) for el in art_titles[:8]])

# 5. Are cross-references hyperlinked? (the reason we chose HTML)
links = soup.find_all("a", href=True)
internal = [a for a in links if a["href"].startswith("#")]
print(f"\n=== hyperlinks: {len(links)} total, {len(internal)} internal (#...) ===")
for a in internal[:8]:
    print("   ", repr(norm(a.get_text())[:45]), "->", a["href"])
