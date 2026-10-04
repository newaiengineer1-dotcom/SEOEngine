"""Text helpers."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def visible_text(html_or_soup) -> str:
    html = str(html_or_soup)
    clone = BeautifulSoup(html, "html.parser")
    for t in clone(["script", "style", "noscript", "template"]):
        t.decompose()
    return re.sub(r"\s+", " ", clone.get_text(" ")).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())


def shingles(ws: list[str], n: int = 6) -> set[str]:
    return {" ".join(ws[i : i + n]) for i in range(max(0, len(ws) - n + 1))}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
