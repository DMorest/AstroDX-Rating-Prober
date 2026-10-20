"""Shared HTTP session configuration for all outbound app requests."""
from __future__ import annotations

from urllib.parse import urlparse
import requests


SYSTEM_PROXY = "system"
DIRECT = "direct"
CUSTOM_PROXY = "custom"


def normalize_network_mode(mode: str | None) -> str:
    value = (mode or SYSTEM_PROXY).strip().casefold()
    aliases = {
        "system": SYSTEM_PROXY,
        "auto": SYSTEM_PROXY,
        "跟随系统代理": SYSTEM_PROXY,
        "系统代理": SYSTEM_PROXY,
        "direct": DIRECT,
        "直连": DIRECT,
        "直连（忽略代理）": DIRECT,
        "custom": CUSTOM_PROXY,
        "自定义": CUSTOM_PROXY,
        "自定义 http(s) 代理": CUSTOM_PROXY,
    }
    if value not in aliases:
        raise ValueError("未知联网模式：{}".format(mode))
    return aliases[value]


def make_session(mode: str = SYSTEM_PROXY, proxy_url: str | None = None) -> requests.Session:
    """Create a request session using system/env proxy, a direct route, or a custom HTTP(S) proxy.

    Direct/custom modes disable environmental proxy discovery to avoid hidden proxy settings
    overriding the route explicitly selected in the UI.
    """
    normalized = normalize_network_mode(mode)
    session = requests.Session()
    if normalized == DIRECT:
        session.trust_env = False
    elif normalized == CUSTOM_PROXY:
        session.trust_env = False
        value = (proxy_url or "").strip()
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("请填写有效的 HTTP(S) 代理地址，例如 http://127.0.0.1:7890")
        session.proxies.update({"http": value, "https": value})
    else:
        session.trust_env = True
    return session
