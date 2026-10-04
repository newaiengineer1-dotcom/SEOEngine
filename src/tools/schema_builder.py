"""JSON-LD builders. Only emits what facts.yaml supports; never invents ratings or reviews."""
from __future__ import annotations

import re


def clean_phone(p: str | None) -> str | None:
    if not p:
        return None
    return "+" + re.sub(r"\D", "", p) if p.strip().startswith("+") else re.sub(r"\D", "", p)


def _prune(d):
    if isinstance(d, dict):
        return {k: _prune(v) for k, v in d.items() if v not in (None, "", [], {})}
    if isinstance(d, list):
        return [_prune(x) for x in d if x not in (None, "", [], {})]
    return d


def organization(facts: dict) -> dict:
    c = facts.get("company", {})
    base = c.get("website", "").rstrip("/")
    return _prune(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": c.get("brand"),
            "url": base + "/",
            "slogan": (c.get("tagline") or "").rstrip("!") or None,
            "foundingDate": str(c.get("founded")) if c.get("founded") else None,
            "description": " ".join((c.get("description") or "").split()) or None,
            "email": (facts.get("entities") or [{}])[0].get("email"),
            "sameAs": [v for v in (facts.get("social") or {}).values() if v],
        }
    )


def local_business(entity: dict, facts: dict) -> dict:
    base = facts.get("company", {}).get("website", "").rstrip("/")
    return _prune(
        {
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            "name": entity.get("legal_name"),
            "url": f"{base}/{entity.get('hub_path', '')}",
            "telephone": clean_phone(entity.get("phone")),
            "email": entity.get("email"),
            "address": {
                "@type": "PostalAddress",
                "streetAddress": entity.get("street"),
                "addressLocality": entity.get("locality"),
                "addressRegion": entity.get("region"),
                "addressCountry": entity.get("country_code"),
            },
            "parentOrganization": {"@type": "Organization", "name": facts.get("company", {}).get("brand")},
            "sameAs": [v for v in (facts.get("social") or {}).values() if v],
        }
    )


def service(name: str, description: str, provider: str, area: str | None, url: str) -> dict:
    return _prune(
        {
            "@context": "https://schema.org",
            "@type": "Service",
            "name": name,
            "description": description,
            "provider": {"@type": "Organization", "name": provider},
            "areaServed": area,
            "url": url,
        }
    )


def faq_page(faq: list[dict]) -> dict | None:
    items = [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
        for f in faq
        if f.get("q") and f.get("a")
    ]
    if not items:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items}


def breadcrumb(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)
        ],
    }
