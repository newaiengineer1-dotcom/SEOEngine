"""Shared Streamlit helpers: page setup, password gate, sidebar controls."""
from __future__ import annotations

import hmac

import streamlit as st

from .config import get_settings
from .flows import ENGINES
from .llm import llm_available
from .storage import get_control, set_control


def setup_page(title: str, icon: str = "☀️"):
    st.set_page_config(page_title=f"{title} · Kunergy SEO Autopilot", page_icon=icon, layout="wide")
    s = get_settings()
    if s.app_password and not st.session_state.get("auth_ok"):
        st.title("🔒 Kunergy SEO Autopilot")
        pw = st.text_input("Password", type="password")
        if pw and hmac.compare_digest(pw, s.app_password):
            st.session_state["auth_ok"] = True
            st.rerun()
        elif pw:
            st.error("Wrong password.")
        st.stop()
    _sidebar(s)
    st.title(f"{icon} {title}")
    return s


def _sidebar(s) -> None:
    sb = st.sidebar
    sb.header("Controls")
    ctl = get_control()
    dry = sb.checkbox("Dry run (never push to GitHub)", value=ctl["dry_run"], help="Recommended until you trust the output.")
    kill = sb.checkbox("🛑 Kill switch (disable AI + publishing)", value=ctl["kill_switch"])
    if dry != ctl["dry_run"] or kill != ctl["kill_switch"]:
        set_control(dry_run=dry, kill_switch=kill)
    default_engine = "direct" if llm_available(s) else "offline"
    st.session_state.setdefault("engine", default_engine)
    sb.selectbox("AI engine", ENGINES, key="engine", help="offline = no AI (scaffolds). direct = Groq REST. crewai = multi-agent crew on Groq.")
    sb.divider()
    sb.caption("Connections")
    sb.write(("✅" if s.groq_api_key else "⚠️") + " Groq key")
    sb.write(("✅" if s.github_token and s.site_repo else "⚠️") + " GitHub token + repo")
    sb.write(("✅" if s.pagespeed_api_key else "➖") + " PageSpeed key (optional)")
    if not s.app_password:
        sb.warning("No APP_PASSWORD set: anyone with the app link can use it. Set one before deploying.")


def engine() -> str:
    return st.session_state.get("engine", "offline")


def control() -> dict:
    return get_control()
