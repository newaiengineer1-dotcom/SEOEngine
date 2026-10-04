"""Search Console data: CSV export parser (recommended) and optional API fetch."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta


def _num(v) -> float:
    s = str(v or "0").replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_gsc_csv(data: bytes) -> list[dict]:
    """Parse a Search Console performance export (Queries.csv or Pages.csv)."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        low = {k.strip().lower(): v for k, v in r.items() if k}
        key = next((low[k] for k in ("top queries", "query", "queries", "top pages", "page", "pages") if k in low), None)
        if key is None:
            continue
        rows.append(
            {
                "query": key,
                "clicks": _num(low.get("clicks")),
                "impressions": _num(low.get("impressions")),
                "ctr": _num(low.get("ctr")),
                "position": _num(low.get("position")),
            }
        )
    return rows


def fetch_queries(site_url: str, credentials: str, days: int = 28, row_limit: int = 500) -> list[dict]:
    """Needs a service account added as a user in Search Console. site_url e.g. 'sc-domain:kunergy.com'."""
    from google.oauth2 import service_account  # lazy: optional dependency
    from googleapiclient.discovery import build

    info = json.loads(credentials) if credentials.strip().startswith("{") else json.load(open(credentials))
    creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    end = date.today() - timedelta(days=2)
    body = {"startDate": (end - timedelta(days=days)).isoformat(), "endDate": end.isoformat(), "dimensions": ["query"], "rowLimit": row_limit}
    resp = svc.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return [
        {"query": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"], "ctr": r["ctr"] * 100, "position": r["position"]}
        for r in resp.get("rows", [])
    ]


def analyze(rows: list[dict]) -> dict:
    tot_clicks = sum(r["clicks"] for r in rows)
    tot_imp = sum(r["impressions"] for r in rows)
    striking = sorted([r for r in rows if 8 <= r["position"] <= 20 and r["impressions"] >= 20], key=lambda r: -r["impressions"])[:15]
    low_ctr = sorted([r for r in rows if r["impressions"] >= 100 and r["ctr"] < 2.0 and r["position"] <= 10], key=lambda r: -r["impressions"])[:15]
    return {
        "queries": len(rows),
        "clicks": tot_clicks,
        "impressions": tot_imp,
        "avg_ctr": round(100 * tot_clicks / tot_imp, 2) if tot_imp else 0.0,
        "top_by_clicks": sorted(rows, key=lambda r: -r["clicks"])[:10],
        "striking_distance": striking,
        "low_ctr_top10": low_ctr,
    }
