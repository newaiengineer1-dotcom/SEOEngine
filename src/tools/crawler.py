"""Polite same-site crawler + rule-based SEO audit (no LLM needed)."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from ..constants import SEVERITY_ORDER, TYPO_RE
from ..models import AuditReport, Issue, PageAudit
from .text import soup_of, visible_text

UA = "KunergySEOAutopilot/1.0 (+https://www.kunergy.com)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp4", ".css", ".js", ".ico", ".xml", ".txt")


def _host(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.")


def normalize_url(u: str) -> str:
    u, _ = urldefrag(u)
    p = urlparse(u)
    path = p.path or "/"
    return p._replace(path=path, fragment="").geturl()


def analyze_html(url: str, html: str, status: int = 200) -> PageAudit:
    soup = soup_of(html)
    title = soup.title.get_text(strip=True) if soup.title else ""
    md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    meta = (md.get("content") or "").strip() if md else ""
    canon = soup.find("link", attrs={"rel": lambda v: v and "canonical" in (v if isinstance(v, list) else [v])})
    html_tag = soup.find("html")
    imgs = soup.find_all("img")
    text = visible_text(soup)

    links: list[str] = []
    anchors = 0
    has_tel = has_wa = False
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if low.startswith("tel:"):
            has_tel = True
            continue
        if "wa.me" in low or "whatsapp" in low:
            has_wa = True
            continue
        if low.startswith(("mailto:", "javascript:")):
            continue
        if href.startswith("#"):
            if len(href) > 1:
                anchors += 1
            continue
        full = normalize_url(urljoin(url, href))
        if urlparse(full).scheme in ("http", "https") and _host(full) == _host(url):
            if not urlparse(full).path.lower().endswith(SKIP_EXT):
                links.append(full)

    jsonld_types: list[str] = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        for m in re.finditer(r'"@type"\s*:\s*"([^"]+)"', s.string or ""):
            jsonld_types.append(m.group(1))

    form_fields = 0
    for form in soup.find_all("form"):
        n = len([i for i in form.find_all(["input", "select", "textarea"]) if i.get("type") not in ("hidden", "submit", "button")])
        form_fields = max(form_fields, n)

    cr = re.search(r"©\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", text)
    typos = [m.group(0) for pat, _ in TYPO_RE for m in [pat.search(text)] if m]

    return PageAudit(
        url=url,
        status=status,
        title=title,
        meta_description=meta,
        h1=[h.get_text(" ", strip=True) for h in soup.find_all("h1")],
        h2_count=len(soup.find_all("h2")),
        canonical=(canon.get("href") if canon else "") or "",
        lang=(html_tag.get("lang") if html_tag else "") or "",
        viewport=bool(soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})),
        images_total=len(imgs),
        images_missing_alt=len([i for i in imgs if not i.has_attr("alt")]),
        word_count=len(text.split()),
        jsonld_types=jsonld_types,
        internal_links=sorted(set(links)),
        anchor_links=anchors,
        og_tags=bool(soup.find("meta", attrs={"property": re.compile(r"^og:", re.I)})),
        typos=typos,
        copyright_year=int(cr.group(1)) if cr else 0,
        has_tel=has_tel,
        has_whatsapp=has_wa,
        max_form_fields=form_fields,
    )


def crawl(site_url: str, limit: int = 25, delay: float = 0.2, session=None) -> list[PageAudit]:
    s = session or requests.Session()
    if hasattr(s, "headers"):
        s.headers.update(HEADERS)
    start = normalize_url(site_url if site_url.startswith("http") else "https://" + site_url)
    rp = RobotFileParser()
    try:
        rr = s.get(urljoin(start, "/robots.txt"), timeout=10)
        if rr.status_code == 200 and "html" not in rr.headers.get("content-type", "").lower():
            rp.parse(rr.text.splitlines())
        else:
            rp = None
    except Exception:
        rp = None
    queue, seen, pages = [start], set(), []
    while queue and len(pages) < limit:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if rp is not None:
            try:
                if not rp.can_fetch(UA, url):
                    continue
            except Exception:
                pass
        try:
            r = s.get(url, timeout=20, allow_redirects=True)
        except Exception as exc:  # network error -> record as status 0
            pages.append(PageAudit(url=url, status=0, title=f"ERROR: {exc}"[:120]))
            continue
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype.lower():
            continue
        page = analyze_html(normalize_url(r.url), r.text, r.status_code)
        pages.append(page)
        for link in page.internal_links:
            if link not in seen and link not in queue:
                queue.append(link)
        if delay:
            time.sleep(delay)
    return pages


def site_checks(site_url: str, session=None) -> dict:
    s = session or requests.Session()
    base = normalize_url(site_url if site_url.startswith("http") else "https://" + site_url)
    p = urlparse(base)
    root = f"{p.scheme}://{p.netloc}"
    out: dict = {"https": p.scheme == "https"}

    def fetch(path: str):
        try:
            return s.get(root + path, timeout=15, allow_redirects=True, headers=HEADERS)
        except Exception:
            return None

    r = fetch("/robots.txt")
    out["robots_txt"] = bool(r is not None and r.status_code == 200 and "html" not in r.headers.get("content-type", "").lower())
    out["robots_has_sitemap"] = bool(out["robots_txt"] and "sitemap:" in r.text.lower())
    r = fetch("/sitemap.xml")
    head = r.text[:2000].lower() if r is not None and r.status_code == 200 else ""
    out["sitemap_xml"] = ("<urlset" in head or "<sitemapindex" in head) and "html" not in (r.headers.get("content-type", "").lower() if r is not None else "")
    alt_host = p.netloc.removeprefix("www.") if p.netloc.startswith("www.") else "www." + p.netloc
    try:
        rr = s.get(f"{p.scheme}://{alt_host}/", timeout=15, allow_redirects=False, headers=HEADERS)
        out["alt_host"] = alt_host
        out["alt_host_status"] = rr.status_code
        out["alt_host_redirects"] = rr.status_code in (301, 308)
    except Exception:
        out["alt_host"], out["alt_host_status"], out["alt_host_redirects"] = alt_host, None, None
    return out


def check_links(pages: list[PageAudit], session=None, limit: int = 40) -> list[Issue]:
    s = session or requests.Session()
    crawled = {p.url for p in pages}
    todo = []
    for p in pages:
        for l in p.internal_links:
            if l not in crawled and l not in todo:
                todo.append(l)
    issues = []
    for url in todo[:limit]:
        try:
            r = s.head(url, timeout=10, allow_redirects=True, headers=HEADERS)
            if r.status_code in (403, 405):
                r = s.get(url, timeout=10, allow_redirects=True, headers=HEADERS)
            if r.status_code >= 400:
                issues.append(Issue("high", "broken_link", url, f"Internal link returns HTTP {r.status_code}.", "Fix or remove the link."))
        except Exception as exc:
            issues.append(Issue("medium", "link_unreachable", url, f"Could not check link: {exc}", "Verify manually."))
    return issues


def build_issues(pages: list[PageAudit], checks: dict) -> list[Issue]:
    I: list[Issue] = []
    now_year = datetime.now().year
    live = [p for p in pages if p.status]
    root_url = pages[0].url if pages else ""

    for p in pages:
        u = p.url
        if p.status != 200:
            I.append(Issue("critical", "bad_status", u, f"Page returned status {p.status}.", "Make sure the page loads (HTTP 200)."))
            continue
        if not p.title:
            I.append(Issue("critical", "no_title", u, "Missing <title>.", "Add a unique title with service + location."))
        elif len(p.title) <= 12 or len(p.title.split()) <= 1:
            I.append(Issue("high", "weak_title", u, f'Title "{p.title}" is just a brand name; it has no service or location keywords.', "Use e.g. 'Solar Panel Installation Dubai & UAE | Kunergy Solar'."))
        elif len(p.title) > 65:
            I.append(Issue("medium", "long_title", u, f"Title is {len(p.title)} characters (will be truncated).", "Keep under about 60 characters."))
        if not p.meta_description:
            I.append(Issue("high", "no_meta_description", u, "Missing meta description.", "Write a 120-155 character description with a call to action."))
        elif not (70 <= len(p.meta_description) <= 165):
            I.append(Issue("low", "meta_length", u, f"Meta description is {len(p.meta_description)} characters.", "Aim for 120-155 characters."))
        if not p.h1:
            I.append(Issue("high", "no_h1", u, "Missing H1.", "Add exactly one H1 containing the primary keyword."))
        elif len(p.h1) > 1:
            I.append(Issue("medium", "multiple_h1", u, f"{len(p.h1)} H1 tags.", "Keep a single H1."))
        elif p.h1[0].lower().startswith("welcome"):
            I.append(Issue("medium", "generic_h1", u, f'H1 "{p.h1[0]}" is generic and has no keywords.', "Describe what you do and where."))
        if not p.canonical:
            I.append(Issue("medium", "no_canonical", u, "No canonical link.", "Add <link rel='canonical'> to avoid duplicate-URL issues."))
        if not p.viewport:
            I.append(Issue("high", "no_viewport", u, "No mobile viewport meta tag.", "Add width=device-width viewport."))
        if not p.lang:
            I.append(Issue("low", "no_lang", u, "<html> has no lang attribute.", 'Add lang="en".'))
        if p.images_missing_alt:
            sev = "high" if p.images_total and p.images_missing_alt / p.images_total > 0.5 else "medium"
            I.append(Issue(sev, "missing_alt", u, f"{p.images_missing_alt} of {p.images_total} images have no alt attribute.", "Add descriptive alt text (alt='' for purely decorative images)."))
        if p.word_count < 300:
            I.append(Issue("medium", "thin_content", u, f"Only {p.word_count} words of visible text.", "Service pages should have 600-1000 useful words."))
        if not p.jsonld_types:
            I.append(Issue("high" if u == root_url else "medium", "no_schema", u, "No JSON-LD structured data.", "Add Organization/LocalBusiness (+ Service, FAQ) schema."))
        if not p.og_tags:
            I.append(Issue("low", "no_open_graph", u, "No Open Graph tags.", "Add og:title/description/url/type for link previews."))
        if p.typos:
            I.append(Issue("medium", "typos", u, "Typos found: " + ", ".join(sorted(set(p.typos))), "Correct spelling (and use 'Electric Vehicle', which is what people search)."))
        if p.copyright_year and p.copyright_year < now_year:
            I.append(Issue("low", "stale_copyright", u, f"Footer copyright says {p.copyright_year}.", f"Update to {now_year}."))
        if p.max_form_fields > 7:
            I.append(Issue("medium", "long_form", u, f"Form has {p.max_form_fields} fields.", "Shorten to ~6-8 and add qualifiers (property type, monthly bill, city)."))

    if len(live) <= 1 and any(p.anchor_links >= 3 for p in live):
        I.append(Issue("critical", "single_page_site", root_url, "The whole site is one URL with anchor (#) navigation.", "Create separate pages per service and market so each can rank."))
    elif len(live) < 5:
        I.append(Issue("high", "few_pages", root_url, f"Only {len(live)} page(s) found.", "Add service, location, project and blog pages."))
    urls = " ".join(p.url.lower() for p in live)
    if not re.search(r"project|case|portfolio|testimonial", urls):
        I.append(Issue("high", "no_proof_pages", root_url, "No projects / case studies / testimonials pages.", "Publish real projects and testimonials; they drive trust and conversions."))
    if "blog" not in urls and "guide" not in urls:
        I.append(Issue("medium", "no_blog", root_url, "No blog or guides section.", "Publish helpful articles (cost, payback, how it works)."))
    if live and not any(p.has_tel or p.has_whatsapp for p in live):
        I.append(Issue("high", "no_click_to_contact", root_url, "No tel: or WhatsApp links found.", "Add click-to-call and WhatsApp buttons (mobile users convert on these)."))
    if not checks.get("https", True):
        I.append(Issue("high", "no_https", root_url, "Site URL is not HTTPS.", "Enable HTTPS and redirect HTTP to HTTPS."))
    if checks.get("robots_txt") is False:
        I.append(Issue("medium", "no_robots", root_url, "robots.txt not found.", "Add robots.txt with a Sitemap line."))
    if checks.get("sitemap_xml") is False:
        I.append(Issue("high", "no_sitemap", root_url, "sitemap.xml not found.", "Generate and submit sitemap.xml in Search Console."))
    if checks.get("alt_host_status") == 200:
        I.append(Issue("medium", "www_split", root_url, f"{checks.get('alt_host')} also serves the site without redirecting.", "301-redirect one host to the other."))

    I.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.code))
    return I


def run_audit(site_url: str, limit: int = 25, pagespeed: dict | None = None, session=None, delay: float = 0.2) -> AuditReport:
    pages = crawl(site_url, limit=limit, session=session, delay=delay)
    checks = site_checks(site_url, session=session)
    issues = build_issues(pages, checks)
    issues += check_links(pages, session=session)
    issues.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.code))
    return AuditReport(
        site_url=site_url,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pages=pages,
        issues=issues,
        site_checks=checks,
        pagespeed=pagespeed,
    )
