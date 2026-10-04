"""Deterministic, idempotent HTML fixes. Every fix reports a Change with a risk level.

Low-risk fixes never change meaning (typos, alt text, lazy-loading, canonical...).
High-risk fixes change copy, structure or add widgets (title/meta/H1, schema, contact bar, link sections).
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString
from bs4.dammit import EntitySubstitution
from bs4.formatter import HTMLFormatter

from ..constants import LOW_RISK_KINDS, MANAGED_ATTR, TYPO_RE
from ..models import Change
from .text import soup_of

STYLE_ID = "kg-contact-bar-style"
BAR_ID = "kg-contact-bar"
LINKS_ID = "kg-service-links"

BAR_CSS = (
    "#kg-contact-bar{position:fixed;left:0;right:0;bottom:0;z-index:9999;display:flex;background:#0b3d2e}"
    "#kg-contact-bar a{flex:1;text-align:center;padding:12px 8px;color:#fff;font:600 15px/1.2 system-ui,sans-serif;"
    "text-decoration:none;background:#0b8043}"
    "#kg-contact-bar a+a{border-left:1px solid rgba(255,255,255,.35)}"
    "body{padding-bottom:56px}"
)


class _KeepOrder(HTMLFormatter):
    """bs4 sorts attributes alphabetically by default; keep the author's order so diffs stay small."""

    def attributes(self, tag):
        return list(tag.attrs.items())


_HTML5 = _KeepOrder(entity_substitution=EntitySubstitution.substitute_xml, void_element_close_prefix="")
_XHTML = _KeepOrder(entity_substitution=EntitySubstitution.substitute_xml, void_element_close_prefix="/")


def render(soup: BeautifulSoup, xhtml: bool = False) -> str:
    return soup.decode(formatter=_XHTML if xhtml else _HTML5)


def canonical_url(path: str, base: str) -> str:
    base = base.rstrip("/")
    p = path.lstrip("/")
    if p in ("", "index.html", "index.htm"):
        return base + "/"
    if p.endswith("/index.html"):
        return f"{base}/{p[: -len('index.html')]}"
    return f"{base}/{p}"


def _ensure_head(soup: BeautifulSoup):
    if soup.head is None and soup.html is not None:
        soup.html.insert(0, soup.new_tag("head"))
    return soup.head


# ------------------------------------------------------------------ low-risk fixes
def fix_typos(soup: BeautifulSoup) -> int:
    count = 0
    for node in list(soup.find_all(string=True)):
        if type(node) is not NavigableString:  # skips comments, scripts, styles, doctype
            continue
        new = str(node)
        for pat, rep in TYPO_RE:
            new, n = pat.subn(rep, new)
            count += n
        if new != str(node):
            node.replace_with(NavigableString(new))
    return count


def _humanize(stem: str) -> str:
    s = re.sub(r"\(\d+\)", " ", stem)
    s = re.sub(r"icons8", " ", s, flags=re.I)
    s = re.sub(r"[-_]+", " ", s)
    s = re.sub(r"\b\d+\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fix_alt_text(soup: BeautifulSoup, brand: str, rules: dict | None) -> tuple[int, int]:
    rules = rules or {}
    exact = {k.lower(): v for k, v in (rules.get("exact") or {}).items()}
    contains = {k.lower(): v for k, v in (rules.get("contains") or {}).items()}
    named = decorative = 0
    for img in soup.find_all("img"):
        if img.has_attr("alt"):
            continue
        src = unquote(img.get("src", ""))
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", src.rsplit("/", 1)[-1]).lower()
        alt = exact.get(stem)
        if alt is None:
            for key, val in contains.items():
                if key in stem:
                    alt = val
                    break
        if alt is None:
            h = _humanize(stem)
            generic = re.fullmatch(r"(bg|img|image|slide|banner|hero|photo|pic)\s*\d*", h) or len(re.sub(r"[^a-z]", "", h)) < 4
            alt = None if generic else h.title()
        if alt is None:
            img["alt"] = ""
            decorative += 1
        else:
            img["alt"] = alt.replace("{brand}", brand)
            named += 1
    return named, decorative


def add_lazy_loading(soup: BeautifulSoup) -> int:
    n = 0
    for i, img in enumerate(soup.find_all("img")):
        if i == 0 or img.has_attr("loading") or img.has_attr("fetchpriority"):
            continue
        img["loading"] = "lazy"
        img["decoding"] = "async"
        n += 1
    return n


def ensure_viewport(soup: BeautifulSoup) -> bool:
    if soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}):
        return False
    head = _ensure_head(soup)
    if head is None:
        return False
    tag = soup.new_tag("meta", attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"})
    head.insert(0, tag)
    return True


def ensure_lang(soup: BeautifulSoup, lang: str = "en") -> bool:
    if soup.html is not None and not soup.html.get("lang"):
        soup.html["lang"] = lang
        return True
    return False


def fix_copyright(soup: BeautifulSoup, year: int) -> int:
    pat = re.compile(r"(©\s*(?:\d{4}\s*[-–]\s*)?)(\d{4})")
    n = 0
    for node in list(soup.find_all(string=True)):
        if type(node) is not NavigableString:
            continue
        s = str(node)

        def _sub(m):
            nonlocal n
            if int(m.group(2)) < year:
                n += 1
                return f"{m.group(1)}{year}"
            return m.group(0)

        new = pat.sub(_sub, s)
        if new != s:
            node.replace_with(NavigableString(new))
    return n


def ensure_canonical(soup: BeautifulSoup, url: str) -> bool:
    if soup.find("link", attrs={"rel": lambda v: v and "canonical" in (v if isinstance(v, list) else [v])}):
        return False
    head = _ensure_head(soup)
    if head is None:
        return False
    head.append(soup.new_tag("link", attrs={"rel": "canonical", "href": url}))
    return True


def ensure_open_graph(soup: BeautifulSoup, title: str, description: str, url: str) -> bool:
    if soup.find("meta", attrs={"property": re.compile(r"^og:", re.I)}):
        return False
    head = _ensure_head(soup)
    if head is None:
        return False
    for prop, val in (("og:type", "website"), ("og:title", title), ("og:description", description), ("og:url", url)):
        if val:
            head.append(soup.new_tag("meta", attrs={"property": prop, "content": val}))
    return True


# ------------------------------------------------------------------ high-risk fixes
def set_title(soup: BeautifulSoup, title: str) -> bool:
    head = _ensure_head(soup)
    if head is None:
        return False
    if soup.title is None:
        t = soup.new_tag("title")
        head.insert(0, t)
    if soup.title.get_text(strip=True) == title:
        return False
    soup.title.string = title
    return True


def set_meta_description(soup: BeautifulSoup, text: str) -> bool:
    head = _ensure_head(soup)
    if head is None:
        return False
    tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if tag is None:
        head.append(soup.new_tag("meta", attrs={"name": "description", "content": text}))
        return True
    if (tag.get("content") or "").strip() == text:
        return False
    tag["content"] = text
    return True


def set_h1(soup: BeautifulSoup, text: str) -> bool:
    h1 = soup.find("h1")
    if h1 is None or h1.get_text(" ", strip=True) == text:
        return False
    h1.string = text
    return True


def inject_jsonld(soup: BeautifulSoup, data, key: str) -> bool:
    holder = soup.head or soup.body
    if holder is None:
        return False
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    existing = soup.find("script", attrs={"data-managed": MANAGED_ATTR, "data-key": key})
    if existing is not None:
        if (existing.string or "") == payload:
            return False
        existing.string = payload
        return True
    tag = soup.new_tag("script", attrs={"type": "application/ld+json", "data-managed": MANAGED_ATTR, "data-key": key})
    tag.string = payload
    holder.append(tag)
    return True


def inject_theme(soup: BeautifulSoup, href: str) -> bool:
    if soup.body is None or soup.head is None:
        return False
    changed = False
    classes = list(soup.body.get("class", []))
    if "kg-premium" not in classes:
        soup.body["class"] = classes + ["kg-premium"]
        changed = True
    link = soup.find("link", attrs={"data-managed": MANAGED_ATTR, "data-key": "premium-theme"})
    if link is None:
        soup.head.append(soup.new_tag("link", attrs={"rel": "stylesheet", "href": href, "data-managed": MANAGED_ATTR, "data-key": "premium-theme"}))
        changed = True
    elif link.get("href") != href:
        link["href"] = href
        changed = True
    return changed


def inject_contact_bar(soup: BeautifulSoup, items: list[tuple[str, str]]) -> bool:
    if soup.body is None or not items:
        return False
    from html import escape

    links = "".join(f'<a href="{escape(h, quote=True)}">{escape(l)}</a>' for l, h in items)
    new_bar = f'<div id="{BAR_ID}" data-managed="{MANAGED_ATTR}">{links}</div>'
    old = soup.find(id=BAR_ID)
    if old is not None and str(old) == str(BeautifulSoup(new_bar, "html.parser")):
        return False
    if old is not None:
        old.decompose()
    soup.body.append(BeautifulSoup(new_bar, "html.parser"))
    if soup.find("style", id=STYLE_ID) is None:
        style = soup.new_tag("style", attrs={"id": STYLE_ID, "data-managed": MANAGED_ATTR})
        style.string = BAR_CSS
        (soup.head or soup.body).append(style)
    return True


def inject_service_links(soup: BeautifulSoup, links: list[tuple[str, str]], heading: str = "Our Solar & Energy Services") -> bool:
    if soup.body is None or not links:
        return False
    from html import escape

    items = "".join(f'<li><a href="{escape(h, quote=True)}">{escape(l)}</a></li>' for l, h in links)
    html = f'<section id="{LINKS_ID}" data-managed="{MANAGED_ATTR}"><h2>{escape(heading)}</h2><ul>{items}</ul></section>'
    new_node = BeautifulSoup(html, "html.parser")
    old = soup.find(id=LINKS_ID)
    if old is not None and str(old) == str(new_node):
        return False
    if old is not None:
        old.decompose()
    footer = soup.find("footer")
    bar = soup.find(id=BAR_ID)
    if footer is not None:
        footer.insert_before(new_node)
    elif bar is not None:
        bar.insert_before(new_node)
    else:
        soup.body.append(new_node)
    return True


# ------------------------------------------------------------------ orchestrator
def _chg(path: str, kind: str, description: str) -> Change:
    return Change(path=path, kind=kind, risk="low" if kind in LOW_RISK_KINDS else "high", description=description)


def apply_page_fixes(
    html: str,
    path: str,
    *,
    year: int,
    brand: str = "Kunergy",
    alt_rules: dict | None = None,
    canonical_base: str | None = None,
    low_risk: bool = True,
    title: str | None = None,
    meta_description: str | None = None,
    h1: str | None = None,
    jsonld: list[tuple[str, dict]] | None = None,
    contact_items: list[tuple[str, str]] | None = None,
    service_links: list[tuple[str, str]] | None = None,
    theme_href: str | None = None,
) -> tuple[str, list[Change]]:
    soup = soup_of(html)
    ch: list[Change] = []

    if low_risk:
        n = fix_typos(soup)
        if n:
            ch.append(_chg(path, "typo_fix", f"Corrected {n} known typo(s) (e.g. Commerical, Kunegy, Electrical Vehicles)."))
        named, deco = fix_alt_text(soup, brand, alt_rules)
        if named or deco:
            ch.append(_chg(path, "alt_text", f"Added alt text to {named} image(s); marked {deco} generic image(s) as decorative (alt='')."))
        n = add_lazy_loading(soup)
        if n:
            ch.append(_chg(path, "lazy_loading", f"Added lazy loading to {n} image(s)."))
        if ensure_viewport(soup):
            ch.append(_chg(path, "viewport", "Added mobile viewport meta tag."))
        if ensure_lang(soup):
            ch.append(_chg(path, "lang", 'Added lang="en" to <html>.'))
        n = fix_copyright(soup, year)
        if n:
            ch.append(_chg(path, "copyright_year", f"Updated footer copyright year to {year}."))
        if canonical_base and ensure_canonical(soup, canonical_url(path, canonical_base)):
            ch.append(_chg(path, "canonical", "Added canonical link."))

    if title and set_title(soup, title):
        ch.append(_chg(path, "title", f'Set <title> to "{title}".'))
    if meta_description and set_meta_description(soup, meta_description):
        ch.append(_chg(path, "meta_description", "Set meta description."))
    if h1 and set_h1(soup, h1):
        ch.append(_chg(path, "h1", f'Set H1 to "{h1}".'))
    if low_risk and canonical_base:
        t = soup.title.get_text(strip=True) if soup.title else ""
        md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if ensure_open_graph(soup, t, (md.get("content") if md else "") or "", canonical_url(path, canonical_base)):
            ch.append(_chg(path, "open_graph", "Added Open Graph tags."))
    for key, data in jsonld or []:
        if inject_jsonld(soup, data, key):
            ch.append(_chg(path, "schema", f"Added/updated JSON-LD schema ({key})."))
    if contact_items and inject_contact_bar(soup, contact_items):
        ch.append(_chg(path, "contact_bar", "Added sticky call / WhatsApp / quote bar."))
    if service_links and inject_service_links(soup, service_links):
        ch.append(_chg(path, "internal_links", "Added crawlable links to the new service pages."))

    if theme_href and inject_theme(soup, theme_href):
        ch.append(_chg(path, "theme", "Linked the premium theme stylesheet (body.kg-premium)."))

    if not ch:
        return html, []
    xhtml = bool(re.search(r"<(?:meta|img|link|br|input)\b[^>]*/>", html))  # mimic the file's existing style
    return render(soup, xhtml), ch
