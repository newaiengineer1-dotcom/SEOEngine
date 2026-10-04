"""Page plan and keyword helpers (deterministic baseline; AI can refine on top)."""
from __future__ import annotations

from .facts import load_plan_yaml
from .models import PageSpec


def default_page_plan() -> list[PageSpec]:
    specs = []
    for d in load_plan_yaml():
        specs.append(
            PageSpec(
                slug=d["slug"],
                market=d.get("market", "GLOBAL"),
                service=d.get("service", ""),
                primary_keyword=d.get("primary_keyword", ""),
                secondary_keywords=list(d.get("secondary_keywords", [])),
                title=d.get("title", ""),
                meta_description=d.get("meta_description", ""),
                h1=d.get("h1", ""),
                parent=d.get("parent", ""),
                enabled=d.get("enabled", True),
            )
        )
    return specs


def plan_from_rows(rows: list[dict]) -> list[PageSpec]:
    out = []
    for r in rows:
        if not r.get("slug"):
            continue
        sec = r.get("secondary_keywords", [])
        if isinstance(sec, str):
            sec = [s.strip() for s in sec.split(",") if s.strip()]
        out.append(
            PageSpec(
                slug=str(r["slug"]).strip(),
                market=str(r.get("market", "GLOBAL")),
                service=str(r.get("service", "")),
                primary_keyword=str(r.get("primary_keyword", "")),
                secondary_keywords=sec,
                title=str(r.get("title", "")),
                meta_description=str(r.get("meta_description", "")),
                h1=str(r.get("h1", "")),
                parent=str(r.get("parent", "")),
                enabled=bool(r.get("enabled", True)),
            )
        )
    return out


def match_queries_to_pages(rows: list[dict], plan: list[PageSpec]) -> list[dict]:
    """Attach real Search Console queries to the page whose keywords overlap the most."""
    out = []
    for r in rows:
        q = set(r["query"].lower().split())
        best, score = None, 0
        for p in plan:
            kws = {w for k in [p.primary_keyword] + p.secondary_keywords for w in k.lower().split()}
            s = len(q & kws)
            if s > score:
                best, score = p, s
        out.append({**r, "best_page": best.slug if best and score >= 2 else ""})
    return out
