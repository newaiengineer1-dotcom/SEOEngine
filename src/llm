"""Groq access: direct OpenAI-compatible REST client (with retry) + CrewAI LLM factory."""
from __future__ import annotations

import json
import re
import time

import requests

from .config import Settings, get_settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(Exception):
    pass


def llm_available(settings: Settings | None = None) -> bool:
    return bool((settings or get_settings()).groq_api_key)


def _bare(model: str) -> str:
    return model.split("/", 1)[1] if model.startswith("groq/") else model


def groq_chat(
    messages: list[dict],
    *,
    fast: bool = False,
    temperature: float = 0.3,
    max_tokens: int = 3000,
    json_mode: bool = False,
    retries: int = 4,
    session=None,
    settings: Settings | None = None,
) -> str:
    s = settings or get_settings()
    if not s.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set.")
    payload = {
        "model": _bare(s.groq_fast_model if fast else s.groq_model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {s.groq_api_key}", "Content-Type": "application/json"}
    http = session or requests
    for attempt in range(retries + 1):
        r = http.post(GROQ_URL, headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            try:
                wait = float(r.headers.get("retry-after", 0) or 0)
            except ValueError:
                wait = 0.0
            time.sleep(wait or min(2 ** attempt * 2, 30))
            continue
        raise LLMError(f"Groq API error {r.status_code}: {r.text[:300]}")
    raise LLMError("Groq API: retries exhausted.")


def extract_json(text: str):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except ValueError:
                continue
    raise LLMError("No valid JSON found in the model output.")


def get_crewai_llm(fast: bool = False, settings: Settings | None = None):
    s = settings or get_settings()
    if not s.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set.")
    try:
        from crewai import LLM
    except ImportError as exc:
        raise LLMError("crewai is not installed (pip install crewai).") from exc
    model = s.groq_fast_model if fast else s.groq_model
    if not model.startswith("groq/"):
        model = "groq/" + model
    return LLM(model=model, api_key=s.groq_api_key, temperature=0.3)
