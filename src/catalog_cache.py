"""Persistent local cache for fetched public song catalogues."""
from __future__ import annotations
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "catalog_cache"


def cache_key(source: str) -> str:
    """Return a stable, filesystem-safe cache key for a source label."""
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", source.strip()).strip("_").lower()
    return key or "catalog"


def save_catalog(source: str, rows: list[dict], cache_dir: Path | None = None) -> Path:
    """Atomically save normalized catalogue rows and metadata as UTF-8 JSON."""
    directory = Path(cache_dir) if cache_dir else CACHE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{cache_key(source)}.json"
    payload = {
        "schema_version": 2,
        "source": source,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def load_catalog(source: str, cache_dir: Path | None = None) -> tuple[list[dict], dict[str, Any]] | None:
    """Load a saved catalogue; return None for absent or invalid cache files."""
    directory = Path(cache_dir) if cache_dir else CACHE_DIR
    path = directory / f"{cache_key(source)}.json"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        rows = payload.get("rows")
        if payload.get("schema_version") != 2 or payload.get("source") != source or not isinstance(rows, list) or not rows:
            return None
        if not all(isinstance(row, dict) for row in rows):
            return None
        return rows, {"saved_at": payload.get("saved_at"), "row_count": len(rows), "path": str(path)}
    except (OSError, ValueError, TypeError):
        return None
