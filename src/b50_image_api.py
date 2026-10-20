"""Adapter for the JiETNG session-image endpoint used by its B50 image renderer.

The endpoint only receives the selected B50 fields when the user explicitly clicks
its export button. The AstroDX cache itself is never sent.
"""
from __future__ import annotations

from typing import Any
import requests
from src.network import make_session, SYSTEM_PROXY

SESSION_IMAGE_URL = "https://jietng.matsuk1.com/api/web/session-image"


def score_icon(achievement: float) -> str:
    """Map achievement to the rank-icon identifiers used by the image endpoint."""
    try:
        ach = float(achievement)
    except (TypeError, ValueError):
        ach = 0.0
    thresholds = (
        (100.5, "sssp"), (100.0, "sss"), (99.5, "ssp"), (99.0, "ss"),
        (98.0, "sp"), (97.0, "s"), (94.0, "aaa"), (90.0, "aa"),
        (80.0, "a"), (75.0, "bbb"), (70.0, "bb"), (60.0, "b"),
        (50.0, "c"), (0.0, "d"),
    )
    for threshold, icon in thresholds:
        if ach >= threshold:
            return icon
    return "d"


def build_session_image_payload(
    records: list[dict[str, Any]], total_rating: int, version: str = "jp"
) -> dict[str, Any]:
    """Build a payload accepted by POST /api/web/session-image."""
    if version not in ("jp", "intl"):
        raise ValueError("图片接口只支持 jp 或 intl 模板")
    best = []
    for record in records[:50]:
        difficulty = str(record.get("difficulty") or "master").strip().casefold()
        if difficulty == "re:master":
            difficulty = "remaster"
        song_type_value = str(record.get("song_type") or "").strip().casefold()
        chart_type = "dx" if song_type_value == "dx" else "standard"
        try:
            achievement = float(record.get("achievement") or 0)
        except (TypeError, ValueError):
            achievement = 0.0
        try:
            dx_score = int(record.get("dx_score") or 0)
        except (TypeError, ValueError):
            dx_score = 0
        best.append({
            "name": str(record.get("title") or "Unknown song"),
            "difficulty": difficulty,
            "type": chart_type,
            "score": "{:.4f}%".format(achievement),
            "dx_score": str(dx_score),
            "score_icon": score_icon(achievement),
        })
    return {
        "version": version,
        "cmd_type": "best50",
        "command": "",
        "timezone": 9 if version == "jp" else 8,
        "profile": {"name": "AstroDX Player", "rating": str(int(total_rating))},
        "records": {"best": best},
    }


def request_session_image(payload: dict[str, Any], timeout: int = 30, network_mode: str = SYSTEM_PROXY, proxy_url: str | None = None) -> tuple[bytes, str, str]:
    """Call the image endpoint and return (bytes, MIME type, file extension)."""
    try:
        with make_session(network_mode, proxy_url) as session:
            response = session.post(
                SESSION_IMAGE_URL,
                json=payload,
                timeout=timeout,
                headers={"User-Agent": "AstroDX-B50/0.12", "Accept": "image/png,image/jpeg,application/json"},
            )
    except requests.RequestException as exc:
        raise RuntimeError("无法连接 B50 图片接口：{}".format(exc)) from exc
    if not response.ok:
        detail = response.text[:300].strip()
        allow = response.headers.get("allow", "").strip()
        if response.status_code == 405:
            method_note = "；HTTP 405 表示服务端或中间代理拒绝 POST 请求，不代表 JSON 内容一定错误"
            if allow:
                method_note += "（Allow: {}）".format(allow)
        else:
            method_note = ""
        raise RuntimeError("B50 图片接口返回 HTTP {}{}{}".format(response.status_code, method_note, ": " + detail if detail else ""))
    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime in ("image/png", "image/jpeg", "image/webp"):
        if not response.content:
            raise RuntimeError("B50 图片接口返回了空图片")
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
        return response.content, mime, extension
    detail = response.text[:400].strip()
    if mime == "application/json":
        try:
            data = response.json()
            detail = str(data.get("message") or data.get("error") or data.get("detail") or detail)
        except ValueError:
            pass
    raise RuntimeError("接口未返回 PNG/JPEG/WebP 图片（{}）{}".format(mime or "未知类型", ": " + detail if detail else ""))
