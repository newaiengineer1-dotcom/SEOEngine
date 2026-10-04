"""QA gate. Errors block publishing; warnings are shown to the reviewer."""
from __future__ import annotations

import json
import re
from collections import Counter
from html import unescape

from ..constants import STOPWORDS
from ..models import QAIssue, QAReport
from . import facts_guard
from .text import jaccard, shingles, soup_of, visible_text, words


def _main_text(soup) -> str:
    node = soup.find("main") or soup.body or soup
    return visible_text(node)


def keyword_stuffing(text: str, threshold: float = 0.045, min_words: int = 150) -> list[tuple[str, float]]:
    ws = words(text)
    if len(ws) < min_words:
        return []
    c = Counter(w for w in ws if len(w) >= 4 and w not in STOPWORDS)
    return [(w, n / len(ws)) for w, n in c.most_common(5) if n / len(ws) > threshold]


def qa_page(path: str, html: str, *, generated: bool, facts: dict | None, all_paths: set[str]) -> list[QAIssue]:
    out: list[QAIssue] = []
    lvl = "error" if generated else "warn"
    soup = soup_of(html)
    title = soup.title.get_text(strip=True) if soup.title else ""
    md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    meta = (md.get("content") or "").strip() if md else ""
    h1s = soup.find_all("h1")

    if not title:
        out.append(QAIssue(lvl, "no_title", path, "Missing <title>."))
    elif len(title) > 65 or len(title) < 20:
        out.append(QAIssue("warn", "title_length", path, f"Title is {len(title)} chars (target 30-60)."))
    if not meta:
        out.append(QAIssue(lvl, "no_meta", path, "Missing meta description."))
    elif not (70 <= len(meta) <= 165):
        out.append(QAIssue("warn", "meta_length", path, f"Meta description is {len(meta)} chars (target 120-155)."))
    if len(h1s) != 1:
        out.append(QAIssue(lvl, "h1_count", path, f"Expected exactly 1 H1, found {len(h1s)}."))
    if soup.find("html") is None or soup.find("head") is None or soup.find("body") is None:
        out.append(QAIssue(lvl, "structure", path, "Missing <html>, <head> or <body>."))
    missing_alt = [i for i in soup.find_all("img") if not i.has_attr("alt")]
    if missing_alt:
        out.append(QAIssue(lvl, "img_alt", path, f"{len(missing_alt)} image(s) without alt attribute."))
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            json.loads(unescape(s.string or ""))
        except ValueError:
            out.append(QAIssue("error", "bad_jsonld", path, "Invalid JSON-LD block."))

    text = _main_text(soup)
    for word, share in keyword_stuffing(text):
        out.append(QAIssue("error", "keyword_stuffing", path, f'"{word}" makes up {share:.1%} of the words; rewrite naturally.'))

    for needle in facts_guard.find_needs_facts(text + " " + title + " " + meta):
        out.append(QAIssue("error", "needs_client_fact", path, f"Placeholder not filled: {needle}"))
    if generated and facts:
        for p in facts_guard.unsupported_claims(text + " " + title + " " + meta, facts):
            out.append(QAIssue("error", "unsupported_claim", path, p))

    for a in soup.find_all("a", href=True):
        h = a["href"].split("#")[0].split("?")[0].strip()
        if not h or re.match(r"^(https?:|mailto:|tel:|javascript:|//)", h, re.I):
            continue
        if re.search(r"\.[a-z0-9]{2,5}$", h, re.I) and not h.lower().endswith((".html", ".htm")):
            continue  # asset link; cannot verify binaries
        rel = h.lstrip("/") if h.startswith("/") else (path.rsplit("/", 1)[0] + "/" + h if "/" in path else h)
        rel = re.sub(r"/{2,}", "/", rel)
        cands = {rel, rel.rstrip("/") + "/index.html", rel + ".html", rel + "/index.html"}
        if rel in ("", "/"):
            cands.add("index.html")
        if not (cands & all_paths):
            out.append(QAIssue("warn", "broken_internal_link", path, f"Link target not found in site files: {a['href']}"))
    return out


def qa_site(files: dict[str, str], *, generated: set[str], all_paths: set[str], facts: dict | None) -> QAReport:
    rep = QAReport()
    shingle_map: dict[str, set[str]] = {}
    for path, html in files.items():
        if not path.lower().endswith((".html", ".htm")):
            continue
        rep.issues.extend(qa_page(path, html, generated=path in generated, facts=facts, all_paths=all_paths))
        if path in generated:
            shingle_map[path] = shingles(words(_main_text(soup_of(html))))
    paths = sorted(shingle_map)
    for i, a in enumerate(paths):
        for b in paths[i + 1 :]:
            sim = jaccard(shingle_map[a], shingle_map[b])
            if sim >= 0.5:
                rep.issues.append(QAIssue("error", "duplicate_content", a, f"{sim:.0%} similar to {b}; every page needs unique copy."))
    return rep
