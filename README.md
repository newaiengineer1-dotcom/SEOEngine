# SEO Autopilot

A Streamlit control panel + multi-agent system (CrewAI on Groq) that **audits, plans, writes, restyles, QA-checks and (after your approval) ships**
SEO and premium-design improvements to https://www.company.com for direct lead generation.

> **Safety model:** AI drafts, deterministic code patches, a QA gate blocks bad output, and **a human approves** every release.
> Agents never push to your main branch: they open a *Pull Request* (or hand you a ZIP). Dry-run and a kill switch are built in.

---

## 1. About the current website (what we are patching)

Evidence from the live page: images are served from a plain `/images/` folder (not `/wp-content/`, `_next/`, or a Wix/Squarespace/Webflow/Shopify CDN),
file names like `png logo.png` and `icons8-facebook-48 (1).png`, a one-page layout with `#anchor` navigation and a text "☰" menu, hand-named form fields
(`Project_Inquiry`, `First_Name`), and all content present in the first HTML response (not a client-rendered React/Vue app).
**Conclusion: most likely a hand-coded static HTML/CSS/JS site, with no CMS or JS framework.** (Not provable from outside: confirm with *View Source* or the
Wappalyzer extension.) This is the easiest kind of site to patch: the app edits `.html` files and adds new folders like `uae/solar-installation-dubai/index.html`.

**How you deploy depends on your host:** GitHub Pages / Netlify / Cloudflare Pages / Vercel -> use the **GitHub repository** source and merge the PR.
cPanel / FTP / shared hosting -> use the **ZIP** source, download the patched ZIP and upload it.

## 2. Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt                            # or requirements-lite.txt (no CrewAI)
cp .env.example .env                                       # add GROQ_API_KEY (and APP_PASSWORD)
streamlit run app.py
python scripts/mini_runner.py                              # or: pip install -r requirements-dev.txt && pytest
```
No Groq key yet? Choose engine **offline** in the sidebar: everything works except AI writing.

## 3. Upload to GitHub and deploy on Streamlit Cloud

1. `bash scripts/push_to_github.sh seo-autopilot` (needs `git` + GitHub CLI), or create a **private** repo manually and `git push`.
2. https://share.streamlit.io -> **New app** -> pick the repo, branch `main`, main file `app.py`.
3. **Settings -> Secrets**: paste the values from `.streamlit/secrets.toml.example`. **Set `APP_PASSWORD`** (the app can open PRs on your site).
4. If the build is slow or fails on CrewAI, replace `requirements.txt` with the content of `requirements-lite.txt`; the `direct` engine runs the same Writer -> Reviewer flow without CrewAI.
5. GitHub token: create a **fine-grained** token limited to the *website* repo with Contents + Pull requests (read/write). Never a classic all-repo token.
6. Remember: Streamlit Cloud's disk is **ephemeral**. Download/commit `facts.yaml`, `theme.yaml`, `plan.json` and drafts you want to keep.

## 4. How the agents do the SEO and build the premium website (step by step)

| # | Step (app page) | Who does it | What happens | Human gate |
|---|---|---|---|---|
| 0 | **Facts Editor** | You | Fill `facts.yaml`: projects, certifications, brands, WhatsApp number. Empty = never claimed. | You |
| 1 | **Site Audit** | Auditor agent + crawler + PageSpeed | Crawls the live site; finds the single-page structure, weak title/H1, no alt text, typos, no schema/sitemap, long form, no click-to-call. Prioritized fix plan. | Read it |
| 2 | **Keyword Map** | Strategist agent | One primary keyword per page, UAE and Pakistan separate (`data/page_plan.yaml`, 14 pages). Upload a Search Console CSV to see striking-distance queries. | Edit/approve plan |
| 3 | **Content Queue** | Writer -> Reviewer crew | Drafts each page from `facts.yaml` only; the Reviewer deletes unsupported claims. `[NEEDS CLIENT FACT]` marks anything unknown. | You edit every draft |
| 4 | **Theme** | Designer agent + theme engine | A fast premium design system (palette, type scale, buttons, cards, form styling, sticky contact bar) as ONE scoped stylesheet; live preview of kunergy.com with it. | You choose/approve |
| 5 | **Approvals -> Build patch** | On-Page & Schema engineer (deterministic code) | *Low risk:* typos, alt text, lazy-load, canonical, Open Graph, copyright year, sitemap.xml, robots.txt. *High risk:* home title/meta/H1, JSON-LD (Organization + 2x LocalBusiness + Service/FAQ/Breadcrumb), sticky Call/WhatsApp/Quote bar, links to new pages, the new pages, premium theme. | - |
| 6 | **QA gate** | Compliance reviewer (code) | Blocks on: unsupported numbers/credentials/superlatives/prices, unfilled placeholders, keyword stuffing, duplicate pages, missing title/meta/H1/alt, invalid JSON-LD, unsafe CSS. Warns on broken links, lengths. | Fix blockers |
| 7 | **Approve & release** | Release Manager | Read the diffs, tick the checkbox, then **Open Pull Request** (GitHub source) or **Download patched ZIP**. "Low-risk only" scope is available for quick safe wins. | **You approve/merge** |
| 8 | After deploy | You + Local agent | Submit `sitemap.xml` and the new URLs in Search Console; claim Google Business Profile; **Local & CRO** page drafts GBP text, posts, review request, outreach email, citation checklist, form spec. | You send/post |
| 9 | **Reports** (weekly) | Reporter agent | Search Console CSV/API -> top queries, striking distance (pos 8-20), high-impression/low-CTR titles to rewrite, next actions. `weekly-audit.yml` re-audits every Monday. | Act on it |

**Mapping to the 30-day plan** (`docs/ROADMAP_AND_MASTER_PROMPT.md`): week 1 = steps 0-2 + Search Console/GA4/GBP setup; week 2 = steps 3-7 (pages + theme);
week 3 = proof, quote-form rebuild, local pack; week 4 = articles, links, steps 8-9 iteration.
Rankings for competitive terms take months: this builds the foundation and the lead-conversion machine; pair with a small Google Ads campaign for speed.

## 5. Agents (CrewAI roles, `src/agents.py`)
Auditor, Keyword & Intent Strategist, Competitor Analyst, Senior SEO Writer, Fact-Checking Reviewer, CRO Specialist, Local SEO Builder, Premium Web Designer, Reporter.
Writer + Reviewer run as a two-task sequential crew with context chaining (`engine = crewai`) or as two Groq calls (`engine = direct`).
Deterministic code (crawler, patcher, QA, schema, sitemap, theme CSS) does the actual file edits: LLMs never write HTML into your site directly.

## 6. Guardrails (by design)
- Claims come only from `facts.yaml`; numbers, certifications, "best/#1/guaranteed", prices are blocked unless in the facts.
- New pages are never overwritten; PRs are drafts by default; paths under `.github/` and non-text files are refused.
- AI-written CSS must be scoped under `body.kg-premium`, with no `@import`, external `url()`, or scripts.
- Re-serialising HTML keeps your attribute order and tag style so diffs stay small. Form option labels that contained typos are corrected: if your form backend matches those exact strings, check it.
- Search data comes from Search Console exports/API or PageSpeed API, not scraped Google results.
- Run Logs record every agent action. Kill switch disables AI + publishing.

## 7. Configuration reference
`GROQ_API_KEY`, `GROQ_MODEL` (verify IDs at console.groq.com), `GROQ_FAST_MODEL`, `GROQ_MAX_RPM`, `GITHUB_TOKEN`, `SITE_REPO`, `SITE_BRANCH`, `SITE_URL`,
`PAGESPEED_API_KEY`, `GSC_CREDENTIALS`, `GSC_SITE_URL`, `APP_PASSWORD`, `ALLOW_AUTOMERGE_LOW_RISK` (default false). See `.env.example`.

## 8. Project layout
```
app.py  pages/ (11 pages)            Streamlit UI
src/config.py storage.py facts.py    settings, state + logs, facts loader
src/llm.py agents.py flows.py        Groq client, CrewAI roles, pipeline
src/theme.py keywords.py             premium theme engine, page plan
src/tools/ crawler pagespeed html_patcher page_builder schema_builder sitemap facts_guard qa site_io github_ops gsc
data/ facts.yaml page_plan.yaml theme.yaml     editable inputs
scripts/ run_audit.py build_patch_cli.py push_to_github.sh mini_runner.py
tests/ (39 tests)   .github/workflows/ (CI + weekly audit)   docs/
```

## 9. What has and has not been verified
**Verified (automated tests, 39 passing, plus a CLI end-to-end run):** crawler/audit rules against a fixture modelled on company.com, HTML patcher (idempotent, order-preserving),
facts guard, QA gate, schema/sitemap/page builder, theme + CSS sanitizer, patch building and blocking, ZIP round-trip, Groq retry logic (mocked), GSC CSV analysis,
and every Streamlit page script executing against a stub (`tests/test_ui_smoke.py`).
**Not verified (built without network access or the packages):** a real `streamlit run` render, live CrewAI runs, live Groq/PageSpeed/Search Console API calls,
and real GitHub PR creation. Expect small API-version tweaks (CrewAI and Streamlit change quickly): start with *Connections -> test buttons*, engine `offline`/`direct`, and **Dry run ON**.

## 10. Troubleshooting
- *Groq 429*: lower `GROQ_MAX_RPM`; the client already backs off and retries. *Model not found*: update `GROQ_MODEL`.
- *CrewAI import/build errors*: use `requirements-lite.txt` and engine `direct`.
- *QA gate blocked*: open the red items; usually `[NEEDS CLIENT FACT]` placeholders or an unsupported number: edit the draft or add the fact to `facts.yaml`.
- *PR button disabled*: needs the GitHub source, QA passed, the approval box ticked, and Dry run OFF (otherwise it saves a dry-run patch).
