"""Online maimai icon/nameplate catalog and local image cache.

Catalog metadata is cached on disk so the UI doesn't repeatedly query LXNS.
Selected images are downloaded on demand and converted to PNG in the app cache.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import time
from typing import Any

import requests
from PIL import Image

from src.network import SYSTEM_PROXY, make_session

LXNS_API = "https://maimai.lxns.net/api/v0/maimai"
LXNS_ASSETS = "https://assets.lxns.net/maimai"
CATALOG_TTL_SECONDS = 24 * 60 * 60


def asset_cache_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / ".local" / "share"
    return base / "AstroDX-Rating-Prober" / "lxns-assets"


def _catalog_path(kind: str) -> Path:
    return asset_cache_root() / "catalogs" / (kind + ".json")


def _unwrap_catalog(payload: Any, kind: str) -> list[dict[str, Any]]:
    """Accept LXNS's public response envelope and tolerate minor schema variants."""
    value = payload
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    if isinstance(value, dict):
        for key in (kind + "s", kind, "items", "list", "results"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
    if not isinstance(value, list):
        raise RuntimeError("LXNS {} 目录返回的数据格式不符合预期。".format(kind))

    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id", item.get("asset_id", item.get("assetId")))
        try:
            asset_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if asset_id < 0 or asset_id in seen:
            continue
        seen.add(asset_id)
        name = str(item.get("name") or item.get("title") or item.get("label") or "").strip()
        if not name:
            name = ("头像" if kind == "icon" else "姓名框") + " #{}".format(asset_id)
        result.append({"id": asset_id, "name": name})
    if not result:
        raise RuntimeError("LXNS {} 目录中没有可用的 ID 项。".format(kind))
    result.sort(key=lambda entry: entry["id"])
    return result


def get_lxns_asset_catalog(
    kind: str,
    network_mode: str = SYSTEM_PROXY,
    proxy_url: str | None = None,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Read the cached catalog or refresh it from LXNS.

    `plate/list` is documented by LXNS. `icon/list` is attempted for icon names; if
    that endpoint isn't available on the deployed API, an actionable error is raised
    instead of silently fabricating a catalog.
    """
    if kind not in ("icon", "plate"):
        raise ValueError("不支持的 maimai 资源类型：{}".format(kind))
    cache_path = _catalog_path(kind)
    cached: list[dict[str, Any]] | None = None
    cached_at = 0.0
    try:
        raw_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(raw_cache, dict) and isinstance(raw_cache.get("items"), list):
            cached = _unwrap_catalog(raw_cache["items"], kind)
            cached_at = float(raw_cache.get("saved_at", 0) or 0)
    except (OSError, ValueError, TypeError, RuntimeError):
        cached = None

    if cached and not force_refresh and time.time() - cached_at < CATALOG_TTL_SECONDS:
        return cached

    endpoints = [
        LXNS_API + "/{}/list".format(kind),
        LXNS_API + "/{}s/list".format(kind),
    ]
    errors = []
    try:
        with make_session(network_mode, proxy_url) as session:
            for url in endpoints:
                try:
                    response = session.get(
                        url,
                        timeout=(5, 12),
                        headers={"User-Agent": "AstroDX-Rating-Prober/1.0", "Accept": "application/json"},
                    )
                    response.raise_for_status()
                    items = _unwrap_catalog(response.json(), kind)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path = cache_path.with_suffix(".tmp")
                    temp_path.write_text(
                        json.dumps({"saved_at": time.time(), "items": items}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    temp_path.replace(cache_path)
                    return items
                except (requests.RequestException, ValueError, RuntimeError) as exc:
                    errors.append("{}: {}".format(url.rsplit("/", 2)[-2], exc))
    except ValueError as exc:
        errors.append(str(exc))

    if cached:
        return cached
    detail = "；".join(errors[-2:]) or "未知错误"
    raise RuntimeError(
        "无法获取 LXNS {} 目录。{}。请检查网络设置，或点击刷新后重试。".format(
            "头像" if kind == "icon" else "姓名框", detail
        )
    )


def ensure_lxns_asset_image(
    kind: str,
    asset_id: int,
    network_mode: str = SYSTEM_PROXY,
    proxy_url: str | None = None,
) -> str:
    """Download one selected asset into a persistent PNG cache and return its path."""
    if kind not in ("icon", "plate"):
        raise ValueError("不支持的 maimai 资源类型：{}".format(kind))
    try:
        asset_id = int(asset_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("maimai 资源 ID 无效。") from exc
    if asset_id < 0:
        raise ValueError("maimai 资源 ID 无效。")

    cache_path = asset_cache_root() / kind / "{}.png".format(asset_id)
    if cache_path.is_file():
        try:
            with Image.open(cache_path) as existing:
                existing.verify()
            return str(cache_path)
        except (OSError, ValueError):
            try:
                cache_path.unlink()
            except OSError:
                pass

    # LXNS's icon asset URL is used by existing open-source clients. The plain PNG
    # alternative is retained for deployments that don't support the !webp suffix.
    urls = [
        "{}/{}/{}.png!webp".format(LXNS_ASSETS, kind, asset_id),
        "{}/{}/{}.png".format(LXNS_ASSETS, kind, asset_id),
    ]
    errors = []
    try:
        with make_session(network_mode, proxy_url) as session:
            for url in urls:
                try:
                    response = session.get(
                        url, timeout=(5, 15),
                        headers={"User-Agent": "AstroDX-Rating-Prober/1.0"},
                    )
                    response.raise_for_status()
                    with Image.open(BytesIO(response.content)) as source:
                        converted = source.convert("RGBA")
                        converted.load()
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_path = cache_path.with_suffix(".tmp.png")
                    converted.save(temp_path, format="PNG", optimize=True)
                    temp_path.replace(cache_path)
                    return str(cache_path)
                except (requests.RequestException, OSError, ValueError) as exc:
                    errors.append(str(exc))
    except ValueError as exc:
        errors.append(str(exc))
    raise RuntimeError(
        "下载 LXNS {} #{} 失败：{}".format(
            "头像" if kind == "icon" else "姓名框", asset_id, "；".join(errors[-2:]) or "未知错误"
        )
    )


def local_level_options(static_dir: str | Path, prefix: str) -> list[str]:
    """Enumerate local UI assets by filename (e.g. UI_FBR_Class_00.png)."""
    if prefix not in ("UI_DNM_DaniPlate_", "UI_FBR_Class_"):
        raise ValueError("不支持的本地段位资源类型：{}".format(prefix))
    folder = Path(static_dir) / "mai" / "pic"
    pattern = prefix + "*.png"
    files = sorted(folder.glob(pattern))
    return [item.name for item in files if item.is_file()]
