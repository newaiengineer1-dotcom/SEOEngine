"""Shared constants."""
from __future__ import annotations

import re

# (regex, replacement). Case-sensitive on purpose. Typos observed on kunergy.com.
TYPO_MAP: list[tuple[str, str]] = [
    (r"\bCommerical\b", "Commercial"),
    (r"\bcommerical\b", "commercial"),
    (r"\bKunegy\b", "Kunergy"),
    (r"\bElectrical Vehicles\b", "Electric Vehicles"),
    (r"\bElectrical Vehicle\b", "Electric Vehicle"),
]
TYPO_RE = [(re.compile(p), r) for p, r in TYPO_MAP]

# Change kinds that never alter meaning or claims. Everything else needs human review.
LOW_RISK_KINDS = {
    "typo_fix",
    "alt_text",
    "lazy_loading",
    "viewport",
    "lang",
    "copyright_year",
    "canonical",
    "open_graph",
    "sitemap",
    "robots",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

STOPWORDS = set(
    """a about above after again all also an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers him his how i if in into is it its just me more most my no nor not now of
    off on once only or other our ours out over own same she should so some such than that the their
    theirs them then there these they this those through to too under until up very was we were what
    when where which while who whom why will with would you your yours""".split()
)

TEXT_EXT = {".html", ".htm", ".xml", ".txt", ".css", ".js", ".json", ".md", ".webmanifest"}
MANAGED_ATTR = "kunergy-autopilot"
