
"""Shared HTTP session configuration for all outbound app requests."""
from __future__ import annotations

import sys
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


def _windows_system_proxy() -> dict[str, str]:
    """Read the manually configured Windows system proxy."""
    if sys.platform != "win32":
        return {}

    try:
        import winreg

        key_path = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Internet Settings"
        )

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path
        ) as key:
            try:
                enabled, _ = winreg.QueryValueEx(
                    key, "ProxyEnable"
                )
            except OSError:
                enabled = 0

            try:
                server, _ = winreg.QueryValueEx(
                    key, "ProxyServer"
                )
            except OSError:
                server = ""

        if not enabled or not isinstance(server, str):
            return {}

        server = server.strip()
        if not server:
            return {}

        # Windows can store either a shared address such as
        # 127.0.0.1:7890 or protocol-specific addresses such as
        # http=127.0.0.1:7890;https=127.0.0.1:7890.
        entries: dict[str, str] = {}

        if "=" in server:
            for part in server.split(";"):
                if "=" not in part:
                    continue

                protocol, address = part.split("=", 1)
                protocol = protocol.strip().lower()
                address = address.strip()

                if protocol in ("http", "https") and address:
                    entries[protocol] = address

            # If Windows specifies only one proxy endpoint, use it
            # for both protocols. HTTPS can use an HTTP CONNECT proxy.
            if entries:
                shared = entries.get("http") or entries.get("https")
                if shared:
                    entries.setdefault("http", shared)
                    entries.setdefault("https", shared)
        else:
            entries = {
                "http": server,
                "https": server,
            }

        proxies: dict[str, str] = {}

        for protocol, address in entries.items():
            # A normal Clash Verge HTTP/mixed listener usually uses
            # http:// even when the destination website uses HTTPS.
            candidate = (
                address if "://" in address
                else "http://" + address
            )
            parsed = urlparse(candidate)

            if (
                parsed.scheme in ("http", "https")
                and parsed.netloc
            ):
                proxies[protocol] = candidate

        return proxies

    except (OSError, ImportError, ValueError):
        return {}


def make_session(
    mode: str = SYSTEM_PROXY,
    proxy_url: str | None = None,
) -> requests.Session:
    """Create a session using system/env, direct, or custom proxy.

    On Windows, prefer the proxy configured in Windows Internet
    Settings, which Clash Verge's System Proxy toggle normally sets.
    If unavailable, fall back to requests environment proxy discovery.
    """
    normalized = normalize_network_mode(mode)
    session = requests.Session()

    if normalized == DIRECT:
        # Ignore HTTP_PROXY / HTTPS_PROXY environment variables.
        session.trust_env = False

    elif normalized == CUSTOM_PROXY:
        # Explicit user configuration takes priority.
        session.trust_env = False

        value = (proxy_url or "").strip()
        parsed = urlparse(value)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
        ):
            raise ValueError(
                "请填写有效的 HTTP(S) 代理地址，例如 "
                "http://127.0.0.1:7890"
            )

        session.proxies.update({
            "http": value,
            "https": value,
        })

    else:
        windows_proxies = _windows_system_proxy()

        if windows_proxies:
            # Use the Windows/Clash Verge proxy rather than stale
            # environment variables that might point elsewhere.
            session.trust_env = False
            session.proxies.update(windows_proxies)
        else:
            # Preserve the original behavior as a fallback.
            session.trust_env = True

    return session
