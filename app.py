"""Kunergy SEO Autopilot: Streamlit entry point."""
import streamlit as st

from src.storage import load_json
from src.ui import setup_page

s = setup_page("Kunergy SEO Autopilot", "☀️")

st.markdown(
    """
**What this does:** audits https://www.kunergy.com, builds a keyword-to-page plan, drafts service pages from *your verified facts*,
patches the site (typos, alt text, schema, sitemap, contact bar, new pages), runs a QA gate, and opens a **Pull Request** (or gives you a ZIP)
for a human to approve. Nothing goes live without your approval.

**Workflow (use the pages in the left menu, in order):**
1. **Connections**: test Groq / GitHub / PageSpeed.
2. **Facts Editor**: fill `facts.yaml` with real, provable company facts (projects, certifications, WhatsApp number...).
3. **Site Audit**: crawl the live site and see prioritized fixes.
4. **Keyword Map**: review the page plan (and upload a Search Console export).
5. **Content Queue**: generate and edit page drafts; resolve every `[NEEDS CLIENT FACT]`.
6. **Approvals**: load the site source (ZIP or GitHub), build the patch, read diffs and QA, then approve.
7. **Local & CRO**, **Reports**, **Run Logs**.
"""
)
audit = load_json("audit.json")
drafts = load_json("drafts.json", []) or []
c1, c2, c3 = st.columns(3)
c1.metric("Last audit issues", len(audit["issues"]) if audit else "–")
c2.metric("Drafts in queue", len(drafts))
c3.metric("Engine", st.session_state.get("engine", "offline"))
st.info("State is stored in `data/state/`. On Streamlit Community Cloud the disk is **ephemeral**: use the download buttons and commit anything you want to keep.")
