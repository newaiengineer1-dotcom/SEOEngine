"""facts.yaml = the single source of truth for every claim the system may publish."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from .config import DATA_DIR

FACTS_PATH = DATA_DIR / "facts.yaml"
PLAN_PATH = DATA_DIR / "page_plan.yaml"


def load_facts(path: Path | None = None) -> dict:
    p = path or FACTS_PATH
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def parse_facts_text(text: str) -> dict:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("facts.yaml must be a YAML mapping at the top level.")
    return data


def save_facts_text(text: str) -> None:
    parse_facts_text(text)  # validate first
    FACTS_PATH.write_text(text, encoding="utf-8")


def years_in_business(facts: dict, today: date | None = None) -> int | None:
    founded = (facts.get("company") or {}).get("founded")
    if not founded:
        return None
    return (today or date.today()).year - int(founded)


def entity(facts: dict, key: str) -> dict | None:
    for e in facts.get("entities", []) or []:
        if e.get("key") == key:
            return e
    return None


def facts_for_prompt(facts: dict) -> str:
    """Compact JSON of the facts the LLM is allowed to use."""
    keep = {k: facts.get(k) for k in ("company", "entities", "services", "proof", "allowed_claims")}
    keep["years_in_business"] = years_in_business(facts)
    return json.dumps(keep, ensure_ascii=False, indent=1)


def load_plan_yaml(path: Path | None = None) -> list[dict]:
    p = path or PLAN_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("pages", [])
