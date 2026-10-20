"""Decode AstroDX cache files and normalize chart score records."""
from __future__ import annotations
import json
import zlib
from pathlib import Path
from typing import Any

DIFFICULTIES = {
    1: "BEGINNER", 2: "BASIC", 3: "ADVANCED", 4: "EXPERT",
    5: "MASTER", 6: "Re:MASTER", 7: "UTAGE",
}

class CacheParseError(ValueError):
    pass

def decode_cache_bytes(raw: bytes) -> dict[str, Any]:
    """Decode a cache payload. Current Android cache commonly uses raw DEFLATE."""
    candidates: list[bytes] = []
    # AstroDX 2.0.0.rc.7 maintainer notes describe DEFLATE; raw DEFLATE has no zlib header.
    for wbits in (-zlib.MAX_WBITS, zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            candidates.append(zlib.decompress(raw, wbits))
        except zlib.error:
            pass
    # Some versions/wrappers may prefix a small header; try a limited offset range.
    if not candidates:
        for offset in range(1, min(33, len(raw))):
            try:
                decoded = zlib.decompress(raw[offset:], -zlib.MAX_WBITS)
                if decoded.lstrip().startswith(b"{"):
                    candidates.append(decoded)
                    break
            except zlib.error:
                continue
    for decoded in candidates:
        try:
            obj = json.loads(decoded.decode("utf-8-sig"))
            if isinstance(obj, dict) and isinstance(obj.get("level_metadata"), dict):
                return obj
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise CacheParseError(
        "无法解码这个 cache 文件。请确认它来自最新版AstroDX，且版本支持 DEFLATE 导出；"
        "不同操作系统版本可能使用不同格式。原文件不会被修改。"
    )

def parse_cache(path_or_bytes: str | Path | bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    obj = decode_cache_bytes(raw)
    rows: list[dict[str, Any]] = []
    for song_key, meta in obj.get("level_metadata", {}).items():
        if not isinstance(meta, dict):
            continue
        title = str(meta.get("title") or song_key)
        for diff in meta.get("difficulties", []) or []:
            if not isinstance(diff, dict):
                continue
            stats = diff.get("stats") or {}
            try:
                ach = float(stats.get("achievementRate") or 0)
            except (TypeError, ValueError):
                ach = 0.0
            diff_id = diff.get("id")
            try:
                diff_id = int(diff_id)
            except (TypeError, ValueError):
                diff_id = -1
            rows.append({
                "title": title,
                "cache_key": str(song_key),
                "difficulty": DIFFICULTIES.get(diff_id, f"UNKNOWN_{diff_id}"),
                "difficulty_id": diff_id,
                "level_text": str(diff.get("value") or ""),
                "achievement": ach,
                "dx_score": int(stats.get("dxScore") or 0),
                "clear_type": int(stats.get("clearType") or 0),
                "plays": int(stats.get("clearedPlays") or 0),
                "complete_plays": int(stats.get("completePlays") or 0),
                "notes": int(stats.get("totalNotesCount") or 0),
                "good": int(stats.get("goodCount") or 0),
                "great": int(stats.get("greatCount") or 0),
                "perfect": int(stats.get("perfectCount") or 0),
                "critical": int(stats.get("criticalCount") or 0),
                "chart_hash": str(diff.get("hash") or ""),
            })
    return obj, rows
