"""Load a site from a ZIP and export patched ZIPs (text files only are patched; binaries pass through)."""
from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

from ..constants import TEXT_EXT


def _strip_root(names: list[str]) -> str:
    """If every entry lives under one top-level folder (typical GitHub ZIP), return that prefix."""
    tops = {n.split("/", 1)[0] for n in names if n and not n.startswith("__MACOSX")}
    if len(tops) == 1 and all("/" in n for n in names if n and not n.startswith("__MACOSX")):
        return tops.pop() + "/"
    return ""


def load_zip(data: bytes, max_bytes: int = 2_000_000) -> tuple[dict[str, str], str]:
    """Return ({path: text}, root_prefix). Skips binaries, hidden dirs and oversized files."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = [i.filename for i in zf.infolist() if not i.is_dir()]
    prefix = _strip_root(names)
    files: dict[str, str] = {}
    for info in zf.infolist():
        if info.is_dir() or info.filename.startswith("__MACOSX"):
            continue
        rel = info.filename[len(prefix):] if prefix else info.filename
        parts = PurePosixPath(rel).parts
        if not rel or any(p.startswith(".") for p in parts) or ".." in parts:
            continue
        if PurePosixPath(rel).suffix.lower() not in TEXT_EXT or info.file_size > max_bytes:
            continue
        try:
            files[rel] = zf.read(info).decode("utf-8")
        except UnicodeDecodeError:
            continue
    return files, prefix


def export_zip(original_zip: bytes | None, changed: dict[str, str], prefix: str = "") -> bytes:
    """Copy every original entry except changed ones, then add changed/new files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        written = set()
        if original_zip:
            src = zipfile.ZipFile(io.BytesIO(original_zip))
            for info in src.infolist():
                rel = info.filename[len(prefix):] if prefix and info.filename.startswith(prefix) else info.filename
                if rel in changed:
                    continue
                out.writestr(info, src.read(info))
                written.add(info.filename)
        for rel, content in changed.items():
            out.writestr(prefix + rel, content)
    return buf.getvalue()
