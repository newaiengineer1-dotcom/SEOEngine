from tests.helpers import facts
from src.models import PageDraft
from src.tools import facts_guard as fg
from src.tools import qa

F = facts()


def test_numbers_and_credentials():
    bad = fg.unsupported_claims("We completed 500 projects and are ISO certified, saving 40%.", F)
    joined = " ".join(bad)
    assert "500 projects" in joined and "certified" in joined.lower() and "40%" in joined
    assert fg.unsupported_claims("Kunergy was founded in 2014 and serves Dubai.", F) == []
    assert fg.unsupported_claims("More than 5 years of experience.", F) == []  # <= years in business


def test_credentials_allowed_when_in_facts():
    f2 = {**F, "proof": {**F["proof"], "certifications": ["ISO 9001"]}}
    assert not any("certif" in p for p in fg.unsupported_claims("We are ISO 9001 certified.", f2))


def test_superlatives_and_best_practices():
    assert fg.unsupported_claims("The best solar company in Dubai, guaranteed.", F)
    assert fg.unsupported_claims("We follow best practices on every site.", F) == []


def test_prices():
    assert fg.unsupported_claims("Systems from AED 9,999.", F)


def test_placeholders_block():
    d = PageDraft(slug="x/", market="UAE", service="s", title="t", meta_description="m", h1="h", intro="[NEEDS CLIENT FACT: intro]")
    assert any(i.code == "needs_client_fact" for i in fg.check_draft(d, F))


def test_qa_catches_problems():
    html = "<html><head></head><body><main><h1>A</h1><h1>B</h1><img src='x.png'><a href='/missing/'>x</a></main></body></html>"
    codes = {i.code for i in qa.qa_page("p/index.html", html, generated=True, facts=F, all_paths={"index.html"})}
    assert {"no_title", "no_meta", "h1_count", "img_alt", "broken_internal_link"} <= codes


def test_keyword_stuffing_and_duplicates():
    stuffed = " ".join(["solar panels dubai"] + ["solar"] * 40 + ["filler words about nothing important at all"] * 20)
    assert qa.keyword_stuffing(stuffed)
    page = "<html><head><title>Some decent page title here</title><meta name='description' content='" + "d" * 100 + "'></head><body><main><h1>H</h1><p>" + ("unique sentence number one about roofs and wiring and planning. " * 12) + "</p></main></body></html>"
    rep = qa.qa_site({"a/index.html": page, "b/index.html": page}, generated={"a/index.html", "b/index.html"}, all_paths={"a/index.html", "b/index.html"}, facts=F)
    assert any(i.code == "duplicate_content" for i in rep.issues)
