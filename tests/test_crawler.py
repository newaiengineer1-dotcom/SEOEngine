from tests.helpers import fixture
from src.tools.crawler import analyze_html, build_issues, crawl


class Resp:
    def __init__(self, text, status=200, ctype="text/html", url=""):
        self.text, self.status_code, self.headers, self.url = text, status, {"content-type": ctype}, url


class FakeSession:
    def __init__(self, pages):
        self.pages, self.headers = pages, {}

    def get(self, url, **kw):
        if url.endswith("/robots.txt"):
            return Resp("", 404, "text/plain", url)
        if url in self.pages:
            return Resp(self.pages[url], 200, "text/html", url)
        return Resp("nope", 404, "text/html", url)


def test_analyze_fixture():
    p = analyze_html("https://www.kunergy.com/", fixture("kunergy_home.html"))
    assert p.title == "Kunergy"
    assert p.h1[0] == "WELCOME TO KUNERGY" and len(p.h1) == 2
    assert p.images_total == p.images_missing_alt and p.images_total >= 10
    assert p.copyright_year == 2024
    assert p.max_form_fields == 8
    assert p.anchor_links >= 4
    assert any("Commerical" in t for t in p.typos)
    assert not p.has_tel and not p.has_whatsapp


def test_issues_match_real_findings():
    p = analyze_html("https://www.kunergy.com/", fixture("kunergy_home.html"))
    codes = {i.code for i in build_issues([p], {"https": True, "robots_txt": False, "sitemap_xml": False})}
    for expected in ["single_page_site", "weak_title", "no_meta_description", "no_canonical", "missing_alt", "typos",
                     "stale_copyright", "no_click_to_contact", "long_form", "no_schema", "no_proof_pages", "no_sitemap", "no_robots", "multiple_h1"]:
        assert expected in codes, expected


def test_crawl_follows_internal_links_and_respects_limit():
    home = '<html><head><title>Home page title here</title></head><body><a href="/a">A</a><a href="/b">B</a><a href="https://other.com/x">x</a></body></html>'
    sess = FakeSession({"https://site.test/": home, "https://site.test/a": "<html><body><h1>A</h1></body></html>", "https://site.test/b": "<html><body><h1>B</h1></body></html>"})
    pages = crawl("https://site.test", limit=10, delay=0, session=sess)
    assert {p.url for p in pages} == {"https://site.test/", "https://site.test/a", "https://site.test/b"}
    assert len(crawl("https://site.test", limit=2, delay=0, session=sess)) == 2
