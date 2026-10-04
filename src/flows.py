"""Pipeline stages: draft -> build patch -> QA -> (human approval) -> publish.  Three engines:

  offline : no LLM. Deterministic scaffolds with [NEEDS CLIENT FACT] markers (cannot be published until filled).
  direct  : Groq REST (Writer then Reviewer prompts). Fewest dependencies.
  crewai  : CrewAI multi-agent crew (Writer -> Reviewer with context), on Groq.
"""
from __future__ import annotations

import difflib
import re
import time
from datetime import date
from urllib.parse import quote

from .agents import AGENT_SPECS, run_single, run_writer_reviewer
from .facts import facts_for_prompt
from .llm import LLMError, extract_json, groq_chat
from .models import Change, PageDraft, PageSpec, PatchResult, QAIssue
from .storage import get_control, log_event, save_json
from . import theme as theme_mod
from .tools import page_builder, qa, schema_builder as sb, sitemap
from .tools.html_patcher import apply_page_fixes
from .tools.schema_builder import clean_phone

ENGINES = ["offline", "direct", "crewai"]

WRITER_SCHEMA = '{"intro": "two short paragraphs separated by a blank line", "sections": [{"h2": "heading", "body": "1-3 paragraphs"}], "faq": [{"q": "question", "a": "answer"}], "cta_text": "short button text"}'


# ============================================================ drafting
def _clean(s) -> str:
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def writer_prompt(spec: PageSpec, facts: dict) -> str:
    return f"""Write the body copy for ONE web page.
PAGE H1: {spec.h1} | Market: {spec.market} | Service: {spec.service}
Primary keyword: "{spec.primary_keyword}" (use naturally, at most 3-4 times; the title and H1 already contain it).
Secondary keywords (optional, natural use only): {", ".join(spec.secondary_keywords)}

FACTS (the ONLY source of truth about the company):
{facts_for_prompt(facts)}

Requirements:
- 450-800 words in total: an intro (2 short paragraphs), 4-6 sections each with an h2 and 1-3 paragraphs, and 4-5 FAQs.
- Plain English, specific and helpful: what the service is, who it suits, how a project generally works, what a buyer should prepare or ask.
- General industry explanation is fine. Anything about the company itself (experience, numbers, brands, certifications, warranties, response times, prices, savings, projects) must come from FACTS, otherwise write [NEEDS CLIENT FACT: what is missing].
- No prices, savings percentages, payback periods, warranty lengths or regulation details unless they appear in FACTS.
- No superlatives ("best", "#1", "leading"), no guarantees, no competitor mentions.
- Output ONLY valid JSON in this exact shape: {WRITER_SCHEMA}"""


def reviewer_prompt(spec: PageSpec, facts: dict, draft_json: str = "") -> str:
    body = f"\nDRAFT TO REVIEW:\n{draft_json}\n" if draft_json else "\n(The draft to review is the output of the previous task.)\n"
    return f"""Review the draft for the page "{spec.h1}".{body}
FACTS (the ONLY source of truth about the company):
{facts_for_prompt(facts)}

Fix it: delete or replace any claim about the company that is not in FACTS (use [NEEDS CLIENT FACT: ...]); remove numbers, prices, warranty lengths,
savings and regulation details not in FACTS; remove superlatives and guarantees; reduce keyword repetition; keep it natural and useful.
Return ONLY valid JSON in the same shape: {WRITER_SCHEMA}"""


def draft_from_dict(spec: PageSpec, d: dict, source: str) -> PageDraft:
    sections = [{"h2": _clean(s.get("h2")), "body": _clean(s.get("body"))} for s in d.get("sections", []) if isinstance(s, dict) and s.get("h2")]
    faq = [{"q": _clean(f.get("q")), "a": _clean(f.get("a"))} for f in d.get("faq", []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    return PageDraft(
        slug=spec.slug, market=spec.market, service=spec.service, title=spec.title, meta_description=spec.meta_description,
        h1=spec.h1, intro=_clean(d.get("intro")), sections=sections, faq=faq,
        cta_text=_clean(d.get("cta_text")) or "Request a quote", parent=spec.parent, source=source,
    )


def _relevant_services(spec: PageSpec, facts: dict) -> list[str]:
    stop = {"and", "the", "for", "solar", "services", "service", "systems", "solutions"}
    key = {w for w in re.findall(r"[a-z]+", f"{spec.service} {spec.primary_keyword}".lower()) if w not in stop and len(w) > 2}
    out = [s["name"] for s in facts.get("services", []) if key & set(re.findall(r"[a-z]+", s["name"].lower()))]
    return out[:4]


def offline_draft(spec: PageSpec, facts: dict) -> PageDraft:
    brand, founded = facts["company"]["brand"], facts["company"].get("founded")
    ent = next((e for e in facts.get("entities", []) if (e["key"] == "uae" and spec.market == "UAE") or (e["key"] == "pk" and spec.market == "PK")), None)
    rel = _relevant_services(spec, facts)
    fact_line = f"{brand} was founded in {founded}." if founded else ""
    if rel:
        fact_line += " Related services we offer: " + "; ".join(rel) + "."
    need = lambda what: f"[NEEDS CLIENT FACT: {what}]"  # noqa: E731
    sections = [
        {"h2": f"What our {spec.service.lower()} service includes", "body": need(f"describe exactly what {brand} delivers for {spec.service}, scope and exclusions")},
        {"h2": "Who it is for", "body": need("which customers/sites you serve for this service, e.g. villas, factories, warehouses")},
        {"h2": "How a project works", "body": need(f"{brand}'s real process steps from enquiry to handover")},
        {"h2": f"Why choose {brand}", "body": need("real proof: years, projects, brands, certifications (fill proof section of facts.yaml)")},
    ]
    if ent:
        sections.append({"h2": "Where to find us", "body": f"{ent['legal_name']}, {ent['street']}, {ent['locality']}, {ent['country']}. Phone: {ent['phone']}. Email: {ent['email']}."})
    faq = [
        {"q": f"How do I get a quote for {spec.service.lower()}?", "a": need("your real quote process and what information customers should send")},
        {"q": "Which areas do you serve?", "a": need("service areas")},
        {"q": "How long does a project take?", "a": need("typical timeline from your real projects")},
    ]
    return PageDraft(
        slug=spec.slug, market=spec.market, service=spec.service, title=spec.title, meta_description=spec.meta_description, h1=spec.h1,
        intro=(fact_line + "\n\n" if fact_line else "") + need(f"2-3 sentence introduction to {spec.service} for {spec.market} customers"),
        sections=sections, faq=faq, parent=spec.parent, source="offline",
    )


def draft_page(spec: PageSpec, facts: dict, engine: str = "offline") -> PageDraft:
    if get_control()["kill_switch"]:
        raise RuntimeError("Kill switch is ON: AI actions are disabled.")
    if engine == "offline":
        return offline_draft(spec, facts)
    if engine == "direct":
        w = AGENT_SPECS["writer"]
        raw = groq_chat([{"role": "system", "content": w["backstory"]}, {"role": "user", "content": writer_prompt(spec, facts)}], json_mode=True, max_tokens=3500)
        first = extract_json(raw)
        r = AGENT_SPECS["reviewer"]
        raw2 = groq_chat([{"role": "system", "content": r["backstory"]}, {"role": "user", "content": reviewer_prompt(spec, facts, raw)}], json_mode=True, max_tokens=3500)
        try:
            data = extract_json(raw2)
        except LLMError:
            data = first
    elif engine == "crewai":
        first_raw, final_raw = run_writer_reviewer(writer_prompt(spec, facts), reviewer_prompt(spec, facts), WRITER_SCHEMA)
        try:
            data = extract_json(final_raw)
        except LLMError:
            data = extract_json(first_raw)
    else:
        raise ValueError(f"Unknown engine: {engine}")
    d = draft_from_dict(spec, data, "ai")
    log_event("draft", f"Drafted {spec.slug}", engine=engine)
    return d


def draft_pages(specs: list[PageSpec], facts: dict, engine: str, progress=None) -> list[PageDraft]:
    out = []
    for i, s in enumerate(specs):
        out.append(draft_page(s, facts, engine))
        if progress:
            progress(i + 1, len(specs), s.slug)
    return out


# ============================================================ patch building
def _wa_link(number: str | None) -> str | None:
    digits = re.sub(r"\D", "", number or "")
    return f"https://wa.me/{digits}?text={quote('Hello Kunergy, I would like to request a quote.')}" if digits else None


def contact_items(path: str, facts: dict, is_home: bool) -> list[tuple[str, str]]:
    ents = {e["key"]: e for e in facts.get("entities", [])}
    items: list[tuple[str, str]] = []
    if path.startswith("uae/"):
        chosen = [("Call", ents.get("uae"))]
    elif path.startswith("pakistan/"):
        chosen = [("Call", ents.get("pk"))]
    else:
        chosen = [("Call UAE", ents.get("uae")), ("Call Pakistan", ents.get("pk"))]
    for label, e in chosen:
        if e and e.get("phone"):
            items.append((label, "tel:" + (clean_phone(e["phone"]) or "")))
        wa = _wa_link(e.get("whatsapp")) if e else None
        if wa:
            items.append(("WhatsApp", wa))
    items.append(("Get a Quote", "#contact" if is_home else "/#contact"))
    return items


def _page_path(slug: str) -> str:
    return slug + "index.html" if slug.endswith("/") else slug


def _unified(path: str, old: str, new: str) -> str:
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))


DEFAULT_OPTIONS = {"low_risk": True, "home_seo": True, "schema": True, "contact_bar": True, "internal_links": True, "new_pages": True, "sitemap": True, "premium_theme": True}
LOW_RISK_ONLY = {"low_risk": True, "home_seo": False, "schema": False, "contact_bar": False, "internal_links": False, "new_pages": False, "sitemap": True, "premium_theme": False}


def build_patch(files: dict[str, str], drafts: list[PageDraft], facts: dict, *, options: dict | None = None, today: date | None = None, theme_cfg: dict | None = None) -> PatchResult:
    opts = {**DEFAULT_OPTIONS, **(options or {})}
    today = today or date.today()
    base = facts["company"]["website"].rstrip("/")
    brand = facts["company"]["brand"]
    res = PatchResult(low_risk_only=not any(opts[k] for k in ("home_seo", "schema", "contact_bar", "internal_links", "new_pages", "premium_theme")))
    html_paths = sorted(p for p in files if p.lower().endswith((".html", ".htm")))
    home = "index.html" if "index.html" in files else (html_paths[0] if html_paths else None)

    use_drafts = drafts if opts["new_pages"] else []
    new_pages: dict[str, PageDraft] = {}
    for d in use_drafts:
        p = _page_path(d.slug)
        if p in files:
            res.qa.issues.append(QAIssue("warn", "page_exists", p, "A page already exists at this path; skipped (never overwritten)."))
            continue
        new_pages[p] = d

    service_links = [(d.h1, "/" + d.slug) for d in new_pages.values()] if opts["internal_links"] else None
    ld_home: list[tuple[str, dict]] | None = None
    if opts["schema"]:
        ld_home = [("organization", sb.organization(facts))] + [(f"local-{e['key']}", sb.local_business(e, facts)) for e in facts.get("entities", [])]
    seo = facts.get("home_seo") or {}
    t_cfg = theme_cfg if theme_cfg is not None else theme_mod.load_theme()
    t_href = None
    if opts["premium_theme"] and t_cfg.get("enabled", True):
        css = theme_mod.build_css(t_cfg)
        css_problems = theme_mod.sanitize_css(css, require_scope=False) + theme_mod.sanitize_css(t_cfg.get("extra_css") or "")
        if css_problems:
            res.qa.issues.append(QAIssue("error", "unsafe_css", theme_mod.CSS_PATH, "; ".join(css_problems[:3])))
        else:
            t_href = theme_mod.theme_href(css)
            if files.get(theme_mod.CSS_PATH) != css:
                res.files[theme_mod.CSS_PATH], res.originals[theme_mod.CSS_PATH] = css, files.get(theme_mod.CSS_PATH, "")
                res.changes.append(Change(theme_mod.CSS_PATH, "theme_css", "high", f"{'Updated' if theme_mod.CSS_PATH in files else 'Created'} premium theme stylesheet ({theme_mod.PALETTES.get(t_cfg.get('palette'), {}).get('label', 'custom')})."))
                res.diffs[theme_mod.CSS_PATH] = _unified(theme_mod.CSS_PATH, files.get(theme_mod.CSS_PATH, ""), css)

    for path in html_paths:
        is_home = path == home
        new_html, ch = apply_page_fixes(
            files[path], path, year=today.year, brand=brand, alt_rules=facts.get("alt_text_rules"), canonical_base=base,
            low_risk=opts["low_risk"],
            title=seo.get("title") if (is_home and opts["home_seo"]) else None,
            meta_description=seo.get("meta_description") if (is_home and opts["home_seo"]) else None,
            h1=seo.get("h1") if (is_home and opts["home_seo"]) else None,
            jsonld=ld_home if is_home else None,
            contact_items=contact_items(path, facts, is_home) if opts["contact_bar"] else None,
            service_links=service_links if is_home else None,
            theme_href=t_href,
        )
        if ch:
            res.files[path] = new_html
            res.originals[path] = files[path]
            res.changes.extend(ch)
            res.diffs[path] = _unified(path, files[path], new_html)

    # ---- new pages
    head_assets = page_builder.extract_head_assets(files.get(home)) if home else ""
    hubs = {d.slug: d for d in new_pages.values() if d.slug in ("uae/", "pakistan/")}
    nav = [("Home", "/")] + [(("UAE" if s == "uae/" else "Pakistan"), "/" + s) for s in hubs] + [("Get a Quote", "/#contact")]
    for path, d in new_pages.items():
        hub = next((x for x in new_pages.values() if x.slug == d.parent), None)
        html = page_builder.render_page(d, facts, head_assets=head_assets, nav_links=nav, hub_title=hub.h1 if hub else "")
        if opts["contact_bar"]:
            html, _ = apply_page_fixes(html, path, year=today.year, low_risk=False, contact_items=contact_items(path, facts, False), theme_href=t_href)
        elif t_href:
            html, _ = apply_page_fixes(html, path, year=today.year, low_risk=False, theme_href=t_href)
        res.files[path] = html
        res.originals[path] = ""
        res.changes.append(Change(path, "new_page", "high", f"New page: {d.h1} ({'AI-drafted' if d.source == 'ai' else 'offline scaffold'})."))
        res.diffs[path] = _unified(path, "", html)

    # ---- sitemap + robots
    if opts["sitemap"] and (html_paths or new_pages):
        site_pages = [p for p in html_paths if not re.search(r"(^|/)(404|thank-?you|thanks)\.html?$", p)] + list(new_pages)
        sm = sitemap.build_sitemap(base, site_pages, today)
        if files.get("sitemap.xml") != sm:
            res.files["sitemap.xml"], res.originals["sitemap.xml"] = sm, files.get("sitemap.xml", "")
            res.changes.append(Change("sitemap.xml", "sitemap", "low", f"{'Updated' if 'sitemap.xml' in files else 'Created'} sitemap.xml with {len(site_pages)} URL(s)."))
            res.diffs["sitemap.xml"] = _unified("sitemap.xml", files.get("sitemap.xml", ""), sm)
        rb_old = files.get("robots.txt")
        rb = sitemap.build_robots(base) if rb_old is None else sitemap.ensure_robots_sitemap(rb_old, base)
        if rb != rb_old:
            res.files["robots.txt"], res.originals["robots.txt"] = rb, rb_old or ""
            res.changes.append(Change("robots.txt", "robots", "low", f"{'Updated' if rb_old else 'Created'} robots.txt with Sitemap line."))
            res.diffs["robots.txt"] = _unified("robots.txt", rb_old or "", rb)

    # ---- QA gate
    changed_html = {p: c for p, c in res.files.items() if p.lower().endswith((".html", ".htm"))}
    all_paths = set(files) | set(new_pages) | set(res.files)
    rep = qa.qa_site(changed_html, generated=set(new_pages), all_paths=all_paths, facts=facts)
    res.qa.issues.extend(rep.issues)
    log_event("build_patch", "Patch built", **res.summary())
    return res


def publish_patch(patch: PatchResult, *, ops, dry_run: bool, title: str, body: str, branch_prefix: str = "seo/autopilot", draft_pr: bool = True) -> dict:
    if get_control()["kill_switch"]:
        raise RuntimeError("Kill switch is ON: publishing is disabled.")
    if not patch.files:
        raise RuntimeError("The patch is empty.")
    if not patch.qa.passed:
        raise RuntimeError(f"QA gate failed with {len(patch.qa.errors)} error(s). Fix them before publishing.")
    if dry_run or ops is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        save_json(f"patches/{stamp}.json", {"files": patch.files, "changes": patch.changes, "summary": patch.summary()})
        log_event("publish", "Dry-run: patch saved, nothing pushed", stamp=stamp)
        return {"mode": "dry_run", "pr_url": None, "saved": f"patches/{stamp}.json"}
    url = ops.open_pr(patch.files, branch_prefix, title, body, draft=draft_pr)
    log_event("publish", "Pull request opened", url=url, low_risk_only=patch.low_risk_only)
    return {"mode": "pr", "pr_url": url}


def pr_body(patch: PatchResult) -> str:
    lines = ["## SEO Autopilot changes", "", "| File | Change | Risk |", "|---|---|---|"]
    lines += [f"| `{c.path}` | {c.description} | {c.risk} |" for c in patch.changes]
    lines += ["", f"QA: {len(patch.qa.errors)} error(s), {len(patch.qa.warnings)} warning(s)."]
    lines += [f"- warning `{i.code}` {i.page}: {i.message}" for i in patch.qa.warnings[:20]]
    lines += ["", "**Rollback:** revert this pull request after merge.", "", "_Generated by Kunergy SEO Autopilot. A human must review before merging._"]
    return "\n".join(lines)


# ============================================================ AI helpers (optional) + deterministic fallbacks
def _ask(role: str, prompt: str, engine: str, expected: str = "Markdown text", fast: bool = False, json_mode: bool = False) -> str:
    if get_control()["kill_switch"]:
        raise RuntimeError("Kill switch is ON: AI actions are disabled.")
    if engine == "crewai":
        return run_single(role, prompt, expected, fast=fast)
    if engine == "direct":
        return groq_chat([{"role": "system", "content": AGENT_SPECS[role]["backstory"]}, {"role": "user", "content": prompt}], fast=fast, json_mode=json_mode)
    raise LLMError("Choose engine 'direct' or 'crewai' for AI features.")


def audit_plan_offline(report) -> str:
    lines = [f"# Prioritized fix plan for {report.site_url}", ""]
    for sev in ("critical", "high", "medium", "low"):
        items = [i for i in report.issues if i.severity == sev]
        if not items:
            continue
        lines.append(f"## {sev.title()} ({len(items)})")
        for i in items:
            lines.append(f"- **{i.code}** ({i.url}): {i.message} → {i.fix}")
        lines.append("")
    return "\n".join(lines)


def audit_plan_ai(report, facts: dict, engine: str) -> str:
    top = "\n".join(f"- [{i.severity}] {i.code} @ {i.url}: {i.message}" for i in report.issues[:60])
    prompt = f"""Here are crawl findings for {report.site_url}, a solar/energy company (UAE + Pakistan):
{top}
PageSpeed: {report.pagespeed}
Write a prioritized 2-week fix plan in Markdown: group by impact on quote requests, give the exact fix for each, and flag what needs real company facts from the owner. Max 450 words."""
    return _ask("auditor", prompt, engine)


CRO_FORM_SPEC = """## Recommended quote form (replace the 9-field form)
| Field | Type | Why |
|---|---|---|
| Full name | text | required |
| Phone / WhatsApp | tel | fastest way to reach buyers |
| Email | email | follow-up and proposal |
| City | select (Dubai, Abu Dhabi, Sharjah, Lahore, Other) | routes the lead to the right team |
| Property type | select (Villa/Home, Commercial, Industrial, Utility) | qualifies the lead |
| Service needed | select (Solar PV, Solar + battery, EV charging, Electrical/AC, Maintenance, Consultancy) | routes the lead |
| Average monthly electricity bill | select ranges | sizes the system |
| Message | textarea (optional) | details |

**Also:** keep the real phone number visible in the header, add a sticky Call/WhatsApp bar on mobile, show proof near the form
(real projects, certifications, testimonials), add a thank-you page and fire a GA4 conversion event on it, and reply to every lead within minutes."""


def cro_plan(report, facts: dict, engine: str = "offline") -> str:
    base = CRO_FORM_SPEC
    if engine == "offline":
        return base
    extra = _ask("cro", f"Given these audit issues:\n" + "\n".join(f"- {i.code}: {i.message}" for i in report.issues[:30]) + "\nSuggest 8 specific conversion improvements for the site in Markdown bullets, most impactful first. Max 250 words.", engine)
    return base + "\n\n## Additional AI recommendations\n" + extra


def local_pack_offline(facts: dict) -> dict:
    brand = facts["company"]["brand"]
    names = [s["name"] for s in facts.get("services", [])]
    short = "solar PV design and installation, battery energy storage, EV charging, electrical contracting, air conditioning and maintenance"
    return {
        "gbp_description": f"{brand} provides renewable energy and technical services: {short}. Call or message us to request a quote.",
        "gbp_categories_to_consider": ["Solar energy company", "Solar energy contractor", "Electrician", "Air conditioning contractor", "EV charging station contractor"],
        "gbp_services_to_list": names,
        "gbp_posts": [
            "Project spotlight: [NEEDS CLIENT FACT: project name, location, system size, photo]. Request a quote at our website.",
            "How does solar work for a villa or business? Short explainer + a photo from a real installation. [NEEDS CLIENT FACT: photo]",
            "Meet the team: [NEEDS CLIENT FACT: team photo and a sentence about the engineers on your projects].",
            "Maintenance matters: why regular solar PV and AC servicing protects performance. Contact us to ask about maintenance.",
        ],
        "review_request": f"Hi [Name], thank you for choosing {brand}. If you are happy with our work, would you share a short review? It really helps other customers find us: [your Google review link]. Thank you!",
        "outreach_email": f"Subject: Partnership / listing request from {brand}\n\nHello [Name],\n\nI'm [your name] at {brand} ({facts['company'].get('website')}). We [NEEDS CLIENT FACT: one honest sentence about a relevant joint project or why this is useful to their audience]. Would you be open to [listing us / a short case-study feature / a guest article]?\n\nThank you,\n[Name, role, phone]",
        "citation_checklist": [
            "Google Business Profile (Dubai and Lahore)", "Bing Places for Business", "Apple Business Connect",
            "LinkedIn company page", "Facebook and Instagram business profiles",
            "Reputable UAE business directories", "Reputable Pakistan business directories",
            "Chamber of commerce / industry association member pages (only if you are a member)",
            "Supplier/partner 'where to buy / installers' pages (only for brands you really install)",
            "Keep name, address and phone IDENTICAL everywhere",
        ],
    }


def local_pack_ai(facts: dict, engine: str) -> dict:
    prompt = f"""Using ONLY these facts:\n{facts_for_prompt(facts)}\nDraft local-SEO assets as JSON with keys: gbp_description (max 700 chars), gbp_posts (4 short posts),
review_request (short, honest, no incentives), outreach_email (partner/supplier/association request with subject). Use [NEEDS CLIENT FACT: ...] for anything unknown. JSON only."""
    data = extract_json(_ask("local", prompt, engine, json_mode=True))
    base = local_pack_offline(facts)
    for k in ("gbp_description", "gbp_posts", "review_request", "outreach_email"):
        if data.get(k):
            base[k] = data[k]
    return base


def weekly_report_md(analysis: dict, ai_text: str = "") -> str:
    def rows(items):
        return "\n".join(f"| {r['query']} | {r['clicks']:.0f} | {r['impressions']:.0f} | {r['ctr']:.1f}% | {r['position']:.1f} |" for r in items) or "| (none) | | | | |"

    head = "| Query | Clicks | Impr. | CTR | Pos. |\n|---|---|---|---|---|"
    md = [
        "# Weekly SEO report", "",
        f"- Queries: **{analysis['queries']}**  |  Clicks: **{analysis['clicks']:.0f}**  |  Impressions: **{analysis['impressions']:.0f}**  |  Avg CTR: **{analysis['avg_ctr']}%**", "",
        "## Top queries by clicks", head, rows(analysis["top_by_clicks"]), "",
        "## Striking distance (position 8-20): improve these pages first", head, rows(analysis["striking_distance"]), "",
        "## High impressions, low CTR (rewrite title/meta)", head, rows(analysis["low_ctr_top10"]), "",
    ]
    if ai_text:
        md += ["## Recommended next actions", ai_text]
    return "\n".join(md)


def weekly_report_ai(analysis: dict, engine: str) -> str:
    prompt = f"Search Console summary: {analysis}\nGive the 3 highest-impact next actions for a solar/energy company's website, each with the exact page/query and what to change. Max 200 words."
    return _ask("reporter", prompt, engine, fast=True)


def design_extra_css(html: str, theme_cfg: dict, engine: str) -> tuple[str, list[str]]:
    """Designer agent proposes extra scoped CSS from the site's real class inventory. Returns (css, problems)."""
    inv = theme_mod.inventory(html)
    data = extract_json(_ask("designer", theme_mod.designer_prompt(inv, theme_cfg), engine, json_mode=True))
    css = str(data.get("extra_css", "")).strip()
    return css, theme_mod.sanitize_css(css)
