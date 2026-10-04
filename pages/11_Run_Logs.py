import streamlit as st

from src.storage import load_json, read_logs
from src.ui import setup_page

setup_page("Dashboard", "📊")
audit = load_json("audit.json")
drafts = load_json("drafts.json", []) or []
patch = load_json("last_patch_summary.json")

if audit:
    sev = {k: sum(1 for i in audit["issues"] if i["severity"] == k) for k in ("critical", "high", "medium", "low")}
    cols = st.columns(5)
    for col, (k, v) in zip(cols, sev.items()):
        col.metric(k.title(), v)
    cols[4].metric("Pages crawled", len(audit["pages"]))
    ps = audit.get("pagespeed")
    if ps and not ps.get("error"):
        st.subheader("PageSpeed (mobile)")
        c = st.columns(4)
        c[0].metric("Performance", ps.get("performance"))
        c[1].metric("SEO", ps.get("seo"))
        c[2].metric("Accessibility", ps.get("accessibility"))
        c[3].metric("LCP (s)", round((ps.get("lcp_ms") or 0) / 1000, 1))
else:
    st.info("No audit yet. Open **Site Audit** and run one.")

c1, c2 = st.columns(2)
c1.metric("Drafts", len(drafts))
c1.metric("Drafts with AI text", sum(1 for d in drafts if d.get("source") == "ai"))
if patch:
    c2.subheader("Last patch")
    c2.json(patch)

st.subheader("30-day checklist")
for item in [
    "Search Console + GA4 + Bing Webmaster verified; conversions defined (form, call, WhatsApp)",
    "Google Business Profile claimed (Dubai + Lahore)",
    "facts.yaml filled with real proof (projects, certifications, brands, WhatsApp)",
    "Audit run; low-risk PR merged",
    "Service pages drafted, edited by a human, QA-clean, merged",
    "Sitemap submitted; new URLs requested for indexing",
    "3-5 real case studies + testimonials published",
    "Quote form shortened; thank-you page + conversion event live",
    "First weekly report reviewed",
]:
    st.checkbox(item, key=f"chk_{item[:20]}")

st.subheader("Recent activity")
logs = read_logs(8)
st.dataframe(logs) if logs else st.caption("No activity yet.")

import streamlit as st

from src.llm import LLMError, groq_chat
from src.tools.github_ops import GitHubError, GitHubOps
from src.tools.pagespeed import run_pagespeed
from src.ui import setup_page

s = setup_page("Connections", "🔌")
st.caption("Keys are read from environment variables, `.env`, or Streamlit secrets. Values are never displayed.")

st.table({"Setting": ["GROQ_API_KEY", "GROQ_MODEL", "GITHUB_TOKEN", "SITE_REPO", "SITE_BRANCH", "SITE_URL", "PAGESPEED_API_KEY", "GSC_CREDENTIALS", "GSC_SITE_URL", "APP_PASSWORD"],
          "Status": ["set" if s.groq_api_key else "MISSING", s.groq_model, "set" if s.github_token else "MISSING", s.site_repo or "MISSING", s.site_branch, s.site_url,
                     "set" if s.pagespeed_api_key else "not set (optional)", "set" if s.gsc_credentials else "not set (optional)", s.gsc_site_url or "not set (optional)", "set" if s.app_password else "NOT SET"]})

c1, c2, c3, c4 = st.columns(4)
if c1.button("Test Groq"):
    try:
        out = groq_chat([{"role": "user", "content": "Reply with the single word OK."}], fast=True, max_tokens=8)
        st.success(f"Groq responded: {out.strip()[:40]}")
    except LLMError as e:
        st.error(str(e))
    except Exception as e:  # network etc.
        st.error(f"Could not reach Groq: {e}")
if c2.button("Test GitHub"):
    try:
        st.success(GitHubOps(s.github_token, s.site_repo, s.site_branch).check())
    except (GitHubError, Exception) as e:
        st.error(f"GitHub check failed: {e}")
if c3.button("Test PageSpeed"):
    with st.spinner("Running PageSpeed (can take ~30s)..."):
        r = run_pagespeed(s.site_url, api_key=s.pagespeed_api_key)
    st.error(r["error"]) if r.get("error") else st.success(f"Performance {r['performance']}, SEO {r['seo']}")
if c4.button("Check CrewAI"):
    try:
        import crewai

        st.success(f"crewai {getattr(crewai, '__version__', 'installed')}")
    except ImportError:
        st.warning("crewai is not installed. Engines 'offline' and 'direct' still work. `pip install crewai` to enable the multi-agent crew.")

import streamlit as st

from src.facts import FACTS_PATH, parse_facts_text, save_facts_text, years_in_business
from src.ui import setup_page

setup_page("Facts Editor", "📝")
st.warning("Everything the AI may claim comes from this file. Leave unknown items empty: they will never be claimed. Add real proof (projects, certifications, brands, testimonials with permission).")
text = st.text_area("facts.yaml", FACTS_PATH.read_text(encoding="utf-8"), height=560)
c1, c2, c3 = st.columns(3)
if c1.button("Validate"):
    try:
        f = parse_facts_text(text)
        st.success(f"Valid YAML. {len(f.get('services', []))} services, {len(f.get('entities', []))} entities, years in business: {years_in_business(f)}")
    except Exception as e:
        st.error(f"Invalid: {e}")
if c2.button("Save"):
    try:
        save_facts_text(text)
        st.success("Saved. On Streamlit Cloud this is temporary: download the file and commit it to your repo.")
    except Exception as e:
        st.error(f"Not saved: {e}")
c3.download_button("Download facts.yaml", text, "facts.yaml", "text/yaml")

import csv
import io
import json

import streamlit as st

from src import flows
from src.facts import load_facts
from src.models import AuditReport
from src.storage import load_json, log_event, save_json
from src.tools.crawler import run_audit
from src.tools.pagespeed import run_pagespeed
from src.ui import control, engine, setup_page

s = setup_page("Site Audit", "🔎")
url = st.text_input("Site URL", s.site_url)
c1, c2 = st.columns(2)
limit = c1.slider("Max pages to crawl", 1, 100, s.crawl_limit)
use_ps = c2.checkbox("Include PageSpeed (mobile) for the home page", value=True)

if st.button("Run audit", type="primary"):
    with st.status("Auditing...", expanded=True) as status:
        st.write("Crawling pages...")
        ps = None
        if use_ps:
            st.write("Running PageSpeed Insights...")
            ps = run_pagespeed(url, api_key=s.pagespeed_api_key)
        report = run_audit(url, limit=limit, pagespeed=ps)
        save_json("audit.json", report.to_dict())
        log_event("audit", f"Audited {url}", pages=len(report.pages), issues=len(report.issues))
        status.update(label=f"Done: {len(report.pages)} page(s), {len(report.issues)} issue(s)", state="complete")

data = load_json("audit.json")
if not data:
    st.info("Run an audit to see results.")
    st.stop()
report = AuditReport.from_dict(data)
st.caption(f"Audit of {report.site_url} at {report.generated_at}")
cols = st.columns(4)
for col, sev in zip(cols, ("critical", "high", "medium", "low")):
    col.metric(sev.title(), sum(1 for i in report.issues if i.severity == sev))
if report.pagespeed:
    st.write("PageSpeed:", report.pagespeed)
st.write("Site checks:", report.site_checks)

tab1, tab2, tab3 = st.tabs(["Issues", "Pages", "Fix plan"])
with tab1:
    sev_filter = st.multiselect("Severity", ["critical", "high", "medium", "low"], default=["critical", "high", "medium", "low"])
    rows = [i.__dict__ for i in report.issues if i.severity in sev_filter]
    st.dataframe(rows)
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    st.download_button("Download issues CSV", buf.getvalue(), "audit_issues.csv", "text/csv")
    st.download_button("Download audit JSON", json.dumps(data, indent=2), "audit.json", "application/json")
with tab2:
    st.dataframe([{k: v for k, v in p.__dict__.items() if k not in ("internal_links",)} for p in report.pages])
with tab3:
    st.markdown(flows.audit_plan_offline(report))
    if st.button("Ask the Auditor agent for a prioritized plan"):
        if control()["kill_switch"]:
            st.error("Kill switch is on.")
        else:
            try:
                with st.spinner("Auditor agent working..."):
                    st.markdown(flows.audit_plan_ai(report, load_facts(), engine()))
            except Exception as e:
                st.error(str(e))

import streamlit as st

from src.keywords import default_page_plan, match_queries_to_pages, plan_from_rows
from src.storage import load_json, save_json
from src.tools.gsc import analyze, load_gsc_csv
from src.ui import setup_page

setup_page("Keyword Map", "🗺️")
st.caption("One primary keyword per page, separate UAE / Pakistan pages. Verify search volumes in Google Keyword Planner before committing.")

saved = load_json("plan.json")
plan = plan_from_rows(saved) if saved else default_page_plan()
rows = [{**p.__dict__, "secondary_keywords": ", ".join(p.secondary_keywords)} for p in plan]
edited = st.data_editor(rows, num_rows="dynamic", key="plan_editor")
c1, c2 = st.columns(2)
if c1.button("Save plan", type="primary"):
    new_plan = plan_from_rows(edited)
    save_json("plan.json", [{**p.__dict__} for p in new_plan])
    st.success(f"Saved {len(new_plan)} pages.")
if c2.button("Reset to default plan"):
    save_json("plan.json", [p.__dict__ for p in default_page_plan()])
    st.rerun()

st.subheader("Use real Search Console data")
up = st.file_uploader("Search Console export (Queries.csv)", type=["csv"])
if up:
    rows_gsc = load_gsc_csv(up.getvalue())
    st.write(f"{len(rows_gsc)} queries loaded.")
    a = analyze(rows_gsc)
    st.write("Striking distance (position 8-20):")
    st.dataframe(a["striking_distance"])
    st.write("Queries matched to planned pages:")
    st.dataframe(match_queries_to_pages(rows_gsc[:200], plan_from_rows(edited)))

import streamlit as st

from src.facts import load_facts
from src.flows import draft_pages
from src.keywords import default_page_plan, plan_from_rows
from src.models import PageDraft
from src.storage import load_json, log_event, save_json
from src.tools import facts_guard
from src.ui import control, engine, setup_page

setup_page("Content Queue", "✍️")
facts = load_facts()
saved = load_json("plan.json")
plan = [p for p in (plan_from_rows(saved) if saved else default_page_plan()) if p.enabled]
st.caption("Drafts use ONLY facts.yaml. Any `[NEEDS CLIENT FACT: ...]` must be replaced by you before the QA gate lets a page through.")

chosen = st.multiselect("Pages to draft", [p.slug for p in plan], default=[p.slug for p in plan[2:5]])
st.write(f"Engine: **{engine()}** " + ("(scaffold only, no AI)" if engine() == "offline" else ""))
if st.button("Generate drafts", type="primary", disabled=not chosen):
    if control()["kill_switch"]:
        st.error("Kill switch is on.")
    else:
        prog = st.progress(0.0)
        try:
            new = draft_pages([p for p in plan if p.slug in chosen], facts, engine(), lambda i, n, slug: prog.progress(i / n, text=slug))
            by = {d["slug"]: d for d in (load_json("drafts.json", []) or [])}
            by.update({d.slug: d.__dict__ for d in new})
            save_json("drafts.json", list(by.values()))
            log_event("drafts", f"Generated {len(new)} draft(s)", engine=engine())
            st.success(f"{len(new)} draft(s) saved.")
        except Exception as e:
            st.error(f"Drafting failed: {e}")

drafts = [PageDraft(**d) for d in (load_json("drafts.json", []) or [])]
if not drafts:
    st.info("No drafts yet.")
for d in drafts:
    issues = facts_guard.check_draft(d, facts)
    badge = "✅ ready" if not issues else f"❌ {len(issues)} blocker(s)"
    with st.expander(f"{d.slug}  ·  {badge}  ·  source: {d.source}"):
        for i in issues:
            st.error(f"{i.code}: {i.message}")
        intro = st.text_area("Intro", d.intro, key=f"intro_{d.slug}", height=120)
        secs = []
        for n, sec in enumerate(d.sections):
            h2 = st.text_input(f"Section {n + 1} heading", sec["h2"], key=f"h2_{d.slug}_{n}")
            body = st.text_area(f"Section {n + 1} text", sec["body"], key=f"b_{d.slug}_{n}", height=130)
            secs.append({"h2": h2, "body": body})
        faqs = []
        for n, f in enumerate(d.faq):
            q = st.text_input(f"FAQ {n + 1} question", f["q"], key=f"q_{d.slug}_{n}")
            a = st.text_area(f"FAQ {n + 1} answer", f["a"], key=f"a_{d.slug}_{n}", height=80)
            faqs.append({"q": q, "a": a})
        c1, c2 = st.columns(2)
        if c1.button("Save edits", key=f"save_{d.slug}"):
            d.intro, d.sections, d.faq = intro, secs, faqs
            d.source = "ai" if d.source == "ai" else "edited"
            all_d = {x["slug"]: x for x in (load_json("drafts.json", []) or [])}
            all_d[d.slug] = d.__dict__
            save_json("drafts.json", list(all_d.values()))
            st.success("Saved. Re-open to refresh the blocker list.")
        if c2.button("Delete draft", key=f"del_{d.slug}"):
            save_json("drafts.json", [x for x in (load_json("drafts.json", []) or []) if x["slug"] != d.slug])
            st.rerun()

import requests
import streamlit as st
import streamlit.components.v1 as components

from src import flows, theme
from src.ui import control, engine, setup_page

s = setup_page("Premium Theme Studio", "🎨")
st.caption("A restrained, fast design system (no external fonts/scripts) applied through ONE scoped stylesheet. Preview first; it only goes live through an approved patch.")
t = theme.load_theme()

c1, c2, c3 = st.columns(3)
keys = list(theme.PALETTES)
palette = c1.selectbox("Palette", keys, index=keys.index(t["palette"]) if t["palette"] in keys else 0, format_func=lambda k: theme.PALETTES[k]["label"])
font = c2.selectbox("Headings", list(theme.FONTS), index=list(theme.FONTS).index(t["font"]) if t["font"] in theme.FONTS else 0)
enabled = c3.checkbox("Apply theme in patches", value=t["enabled"])
pal = theme.PALETTES[palette]
st.markdown("".join(f'<span style="display:inline-block;width:90px;height:44px;background:{pal[k]};color:#fff;border-radius:8px;margin:0 6px 6px 0;padding:4px 8px;font-size:12px">{k}<br>{pal[k]}</span>' for k in ("primary", "dark", "accent", "bg_alt")), unsafe_allow_html=True)

extra = st.text_area("Extra CSS (every selector must start with body.kg-premium)", t.get("extra_css", ""), height=140)
problems = theme.sanitize_css(extra) if extra.strip() else []
for p in problems:
    st.error(p)

if st.button("🤖 Designer agent: suggest extra CSS for the real site", disabled=engine() == "offline"):
    if control()["kill_switch"]:
        st.error("Kill switch is on.")
    else:
        try:
            html = requests.get(s.site_url, timeout=20, headers={"User-Agent": "KunergySEOAutopilot/1.0"}).text
            with st.spinner("Designer agent working..."):
                css, probs = flows.design_extra_css(html, {"palette": palette, "font": font}, engine())
            if probs:
                st.error("Rejected by the CSS safety check: " + "; ".join(probs[:4]))
            else:
                st.session_state["suggested_css"] = css
                st.success("Suggestion passed the safety check. Copy it into the box above to use it.")
                st.code(css, language="css")
        except Exception as e:
            st.error(str(e))

cfg = {"enabled": enabled, "palette": palette, "font": font, "extra_css": extra if not problems else ""}
css = theme.build_css(cfg)
if st.button("Save theme", type="primary", disabled=bool(problems)):
    theme.save_theme(cfg)
    st.success("Saved (download data/theme.yaml and commit it on Streamlit Cloud).")
with st.expander("Generated CSS"):
    st.code(css, language="css")
st.download_button("Download CSS", css, "kunergy-premium.css", "text/css")

st.subheader("Live preview of kunergy.com with this theme (nothing is saved or deployed)")
if st.button("Load preview"):
    try:
        html = requests.get(s.site_url, timeout=20, headers={"User-Agent": "KunergySEOAutopilot/1.0"}).text
        components.html(theme.preview_html(html, css, s.site_url), height=760, scrolling=True)
    except Exception as e:
        st.error(f"Could not load the live site: {e}")

import streamlit as st
import streamlit.components.v1 as components

from src.facts import load_facts
from src.flows import DEFAULT_OPTIONS, LOW_RISK_ONLY, build_patch, pr_body, publish_patch
from src.models import PageDraft
from src.storage import load_json, save_json
from src.tools import site_io
from src.tools.github_ops import GitHubError, GitHubOps
from src.ui import control, setup_page

s = setup_page("Approvals", "✅")
facts = load_facts()
st.caption("Load the site source, build the patch, review diffs + QA, then approve. Agents never push to your main branch: they open a Pull Request, or you download a ZIP.")

# ---------------- 1. source
src = st.radio("Site source", ["Upload site ZIP", "GitHub repository"], horizontal=True)
if src == "Upload site ZIP":
    up = st.file_uploader("ZIP of your website files (index.html, css/, images/...)", type=["zip"])
    if up and st.button("Load ZIP"):
        files, prefix = site_io.load_zip(up.getvalue())
        st.session_state.update(site_files=files, site_zip=up.getvalue(), site_prefix=prefix, site_src="zip")
else:
    if st.button("Fetch from GitHub"):
        try:
            ops = GitHubOps(s.github_token, s.site_repo, s.site_branch)
            st.session_state.update(site_files=ops.fetch_text_files(), site_zip=None, site_prefix="", site_src="github")
        except (GitHubError, Exception) as e:
            st.error(f"GitHub: {e}")
files = st.session_state.get("site_files")
if not files:
    st.info("Load your site files to continue. (Don't have them? Export from your host/cPanel, or ask your developer for the repo.)")
    st.stop()
st.success(f"Loaded {len(files)} text file(s) from {st.session_state.get('site_src')}; {sum(1 for p in files if p.endswith('.html'))} HTML page(s).")

# ---------------- 2. scope & options
scope = st.radio("Scope", ["All reviewed changes (SEO + content + premium theme)", "Low-risk fixes only (typos, alt text, canonical, sitemap...)"])
low_only = scope.startswith("Low-risk")
opts = dict(LOW_RISK_ONLY if low_only else DEFAULT_OPTIONS)
if not low_only:
    cols = st.columns(4)
    for col, k in zip(cols * 2, [k for k in DEFAULT_OPTIONS if k not in ("low_risk", "sitemap")]):
        opts[k] = col.checkbox(k, value=True, key=f"opt_{k}")
drafts = [PageDraft(**d) for d in (load_json("drafts.json", []) or [])]
use = st.multiselect("Drafts to include as new pages", [d.slug for d in drafts], default=[d.slug for d in drafts], disabled=low_only)

# ---------------- 3. build
if st.button("Build patch", type="primary"):
    patch = build_patch(files, [d for d in drafts if d.slug in use], facts, options=opts)
    st.session_state["patch"] = patch
    save_json("last_patch_summary.json", patch.summary())
patch = st.session_state.get("patch")
if not patch:
    st.stop()

sm = patch.summary()
c = st.columns(5)
for col, (k, v) in zip(c, sm.items()):
    col.metric(k.replace("_", " "), v)
if patch.qa.errors:
    st.error("QA gate: BLOCKED")
    for i in patch.qa.errors:
        st.write(f"❌ `{i.code}` {i.page}: {i.message}")
else:
    st.success("QA gate: passed")
if patch.qa.warnings:
    with st.expander(f"{len(patch.qa.warnings)} warning(s)"):
        for i in patch.qa.warnings:
            st.write(f"⚠️ `{i.code}` {i.page}: {i.message}")

st.subheader("Changes")
st.dataframe([c.__dict__ for c in patch.changes])
st.subheader("Diffs")
for path, diff in patch.diffs.items():
    with st.expander(path):
        lines = diff.splitlines()
        st.code("\n".join(lines[:400]) + ("\n... (truncated)" if len(lines) > 400 else ""), language="diff")
html_files = [p for p in patch.files if p.endswith(".html")]
if html_files:
    pick = st.selectbox("Preview a page (layout only; relative assets may not load in the preview)", html_files)
    components.html(patch.files[pick], height=620, scrolling=True)

# ---------------- 4. approve
st.subheader("Approve")
ok = st.checkbox("I have read every diff and QA item and every claim in the new pages is true.")
ctl = control()
d1, d2 = st.columns(2)
zip_bytes = site_io.export_zip(st.session_state.get("site_zip"), patch.files, st.session_state.get("site_prefix", "")) if patch.files else b""
d1.download_button("⬇️ Download patched ZIP", zip_bytes, "kunergy-site-patched.zip", "application/zip", disabled=not (ok and patch.qa.passed))
can_pr = st.session_state.get("site_src") == "github"
if d2.button("🚀 Open Pull Request" if not ctl["dry_run"] else "🧪 Dry run (save patch only)", disabled=not (ok and patch.qa.passed and (can_pr or ctl["dry_run"]))):
    try:
        ops = GitHubOps(s.github_token, s.site_repo, s.site_branch) if (can_pr and not ctl["dry_run"]) else None
        out = publish_patch(patch, ops=ops, dry_run=ctl["dry_run"], title="SEO Autopilot: " + ("low-risk fixes" if patch.low_risk_only else "SEO + content + theme"),
                            body=pr_body(patch), draft_pr=not (patch.low_risk_only and s.allow_automerge_low_risk))
        if out["pr_url"]:
            st.success(f"Pull request opened: {out['pr_url']}")
            if patch.low_risk_only and s.allow_automerge_low_risk and ops:
                st.info("Auto-merge of low-risk PRs is enabled by configuration.")
                st.write(ops.merge_pr_number(int(out["pr_url"].rstrip("/").split("/")[-1])))
        else:
            st.success(f"Dry run complete: patch saved to data/state/{out['saved']}. Turn off 'Dry run' in the sidebar to open a real PR.")
    except Exception as e:
        st.error(str(e))
if not can_pr:
    st.caption("PRs need the 'GitHub repository' source. With a ZIP, download the patched ZIP and upload it to your host (cPanel/FTP/Netlify...).")

import json

import requests
import streamlit as st

from src import flows
from src.facts import load_facts
from src.models import AuditReport
from src.storage import load_json
from src.tools.crawler import analyze_html
from src.ui import control, engine, setup_page

setup_page("Local SEO, CRO & Competitors", "📍")
facts = load_facts()
tab1, tab2, tab3 = st.tabs(["Conversion (CRO)", "Local & authority pack", "Competitor gaps"])

with tab1:
    audit = load_json("audit.json")
    report = AuditReport.from_dict(audit) if audit else None
    st.markdown(flows.CRO_FORM_SPEC)
    if report and engine() != "offline" and st.button("Add AI recommendations"):
        try:
            st.markdown(flows.cro_plan(report, facts, engine()).split("## Additional AI recommendations")[-1])
        except Exception as e:
            st.error(str(e))

with tab2:
    st.caption("Drafts only. A human posts and sends everything. Never use fake reviews or paid links.")
    if st.button("Generate pack"):
        try:
            st.session_state["pack"] = flows.local_pack_offline(facts) if engine() == "offline" else flows.local_pack_ai(facts, engine())
        except Exception as e:
            st.error(str(e))
    pack = st.session_state.get("pack")
    if pack:
        for k, v in pack.items():
            st.subheader(k.replace("_", " ").title())
            st.write(v) if isinstance(v, list) else st.code(v, language=None)
        st.download_button("Download pack (JSON)", json.dumps(pack, indent=2, ensure_ascii=False), "local_pack.json")

with tab3:
    st.caption("Paste competitor page URLs (one per line). We compare structure and proof signals; we never copy their text.")
    urls = [u.strip() for u in st.text_area("Competitor URLs", height=100).splitlines() if u.strip().startswith("http")]
    if urls and st.button("Analyze competitors"):
        rows = []
        for u in urls[:8]:
            try:
                r = requests.get(u, timeout=20, headers={"User-Agent": "KunergySEOAutopilot/1.0"})
                p = analyze_html(u, r.text, r.status_code)
                rows.append({"url": u, "title": p.title, "h1": " | ".join(p.h1), "h2s": p.h2_count, "words": p.word_count, "schema": ", ".join(sorted(set(p.jsonld_types))), "has_tel": p.has_tel, "has_whatsapp": p.has_whatsapp, "form_fields": p.max_form_fields})
            except Exception as e:
                rows.append({"url": u, "title": f"ERROR {e}"})
        st.session_state["comp_rows"] = rows
    rows = st.session_state.get("comp_rows")
    if rows:
        st.dataframe(rows)
        if engine() != "offline" and not control()["kill_switch"] and st.button("Ask the Competitor agent for gaps"):
            try:
                st.markdown(flows._ask("competitor", f"Competitor page signals (structure only): {rows}\nOur company facts: {flows.facts_for_prompt(facts)}\nList the 6 biggest gaps/opportunities for our pages (proof, FAQs, schema, CTAs, depth). Do not suggest copying text. Max 250 words.", engine()))
            except Exception as e:
                st.error(str(e))

import streamlit as st

from src import flows
from src.tools import gsc
from src.ui import control, engine, setup_page

s = setup_page("Weekly Report", "📈")
rows = None
src = st.radio("Data source", ["Upload Search Console CSV", "Search Console API"], horizontal=True)
if src == "Upload Search Console CSV":
    up = st.file_uploader("Performance export (Queries.csv)", type=["csv"])
    if up:
        rows = gsc.load_gsc_csv(up.getvalue())
else:
    st.caption("Needs GSC_CREDENTIALS (service-account JSON, added as a user in Search Console) and GSC_SITE_URL (e.g. sc-domain:kunergy.com).")
    days = st.slider("Days", 7, 90, 28)
    if st.button("Fetch from API"):
        try:
            st.session_state["gsc_rows"] = gsc.fetch_queries(s.gsc_site_url, s.gsc_credentials, days)
        except Exception as e:
            st.error(f"GSC API: {e}")
    rows = st.session_state.get("gsc_rows")

if not rows:
    st.info("Load data to build the report.")
    st.stop()
a = gsc.analyze(rows)
c = st.columns(4)
c[0].metric("Queries", a["queries"])
c[1].metric("Clicks", int(a["clicks"]))
c[2].metric("Impressions", int(a["impressions"]))
c[3].metric("Avg CTR %", a["avg_ctr"])
ai = ""
if engine() != "offline" and not control()["kill_switch"] and st.checkbox("Add AI recommendations (Reporter agent)"):
    try:
        ai = flows.weekly_report_ai(a, engine())
    except Exception as e:
        st.error(str(e))
md = flows.weekly_report_md(a, ai)
st.markdown(md)
st.download_button("Download report (Markdown)", md, "weekly_seo_report.md", "text/markdown")

import csv
import io

import streamlit as st

from src.storage import read_logs
from src.ui import setup_page

setup_page("Run Logs", "🧾")
logs = read_logs(1000)
if not logs:
    st.info("No activity yet.")
    st.stop()
kinds = sorted({l["kind"] for l in logs})
sel = st.multiselect("Kind", kinds, default=kinds)
rows = [l for l in logs if l["kind"] in sel]
st.dataframe(rows)
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=sorted({k for r in rows for k in r}))
w.writeheader()
w.writerows(rows)
st.download_button("Download CSV", buf.getvalue(), "run_logs.csv", "text/csv")
