import io
import json
import zipfile

from tests.helpers import facts
from src import llm
from src.keywords import default_page_plan, match_queries_to_pages, plan_from_rows
from src.llm import LLMError, extract_json, groq_chat
from src.tools import gsc, page_builder, schema_builder as sb, site_io
from src.tools.github_ops import safe_path
from src.tools.sitemap import build_sitemap, ensure_robots_sitemap
from tests.helpers import filled_draft

F = facts()


def test_page_plan_is_sane():
    plan = default_page_plan()
    slugs = [p.slug for p in plan]
    assert len(slugs) == len(set(slugs)) == 14
    for p in plan:
        assert len(p.title) <= 62 and 70 <= len(p.meta_description) <= 160, p.slug
        assert not p.parent or p.parent in slugs
        assert p.primary_keyword
    rows = [{"slug": "a/", "market": "UAE", "secondary_keywords": "x, y", "enabled": False}]
    assert plan_from_rows(rows)[0].secondary_keywords == ["x", "y"] and plan_from_rows(rows)[0].enabled is False


def test_match_queries():
    plan = default_page_plan()
    out = match_queries_to_pages([{"query": "solar panel installation dubai", "clicks": 1, "impressions": 2, "ctr": 0, "position": 9}], plan)
    assert out[0]["best_page"] == "uae/solar-installation-dubai/"


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": [1,2]}\n```') == {"a": [1, 2]}
    assert extract_json('blah blah {"x": "y"} trailing') == {"x": "y"}
    try:
        extract_json("no json here")
        raise AssertionError
    except LLMError:
        pass


def test_groq_retries_then_succeeds():
    from src.config import Settings

    class R:
        def __init__(self, code, body=None, headers=None):
            self.status_code, self._b, self.headers, self.text = code, body, headers or {}, "x"

        def json(self):
            return self._b

    class S:
        calls = 0

        def post(self, *a, **k):
            S.calls += 1
            return R(429, headers={"retry-after": "0"}) if S.calls < 3 else R(200, {"choices": [{"message": {"content": "hello"}}]})

    s = Settings("k", "groq/m", "groq/f", "", "", "main", "https://x", "", "", "", "", 20, 25, False)
    old = llm.time.sleep
    llm.time.sleep = lambda _: None
    try:
        assert groq_chat([{"role": "user", "content": "hi"}], session=S(), settings=s) == "hello"
        assert S.calls == 3
    finally:
        llm.time.sleep = old
    try:
        groq_chat([], settings=Settings("", "m", "f", "", "", "main", "", "", "", "", "", 20, 25, False))
        raise AssertionError
    except LLMError as e:
        assert "GROQ_API_KEY" in str(e)


def test_gsc_csv_and_analysis():
    csv_bytes = "Top queries,Clicks,Impressions,CTR,Position\nsolar dubai,5,1000,0.5%,9.2\nev charger uae,0,40,0%,15\n".encode("utf-8-sig")
    rows = gsc.load_gsc_csv(csv_bytes)
    assert rows[0]["ctr"] == 0.5 and rows[1]["position"] == 15
    a = gsc.analyze(rows)
    assert a["clicks"] == 5 and len(a["striking_distance"]) == 2


def test_zip_roundtrip_keeps_binaries_and_prefix():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("site-main/index.html", "<html></html>")
        z.writestr("site-main/img/a.png", b"\x89PNG\x00\x01")
        z.writestr("site-main/.git/config", "x")
    files, prefix = site_io.load_zip(buf.getvalue())
    assert prefix == "site-main/" and list(files) == ["index.html"]
    out = site_io.export_zip(buf.getvalue(), {"index.html": "<html>new</html>", "sitemap.xml": "<urlset/>"}, prefix)
    z = zipfile.ZipFile(io.BytesIO(out))
    assert z.read("site-main/index.html") == b"<html>new</html>"
    assert z.read("site-main/img/a.png") == b"\x89PNG\x00\x01"
    assert "site-main/sitemap.xml" in z.namelist()


def test_safe_path():
    assert safe_path("index.html") and safe_path("uae/x/index.html")
    assert not safe_path("../x.html") and not safe_path("/etc/passwd") and not safe_path(".github/workflows/a.yml") and not safe_path("img/a.png")


def test_schema_and_sitemap():
    org = sb.organization(F)
    assert org["name"] == "Kunergy" and org["foundingDate"] == "2014" and "aggregateRating" not in org
    lb = sb.local_business(F["entities"][0], F)
    assert lb["address"]["addressCountry"] == "AE" and lb["telephone"] == "+971504254087"
    assert sb.faq_page([]) is None
    sm = build_sitemap("https://x.com", ["index.html", "a/index.html"])
    assert "<loc>https://x.com/</loc>" in sm and "<loc>https://x.com/a/</loc>" in sm
    assert ensure_robots_sitemap("User-agent: *\n", "https://x.com").endswith("Sitemap: https://x.com/sitemap.xml\n")


def test_page_builder_escapes_and_emits_valid_jsonld():
    d = filled_draft("uae/solar-installation-dubai/")
    d.intro = "Hello <script>alert(1)</script> world"
    html = page_builder.render_page(d, F, nav_links=[("Home", "/")])
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    import re

    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    assert len(blocks) == 3 and all(json.loads(b)["@context"] == "https://schema.org" for b in blocks)
