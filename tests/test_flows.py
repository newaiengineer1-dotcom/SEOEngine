from tests.helpers import TempState, facts, filled_draft, fixture
from src import flows
from src.flows import LOW_RISK_ONLY, build_patch, offline_draft, publish_patch
from src.keywords import default_page_plan

F = facts()
SITE = {"index.html": fixture("kunergy_home.html")}
SLUGS = ["uae/solar-installation-dubai/", "pakistan/solar-installation-lahore/"]


def test_offline_drafts_are_blocked_by_qa():
    spec = default_page_plan()[2]
    d = offline_draft(spec, F)
    assert d.source == "offline" and "[NEEDS CLIENT FACT" in d.intro + d.sections[0]["body"]
    p = build_patch(SITE, [d], F)
    assert not p.qa.passed
    assert any(i.code == "needs_client_fact" for i in p.qa.errors)
    with TempState():
        try:
            publish_patch(p, ops=None, dry_run=True, title="t", body="b")
            raise AssertionError("publish should have been blocked")
        except RuntimeError as e:
            assert "QA gate" in str(e)


def test_full_patch_with_filled_drafts_passes_qa():
    p = build_patch(SITE, [filled_draft(s) for s in SLUGS], F)
    assert p.qa.passed, [f"{i.code}:{i.message}" for i in p.qa.errors]
    for path in ["index.html", "sitemap.xml", "robots.txt", "uae/solar-installation-dubai/index.html", "pakistan/solar-installation-lahore/index.html"]:
        assert path in p.files, path
    home = p.files["index.html"]
    from datetime import date

    assert "Commerical" not in home.split("<body", 1)[1] and f"© {date.today().year}" in home
    assert 'href="/uae/solar-installation-dubai/"' in home
    assert "tel:+971504254087" in home and "tel:+923001950006" in home
    assert "LocalBusiness" in home and "Organization" in home
    sm = p.files["sitemap.xml"]
    assert "https://www.kunergy.com/uae/solar-installation-dubai/" in sm and sm.count("<url>") == 3
    assert "Sitemap: https://www.kunergy.com/sitemap.xml" in p.files["robots.txt"]
    page = p.files["uae/solar-installation-dubai/index.html"]
    assert "<h1>Solar Panel Installation in Dubai &amp; the UAE</h1>" in page
    assert 'rel="canonical" href="https://www.kunergy.com/uae/solar-installation-dubai/"' in page
    assert "css/style.css" in page  # reuses the existing stylesheet
    assert p.summary()["high_risk_changes"] > 0 and p.diffs["index.html"].startswith("--- a/index.html")


def test_low_risk_only_patch_has_no_high_risk_changes():
    p = build_patch(SITE, [filled_draft(s) for s in SLUGS], F, options=LOW_RISK_ONLY)
    assert p.low_risk_only and p.changes
    assert all(c.risk == "low" for c in p.changes), [c for c in p.changes if c.risk == "high"]
    assert "uae/solar-installation-dubai/index.html" not in p.files
    assert "kg-contact-bar" not in p.files["index.html"]


def test_build_is_idempotent_on_its_own_output():
    p1 = build_patch(SITE, [filled_draft(s) for s in SLUGS], F)
    site2 = {**SITE, **p1.files}
    p2 = build_patch(site2, [filled_draft(s) for s in SLUGS], F)
    assert "index.html" not in p2.files, p2.diffs.get("index.html", "")[:500]
    assert "sitemap.xml" not in p2.files and "robots.txt" not in p2.files
    assert any(i.code == "page_exists" for i in p2.qa.issues)  # never overwrites existing pages


def test_publish_dry_run_saves_and_kill_switch_blocks():
    from src import storage

    p = build_patch(SITE, [filled_draft(s) for s in SLUGS], F)
    with TempState() as tmp:
        out = publish_patch(p, ops=None, dry_run=True, title="t", body=flows.pr_body(p))
        assert out["mode"] == "dry_run" and (tmp / out["saved"]).exists()
        storage.set_control(kill_switch=True)
        try:
            publish_patch(p, ops=None, dry_run=True, title="t", body="b")
            raise AssertionError("kill switch should block")
        except RuntimeError as e:
            assert "Kill switch" in str(e)


def test_publish_opens_pr_through_ops_when_not_dry_run():
    class FakeOps:
        def open_pr(self, files, prefix, title, body, draft=True):
            self.args = (sorted(files), prefix, draft)
            return "https://github.com/x/y/pull/1"

    p = build_patch(SITE, [filled_draft(s) for s in SLUGS], F)
    ops = FakeOps()
    with TempState():
        out = publish_patch(p, ops=ops, dry_run=False, title="t", body="b")
    assert out["pr_url"].endswith("/pull/1") and ops.args[2] is True


def test_contact_items_by_market():
    assert [l for l, _ in flows.contact_items("uae/x/index.html", F, False)] == ["Call", "Get a Quote"]
    assert [l for l, _ in flows.contact_items("index.html", F, True)] == ["Call UAE", "Call Pakistan", "Get a Quote"]
    f2 = {**F, "entities": [{**F["entities"][0], "whatsapp": "+971 50 000 0000"}, F["entities"][1]]}
    assert any(l == "WhatsApp" for l, _ in flows.contact_items("uae/x/", f2, False))


def test_local_pack_and_reports():
    pack = flows.local_pack_offline(F)
    assert len(pack["gbp_posts"]) == 4 and len(pack["gbp_services_to_list"]) == 13
    from src.tools.gsc import analyze

    rows = [{"query": "solar dubai", "clicks": 3, "impressions": 500, "ctr": 0.6, "position": 6.0}, {"query": "ev charger dubai", "clicks": 0, "impressions": 90, "ctr": 0, "position": 12.0}]
    md = flows.weekly_report_md(analyze(rows))
    assert "Striking distance" in md and "ev charger dubai" in md and "solar dubai" in md


def test_premium_theme_is_scoped_safe_and_idempotent():
    from src import theme

    css = theme.build_css({"palette": "midnight_amber"})
    assert theme.sanitize_css(css, require_scope=False) == []
    assert "body.kg-premium" in css and "#12395F".lower() in css.lower() and "@import" not in css
    assert theme.sanitize_css("body.kg-premium a{color:red}") == []
    assert theme.sanitize_css("a{color:red}") and theme.sanitize_css("body.kg-premium{background:url(https://x.com/a.png)}")
    assert theme.sanitize_css("@import url(x);body.kg-premium a{}")
    p = build_patch(SITE, [filled_draft(s) for s in SLUGS], F, theme_cfg={"enabled": True, "palette": "solar_green"})
    assert p.qa.passed and "assets/kunergy-premium.css" in p.files
    assert 'class="kg-premium"' in p.files["index.html"] and "assets/kunergy-premium.css?v=" in p.files["index.html"]
    assert "kg-premium" in p.files["uae/solar-installation-dubai/index.html"]
    p2 = build_patch({**SITE, **p.files}, [filled_draft(s) for s in SLUGS], F, theme_cfg={"enabled": True, "palette": "solar_green"})
    assert "assets/kunergy-premium.css" not in p2.files and "index.html" not in p2.files
    off = build_patch(SITE, [], F, theme_cfg={"enabled": False})
    assert "assets/kunergy-premium.css" not in off.files


def test_theme_inventory_and_preview():
    from src import theme

    inv = theme.inventory('<html><head><link rel="stylesheet" href="a.css"></head><body><div class="hero big"><section id="x"></section></div></body></html>')
    assert inv["stylesheets"] == ["a.css"] and "hero" in inv["top_classes"] and "x" in inv["ids"]
    out = theme.preview_html("<html><head></head><body><p>x</p></body></html>", "body.kg-premium{}", "https://www.kunergy.com")
    assert '<base href="https://www.kunergy.com/"' in out and "kg-premium" in out
