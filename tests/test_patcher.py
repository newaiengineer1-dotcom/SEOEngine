import json

from tests.helpers import facts, fixture
from src.tools import html_patcher as hp
from src.tools.text import soup_of

F = facts()
KW = dict(year=2026, brand="Kunergy", alt_rules=F["alt_text_rules"], canonical_base="https://www.kunergy.com")


def test_typos_fixed_but_scripts_untouched():
    soup = soup_of(fixture("kunergy_home.html"))
    n = hp.fix_typos(soup)
    out = str(soup)
    assert n >= 5
    assert "Commerical, Industrial" not in out and "Electric Vehicles (EV)" in out
    assert "Kunegy" not in out.split("<body>")[1]
    assert 'var x = "Commerical stays untouched in scripts"' in out


def test_alt_text_rules():
    soup = soup_of(fixture("kunergy_home.html"))
    named, deco = hp.fix_alt_text(soup, "Kunergy", F["alt_text_rules"])
    alts = {i["src"].split("/")[-1]: i["alt"] for i in soup.find_all("img")}
    assert alts["png logo.png"] == "Kunergy logo"
    assert alts["icons8-facebook-48 (1).png"] == "Kunergy on Facebook"
    assert alts["RES.png"] == "Renewable energy solutions"
    assert alts["bg1.jpg"] == "" and deco == 3
    assert all(i.has_attr("alt") for i in soup.find_all("img"))


def test_apply_is_idempotent_and_reports_risk():
    html = fixture("kunergy_home.html")
    seo = F["home_seo"]
    kwargs = dict(KW, title=seo["title"], meta_description=seo["meta_description"], h1=seo["h1"],
                  jsonld=[("organization", {"@context": "https://schema.org", "@type": "Organization", "name": "Kunergy"})],
                  contact_items=[("Call", "tel:+971504254087"), ("Get a Quote", "#contact")],
                  service_links=[("Solar", "/uae/solar-installation-dubai/")])
    new, ch = hp.apply_page_fixes(html, "index.html", **kwargs)
    kinds = {c.kind: c.risk for c in ch}
    assert kinds["typo_fix"] == "low" and kinds["alt_text"] == "low" and kinds["copyright_year"] == "low"
    assert kinds["title"] == "high" and kinds["schema"] == "high" and kinds["contact_bar"] == "high"
    assert "© 2026" in new and "<title>Solar, EV Charging" in new
    again, ch2 = hp.apply_page_fixes(new, "index.html", **kwargs)
    assert ch2 == [] and again == new
    assert new.count('id="kg-contact-bar"') == 1 and new.count('id="kg-service-links"') == 1


def test_jsonld_is_valid_json():
    soup = soup_of("<html><head></head><body></body></html>")
    assert hp.inject_jsonld(soup, {"@type": "Organization", "name": "A & B <c>"}, "k")
    assert not hp.inject_jsonld(soup, {"@type": "Organization", "name": "A & B <c>"}, "k")
    tag = soup.find("script", attrs={"type": "application/ld+json"})
    assert json.loads(tag.string)["name"] == "A & B <c>"


def test_service_links_inserted_before_footer():
    soup = soup_of(fixture("kunergy_home.html"))
    hp.inject_service_links(soup, [("A", "/a/")])
    assert soup.find(id="kg-service-links").find_next_sibling().name == "footer"


def test_canonical_url():
    assert hp.canonical_url("index.html", "https://x.com/") == "https://x.com/"
    assert hp.canonical_url("uae/a/index.html", "https://x.com") == "https://x.com/uae/a/"
    assert hp.canonical_url("about.html", "https://x.com") == "https://x.com/about.html"


def test_no_change_returns_original():
    html = "<!DOCTYPE html><html lang='en'><head><meta name='viewport' content='x'><title>T</title></head><body><p>hi</p></body></html>"
    out, ch = hp.apply_page_fixes(html, "x.html", year=2026, low_risk=False)
    assert out == html and ch == []


def test_attribute_order_and_void_style_preserved():
    html = '<!DOCTYPE html><html><head><meta name="viewport" content="x"><title>T</title></head><body><img src="a.png" class="z" id="y"><p>Commerical</p></body></html>'
    out, ch = hp.apply_page_fixes(html, "x.html", year=2026, brand="Kunergy", low_risk=True)
    assert '<img src="a.png" class="z" id="y"' in out  # not re-sorted to class/id/src
    assert "/>" not in out  # HTML5 style kept
    xhtml = '<html><head><meta name="viewport" content="x" /><title>T</title></head><body><br /><p>Commerical</p></body></html>'
    out2, _ = hp.apply_page_fixes(xhtml, "x.html", year=2026, low_risk=True)
    assert "<br/>" in out2 and "Commercial" in out2
