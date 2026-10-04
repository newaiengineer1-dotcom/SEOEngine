"""Tiny JSON state store + JSONL run log.

NOTE: Streamlit Community Cloud has an ephemeral disk. State survives reruns but not redeploys/restarts.
Use the Download buttons, or commit exported files to the repo, for anything you must keep.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import STATE_DIR


def _default(o: Any):
    if is_dataclass(o):
        return asdict(o)
    return str(o)


def _path(name: str) -> Path:
    p = STATE_DIR / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_json(name: str, obj: Any) -> None:
    _path(name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default), encoding="utf-8")


def load_json(name: str, default: Any = None) -> Any:
    p = _path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return default


# ---------- control flags (kill switch / dry run) ----------
def get_control() -> dict:
    d = load_json("control.json", {}) or {}
    return {"kill_switch": bool(d.get("kill_switch", False)), "dry_run": bool(d.get("dry_run", True))}


def set_control(**kwargs: bool) -> dict:
    c = get_control()
    c.update({k: bool(v) for k, v in kwargs.items() if k in c})
    save_json("control.json", c)
    return c


# ---------- run log ----------
def log_event(kind: str, message: str, **data: Any) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind, "message": message}
    rec.update(data)
    with _path("runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=_default) + "\n")


def read_logs(limit: int = 500) -> list[dict]:
    p = _path("runs.jsonl")
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return list(reversed(out))
