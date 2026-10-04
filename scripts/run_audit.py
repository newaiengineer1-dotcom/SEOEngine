"""Headless audit (used by the weekly GitHub Action).

    python scripts/run_audit.py --url https://www.kunergy.com --limit 25 --out reports
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import flows  # noqa: E402
from src.tools.crawler import run_audit  # noqa: E402
from src.tools.pagespeed import run_pagespeed  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("SITE_URL", "https://www.kunergy.com"))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--out", default="reports")
    ap.add_argument("--no-pagespeed", action="store_true")
    ap.add_argument("--fail-on-critical", action="store_true")
    a = ap.parse_args()
    ps = None if a.no_pagespeed else run_pagespeed(a.url, api_key=os.getenv("PAGESPEED_API_KEY", ""))
    report = run_audit(a.url, limit=a.limit, pagespeed=ps)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    (out / "fix_plan.md").write_text(flows.audit_plan_offline(report), encoding="utf-8")
    crit = sum(1 for i in report.issues if i.severity == "critical")
    print(f"{len(report.pages)} page(s), {len(report.issues)} issue(s), {crit} critical. Wrote {out}/audit.json and fix_plan.md")
    return 1 if (a.fail_on_critical and crit) else 0


if __name__ == "__main__":
    sys.exit(main())
