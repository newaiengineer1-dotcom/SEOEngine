"""Render a PageDraft to a complete, semantic HTML page (all text is HTML-escaped)."""
from __future__ import annotations

import json
import re
from datetime import date
from html import escape

from ..models import PageDraft
from . import schema_builder as sb
from .html_patcher import canonical_url
from .text import soup_of

CSS = """
:root{--g:#0b6b3a;--d:#0b3d2e;--t:#1d2b24;--m:#5b6b63;--bg:#f6faf7}
*{box-sizing:border-box}body{margin:0;font:17px/1.65 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--t);background:#fff}
header.kg{background:var(--d);color:#fff;padding:14px 20px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}
header.kg a{color:#fff;text-decoration:none;font-weight:600}header.kg nav a{margin-left:16px;font-weight:500}
main{max-width:860px;margin:0 auto;padding:28px 20px 80px}h1{font-size:2rem;line-height:1.25;color:var(--d)}h2{margin-top:2rem;color:var(--d)}
.crumbs{font-size:.9rem;color:var(--m)}.crumbs a{color:var(--g)}
.cta{background:var(--bg);border:1px solid #cfe5d6;border-radius:12px;padding:20px;margin:2rem 0}
.btn{display:inline-block;background:var(--g);color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600}
details{border-bottom:1px solid #e3ece6;padding:10px 0}summary{cursor:pointer;font-weight:600}
footer.kg{background:var(--bg);padding:24px 20px;font-size:.92rem;color:var(--m)}footer.kg a{color:var(--g)}
"""


def extract_head_assets(home_html: str | None) -> str:
    """Reuse the home page's stylesheet/icon links so new pages match the existing design."""
    if not home_html:
        return ""
    soup = soup_of(home_html)
    out = []
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])) if isinstance(link.get("rel"), list) else str(link.get("rel", ""))
        if re.search(r"stylesheet|icon", rel, re.I) and link.get("href"):
            out.append(str(link))
    return "\n".join(out)


def _paras(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f"<p>{escape(p)}</p>" for p in parts)


def render_page(draft: PageDraft, facts: dict, *, head_assets: str = "", nav_links: list[tuple[str, str]] | None = None, hub_title: str = "") -> str:
    base = facts["company"]["website"].rstrip("/")
    brand = facts["company"]["brand"]
    path = draft.slug.rstrip("/") + "/index.html" if draft.slug.endswith("/") else draft.slug
    canon = canonical_url(path, base)

    crumbs = [(brand, base + "/")]
    if draft.parent:
        crumbs.append((hub_title or draft.parent.strip("/").title(), f"{base}/{draft.parent}"))
    crumbs.append((draft.h1, canon))
    crumb_html = " / ".join(f'<a href="{escape(u, quote=True)}">{escape(n)}</a>' for n, u in crumbs[:-1]) + f" / {escape(crumbs[-1][0])}"

    area = {"UAE": "United Arab Emirates", "PK": "Pakistan"}.get(draft.market)
    schemas = [sb.service(draft.h1, draft.meta_description, brand, area, canon), sb.breadcrumb(crumbs)]
    faq = sb.faq_page(draft.faq)
    if faq:
        schemas.append(faq)
    ld = "\n".join(f'<script type="application/ld+json" data-managed="kunergy-autopilot">{json.dumps(s, ensure_ascii=False)}</script>' for s in schemas)

    sections = "".join(f"<section><h2>{escape(s.get('h2', ''))}</h2>{_paras(s.get('body', ''))}</section>" for s in draft.sections)
    faq_html = ""
    if draft.faq:
        faq_html = "<section><h2>Frequently asked questions</h2>" + "".join(
            f"<details><summary>{escape(f['q'])}</summary><p>{escape(f['a'])}</p></details>" for f in draft.faq
        ) + "</section>"

    nav = "".join(f'<a href="{escape(h, quote=True)}">{escape(l)}</a>' for l, h in (nav_links or [("Home", "/")]))
    ent = [e for e in facts.get("entities", [])]
    foot = " &nbsp;|&nbsp; ".join(
        f"<strong>{escape(e['legal_name'])}</strong>, {escape(e['street'])}, {escape(e['locality'])}, {escape(e['country'])}. "
        f'<a href="tel:{escape(sb.clean_phone(e["phone"]) or "", quote=True)}">{escape(e["phone"])}</a>'
        for e in ent
    )
    head = head_assets or ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(draft.title)}</title>
<meta name="description" content="{escape(draft.meta_description, quote=True)}">
<link rel="canonical" href="{escape(canon, quote=True)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{escape(draft.title, quote=True)}">
<meta property="og:description" content="{escape(draft.meta_description, quote=True)}">
<meta property="og:url" content="{escape(canon, quote=True)}">
{head}
<style>{CSS}</style>
{ld}
</head>
<body>
<header class="kg"><a href="/">{escape(brand)}</a><nav>{nav}</nav></header>
<main>
<p class="crumbs">{crumb_html}</p>
<h1>{escape(draft.h1)}</h1>
{_paras(draft.intro)}
{sections}
{faq_html}
<div class="cta"><strong>Ready to talk about your project?</strong><p>Tell us about your site and we will get back to you.</p><a class="btn" href="/#contact">{escape(draft.cta_text)}</a></div>
</main>
<footer class="kg">{foot}<p>&copy; {date.today().year} {escape(brand)}. All rights reserved.</p></footer>
</body>
</html>
"""
