"""Fetch and normalize public maimai DX song catalogues.

Only public song/chart metadata is fetched; no player account or score API is used.
"""
from __future__ import annotations
import requests
from src.network import make_session, SYSTEM_PROXY

WATERFISH_URL = "https://www.diving-fish.com/api/maimaidxprober/music_data"
LXNS_URL = "https://maimai.lxns.net/api/v0/maimai/song/list"
SALTMETA_URL = "https://meta.salt.realtvop.top/meta.next.json"
DIFFS = ["BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER", "UTAGE"]
SALT_DIFFICULTIES = {0: "BASIC", 1: "ADVANCED", 2: "EXPERT", 3: "MASTER", 4: "Re:MASTER", 10: "UTAGE"}

class CatalogFetchError(RuntimeError):
    pass

def _get_json(url: str, params: dict | None = None, network_mode: str = SYSTEM_PROXY, proxy_url: str | None = None):
    try:
        with make_session(network_mode, proxy_url) as session:
            response = session.get(url, params=params, timeout=25, headers={"User-Agent": "AstroDX-B50/0.12"})
            response.raise_for_status()
            return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CatalogFetchError("无法获取曲库（联网模式：{}）：{}".format(network_mode, exc)) from exc

def fetch_waterfish(network_mode: str = SYSTEM_PROXY, proxy_url: str | None = None) -> list[dict]:
    """Diving-Fish public music_data; version is the source's basic_info.from label."""
    data = _get_json(WATERFISH_URL, network_mode=network_mode, proxy_url=proxy_url)
    if not isinstance(data, list):
        raise CatalogFetchError("水鱼 music_data 返回格式不是数组")
    rows = []
    for song in data:
        if not isinstance(song, dict):
            continue
        title = song.get("title")
        ds = song.get("ds") or []
        levels = song.get("level") or []
        ids = song.get("cids") or []
        song_type = str(song.get("type") or "")
        basic = song.get("basic_info") or {}
        version = str(basic.get("from") or "未知版本")
        chart_stats = song.get("charts") or []
        for idx, constant in enumerate(ds):
            if constant is None or idx >= len(DIFFS) or idx >= len(levels):
                continue
            note_data = chart_stats[idx].get("notes") if idx < len(chart_stats) and isinstance(chart_stats[idx], dict) else None
            total_notes = sum(int(v or 0) for v in note_data) if isinstance(note_data, (list, tuple)) else 0
            rows.append({
                "title": title, "difficulty": DIFFS[idx], "constant": constant,
                "song_id": song.get("id", ""), "chart_id": ids[idx] if idx < len(ids) else "",
                "song_type": song_type, "version": version,
                "level_text": str(levels[idx]), "total_notes": total_notes, "source": "水鱼",
            })
    if not rows:
        raise CatalogFetchError("水鱼曲库未返回可用谱面记录")
    return rows

def fetch_lxns(network_mode: str = SYSTEM_PROXY, proxy_url: str | None = None) -> list[dict]:
    """Lxns public song list; map numeric version IDs to their display titles."""
    payload = _get_json(LXNS_URL, params={"notes": "false"}, network_mode=network_mode, proxy_url=proxy_url)
    if not isinstance(payload, dict) or not isinstance(payload.get("songs"), list):
        raise CatalogFetchError("落雪 song/list 返回格式不符合预期")
    version_names = {}
    for version in payload.get("versions", []) or []:
        if isinstance(version, dict):
            label = str(version.get("title") or version.get("name") or version.get("version") or "未知版本")
            for key in (version.get("version"), version.get("id")):
                if key is not None:
                    version_names[key] = label
    rows = []
    for song in payload["songs"]:
        if not isinstance(song, dict) or song.get("disabled"):
            continue
        title = song.get("title")
        song_version = song.get("version")
        version = version_names.get(song_version, str(song_version if song_version is not None else "未知版本"))
        difficulties = song.get("difficulties") or {}
        for chart_type in ("standard", "dx"):
            for chart in difficulties.get(chart_type, []) or []:
                if not isinstance(chart, dict):
                    continue
                try:
                    idx = int(chart.get("difficulty"))
                    constant = float(chart.get("level_value"))
                except (TypeError, ValueError):
                    continue
                if idx < 0 or idx >= len(DIFFS):
                    continue
                # A chart's own debut version is more accurate when provided.
                chart_version = chart.get("version")
                chart_version_label = version_names.get(chart_version, str(chart_version)) if chart_version is not None else version
                rows.append({
                    "title": title, "difficulty": DIFFS[idx], "constant": constant,
                    "song_id": song.get("id", ""), "chart_id": "",
                    "song_type": chart_type.upper(), "version": chart_version_label,
                    "level_text": str(chart.get("level") or ""), "source": "落雪",
                })
    if not rows:
        raise CatalogFetchError("落雪曲库未返回可用谱面记录")
    return rows


def fetch_saltmeta(region: str = "jp", network_mode: str = SYSTEM_PROXY, proxy_url: str | None = None) -> list[dict]:
    """Fetch SaltMeta region-aware chart metadata (jp / intl / cn / us)."""
    if region not in ("jp", "intl", "cn", "us"):
        raise CatalogFetchError("SaltMeta 地区参数无效")
    payload = _get_json(SALTMETA_URL, network_mode=network_mode, proxy_url=proxy_url)
    if not isinstance(payload, dict) or not isinstance(payload.get("musics"), list):
        raise CatalogFetchError("SaltMeta 返回格式不符合预期；请稍后重试或改用其他曲库")
    rows = []
    for music in payload.get("musics", []):
        if not isinstance(music, dict):
            continue
        for chart in music.get("charts", []) or []:
            if not isinstance(chart, dict):
                continue
            difficulty_id = chart.get("difficulty")
            difficulty = SALT_DIFFICULTIES.get(difficulty_id)
            if not difficulty:
                continue
            regions = chart.get("regions") or {}
            region_data = regions.get(region)
            if not isinstance(region_data, dict):
                continue
            try:
                constant = float(region_data.get("internalLevel"))
            except (TypeError, ValueError):
                continue
            version = region_data.get("version", "未知版本")
            if region == "cn" and isinstance(version, (int, float)):
                version = "DX" + str(int(version))
            rows.append({
                "title": music.get("title", ""),
                "difficulty": difficulty,
                "constant": constant,
                "song_id": str(music.get("id", "")),
                "chart_id": "",
                "song_type": str(chart.get("type", "")).upper(),
                "version": str(version),
                # SaltMeta's display level (e.g. 13+, 14) is distinct from internalLevel.
                # Keeping it is essential: AstroDX cache stores this same display label.
                "level_text": str(chart.get("level") or ""),
                "total_notes": ((chart.get("noteCounts") or {}).get("total", 0)
                                if isinstance(chart.get("noteCounts"), dict) else 0),
                "artist": music.get("artist", ""),
                "category": music.get("category", ""),
                "cover_id": str(music.get("id", "")),
                "note_designer": chart.get("noteDesigner", ""),
                "region": region,
                "source": "SaltMeta",
            })
    if not rows:
        raise CatalogFetchError("SaltMeta 没有返回所选地区的谱面数据；可尝试切换地区或曲库")
    return rows
