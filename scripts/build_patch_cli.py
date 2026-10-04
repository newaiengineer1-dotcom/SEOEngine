"""Headless patch builder.

    python scripts/build_patch_cli.py --site-zip site.zip --out site-patched.zip [--drafts drafts.json] [--low-risk-only]

`drafts.json` is the file exported from the Content Queue (data/state/drafts.json). Exits 1 if the QA gate fails.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.facts import load_facts  # noqa: E402
from src.flows import LOW_RISK_ONLY, build_patch  # noqa: E402
from src.models import PageDraft  # noqa: E402
from src.tools import site_io  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--drafts")
    ap.add_argument("--low-risk-only", action="store_true")
    a = ap.parse_args()
    raw = pathlib.Path(a.site_zip).read_bytes()
    files, prefix = site_io.load_zip(raw)
    drafts = [PageDraft(**d) for d in json.loads(pathlib.Path(a.drafts).read_text())] if a.drafts else []
    patch = build_patch(files, drafts, load_facts(), options=LOW_RISK_ONLY if a.low_risk_only else None)
    print(json.dumps(patch.summary(), indent=2))
    for i in patch.qa.errors:
        print(f"ERROR {i.code} {i.page}: {i.message}")
    if not patch.qa.passed:
        return 1
    pathlib.Path(a.out).write_bytes(site_io.export_zip(raw, patch.files, prefix))
    print(f"Wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
