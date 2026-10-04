"""Blocks unsupported claims: numbers, credentials, superlatives, and leftover placeholders."""
from __future__ import annotations

import json
import re

from ..facts import years_in_business
from ..models import PageDraft, QAIssue

CLAIM_RE = re.compile(
    r"(\d[\d,\.]*)\+?\s*(%|kwp|kw|mwp|mw|years?|yrs|projects?|installations?|clients?|customers?|homes|villas|aed|pkr|usd)",
    re.I,
)
PRICE_RE = re.compile(r"(aed|usd|pkr|\$)\s*(\d[\d,\.]*)", re.I)
NEEDS_RE = re.compile(r"\[NEEDS CLIENT FACT[^\]]*\]", re.I)
SUPERLATIVES = re.compile(
    r"(\bbest\s+(?:in|solar|company|provider|price|prices|quality|installer|choice)\b|#1|\bnumber one\b|\bno\.?\s?1\b"
    r"|\bleading\s+(?:provider|company|supplier|installer|contractor)\b|\btop-rated\b|\bcheapest\b|\blowest price\b|\bguarantee[sd]?\b|\bunbeatable\b)",
    re.I,
)
CREDENTIALS = {
    r"\bcertified\b|\bcertification\b|\baccredited\b|\biso\s?\d{3,5}\b": "certifications",
    r"\blicen[sc]ed\b": "licences",
    r"\baward(?:-winning|s)?\b": "awards",
}


def _norm(s: str) -> str:
    return re.sub(r"[\s,]", "", s.lower())


def facts_blob(facts: dict) -> str:
    return _norm(json.dumps(facts, ensure_ascii=False))


def find_needs_facts(text: str) -> list[str]:
    return NEEDS_RE.findall(text or "")


def unsupported_claims(text: str, facts: dict) -> list[str]:
    blob = facts_blob(facts)
    years = years_in_business(facts)
    problems: list[str] = []
    for m in CLAIM_RE.finditer(text):
        num, unit = m.group(1).rstrip(".,"), m.group(2).lower()
        token = _norm(num + unit)
        if token in blob:
            continue
        if unit in ("year", "years", "yrs") and years is not None:
            try:
                if float(num) <= years:
                    continue
            except ValueError:
                pass
        problems.append(f'unsupported number claim "{m.group(0).strip()}"')
    for m in PRICE_RE.finditer(text):
        token = _norm(m.group(1) + m.group(2))
        if token not in blob and _norm(m.group(2) + m.group(1)) not in blob:
            problems.append(f'unsupported price claim "{m.group(0).strip()}"')
    for pat, key in CREDENTIALS.items():
        hit = re.search(pat, text, re.I)
        if hit and not (facts.get("proof") or {}).get(key):
            problems.append(f'"{hit.group(0)}" claimed but proof.{key} is empty in facts.yaml')
    for m in SUPERLATIVES.finditer(text):
        word = m.group(0)
        if _norm(word) not in blob:
            problems.append(f'unsupported superlative/guarantee "{word}"')
    return sorted(set(problems))


def draft_text(d: PageDraft) -> str:
    parts = [d.intro] + [f"{s.get('h2', '')} {s.get('body', '')}" for s in d.sections] + [f"{f.get('q', '')} {f.get('a', '')}" for f in d.faq]
    return "\n".join(parts)


def check_draft(d: PageDraft, facts: dict) -> list[QAIssue]:
    text = draft_text(d) + "\n" + d.title + "\n" + d.meta_description + "\n" + d.h1
    out = [QAIssue("error", "needs_client_fact", d.slug, f"Placeholder not filled: {n}") for n in find_needs_facts(text)]
    out += [QAIssue("error", "unsupported_claim", d.slug, p) for p in unsupported_claims(text, facts)]
    return out
