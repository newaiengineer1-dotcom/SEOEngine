"""sitemap.xml and robots.txt builders."""
from __future__ import annotations

from datetime import date
from html import escape

from .html_patcher import canonical_url


def build_sitemap(base: str, html_paths: list[str], lastmod: date | None = None) -> str:
    lm = (lastmod or date.today()).isoformat()
    urls = sorted({canonical_url(p, base) for p in html_paths})
    body = "\n".join(f"  <url><loc>{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


def build_robots(base: str) -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {base.rstrip('/')}/sitemap.xml\n"


def ensure_robots_sitemap(existing: str, base: str) -> str:
    if "sitemap:" in existing.lower():
        return existing
    return existing.rstrip("\n") + f"\n\nSitemap: {base.rstrip('/')}/sitemap.xml\n"
