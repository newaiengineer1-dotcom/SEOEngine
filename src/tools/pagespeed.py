"""Google PageSpeed Insights API v5 (free; an API key gives higher quota)."""
from __future__ import annotations

import requests

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run_pagespeed(url: str, strategy: str = "mobile", api_key: str = "", session=None) -> dict:
    params = [("url", url), ("strategy", strategy)] + [("category", c) for c in ("performance", "seo", "accessibility", "best-practices")]
    if api_key:
        params.append(("key", api_key))
    try:
        r = (session or requests).get(API, params=params, timeout=120)
        if r.status_code != 200:
            return {"error": f"PageSpeed API HTTP {r.status_code}: {r.text[:200]}"}
        lh = r.json().get("lighthouseResult", {})
        cats = lh.get("categories", {})
        audits = lh.get("audits", {})

        def score(k):
            v = (cats.get(k) or {}).get("score")
            return None if v is None else round(v * 100)

        def num(k):
            return (audits.get(k) or {}).get("numericValue")

        return {
            "url": url,
            "strategy": strategy,
            "performance": score("performance"),
            "seo": score("seo"),
            "accessibility": score("accessibility"),
            "best_practices": score("best-practices"),
            "lcp_ms": num("largest-contentful-paint"),
            "cls": num("cumulative-layout-shift"),
            "tbt_ms": num("total-blocking-time"),
            "error": None,
        }
    except Exception as exc:
        return {"error": str(exc)}
