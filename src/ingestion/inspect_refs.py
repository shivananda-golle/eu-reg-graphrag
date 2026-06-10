"""
Module 1 probe — are the AI Act's internal cross-references hyperlinked,
or are they plain prose we must extract ourselves in Module 2?

Run:  uv run python src/ingestion/inspect_refs.py
"""

import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

soup = BeautifulSoup(
    Path("data/raw/ai_act_32024R1689.html").read_text(encoding="utf-8"), "lxml"
)

internal = [a for a in soup.find_all("a", href=True) if a["href"].startswith("#")]


def prefix(href: str) -> str:
    """Leading alphabetic part of the target id, e.g. '#ntr1-...' -> 'ntr'."""
    head = ""
    for ch in href.lstrip("#"):
        if ch.isalpha():
            head += ch
        else:
            break
    return head or "(other)"


print("internal link target prefixes:", dict(Counter(prefix(a["href"]) for a in internal)))

# Do any links actually carry article/annex cross-reference TEXT?
ref_links = [
    a for a in internal
    if re.search(r"article|annex", a.get_text(" ", strip=True), re.I)
]
print("links whose visible text mentions article/annex:", len(ref_links))
for a in ref_links[:10]:
    print("   ", repr(a.get_text(" ", strip=True)[:40]), "->", a["href"])

# Counter-check: how many references exist as PLAIN PROSE in the body text?
text = soup.get_text(" ")
print("\nplain-text mentions of 'Annex':  ", len(re.findall(r"\bAnnex\b", text)))
print("plain-text mentions of 'Article':", len(re.findall(r"\bArticle\s", text)))
