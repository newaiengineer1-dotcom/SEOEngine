"""Settings loader. Reads environment variables, .env, then Streamlit secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATE_DIR = DATA_DIR / "state"

try:  # optional
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return _get(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    groq_fast_model: str
    github_token: str
    site_repo: str  # "owner/repo"
    site_branch: str
    site_url: str
    pagespeed_api_key: str
    gsc_credentials: str  # JSON string or path to service-account JSON
    gsc_site_url: str  # e.g. "sc-domain:kunergy.com"
    app_password: str
    max_rpm: int
    crawl_limit: int
    allow_automerge_low_risk: bool


def get_settings() -> Settings:
    return Settings(
        groq_api_key=_get("GROQ_API_KEY"),
        groq_model=_get("GROQ_MODEL", "groq/llama-3.3-70b-versatile"),
        groq_fast_model=_get("GROQ_FAST_MODEL", "groq/llama-3.1-8b-instant"),
        github_token=_get("GITHUB_TOKEN"),
        site_repo=_get("SITE_REPO"),
        site_branch=_get("SITE_BRANCH", "main"),
        site_url=_get("SITE_URL", "https://www.kunergy.com").rstrip("/"),
        pagespeed_api_key=_get("PAGESPEED_API_KEY"),
        gsc_credentials=_get("GSC_CREDENTIALS"),
        gsc_site_url=_get("GSC_SITE_URL"),
        app_password=_get("APP_PASSWORD"),
        max_rpm=int(_get("GROQ_MAX_RPM", "20") or 20),
        crawl_limit=int(_get("CRAWL_LIMIT", "25") or 25),
        allow_automerge_low_risk=_bool("ALLOW_AUTOMERGE_LOW_RISK", False),
    )
