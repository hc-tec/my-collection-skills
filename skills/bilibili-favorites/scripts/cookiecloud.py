#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
CookieCloud helper (decrypt + domain cookie extraction).

Designed for skill scripts that need to reuse browser cookies without pasting them.

Environment variables (optional):
- COOKIECLOUD_SERVER_URL (default: http://127.0.0.1:8088)
- COOKIECLOUD_UUID
- COOKIECLOUD_PASSWORD
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from base64 import b64decode
from collections import OrderedDict
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

try:
    # Preferred import name used by pycryptodome.
    from Cryptodome.Cipher import AES  # type: ignore
    from Cryptodome.Util.Padding import unpad  # type: ignore
except ImportError:  # pragma: no cover
    # Some environments expose the same API as `Crypto.*`.
    from Crypto.Cipher import AES  # type: ignore
    from Crypto.Util.Padding import unpad  # type: ignore


@dataclasses.dataclass(frozen=True)
class CookieCloudConfig:
    server_url: str
    uuid: str
    password: str
    input_file: str | None = None


def _normalize_domain(domain: str) -> str:
    domain = str(domain).strip().lower().rstrip(":")
    if "://" in domain:
        parsed = urlparse(domain)
        domain = (parsed.hostname or "").lower()
    domain = domain.split(":", 1)[0]
    return domain.lstrip(".")


def _domain_matches(domain: str, pattern: str) -> bool:
    domain = _normalize_domain(domain)
    pattern = _normalize_domain(pattern)
    return bool(domain and pattern and (domain == pattern or domain.endswith(f".{pattern}")))


def _decrypt_cookiecloud_payload(ciphertext_b64: str, uuid: str, password: str) -> dict[str, Any]:
    # CookieCloud uses CryptoJS/OpenSSL salted format.
    key = hashlib.md5(f"{uuid}-{password}".encode("utf-8")).hexdigest()[:16].encode("utf-8")

    encrypted = b64decode(ciphertext_b64)
    if len(encrypted) < 16 or not encrypted.startswith(b"Salted__"):
        raise ValueError("Unsupported ciphertext format (expected OpenSSL/CryptoJS Salted__)")

    salt = encrypted[8:16]
    ct = encrypted[16:]

    key_iv = b""
    prev = b""
    while len(key_iv) < 48:
        prev = hashlib.md5(prev + key + salt).digest()
        key_iv += prev

    aes_key = key_iv[:32]
    iv = key_iv[32:48]

    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return json.loads(pt.decode("utf-8"))


def _fetch_encrypted_from_server(server_url: str, uuid: str) -> str:
    server_url = server_url.rstrip("/")
    url = f"{server_url}/get/{uuid}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    encrypted = data.get("encrypted")
    if not encrypted:
        raise ValueError(f"Missing 'encrypted' in response from {url}")
    return str(encrypted)


def _load_encrypted_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    encrypted = data.get("encrypted")
    if not encrypted:
        raise ValueError(f"Missing 'encrypted' in {path}")
    return str(encrypted)


def load_cookie_data(cfg: CookieCloudConfig) -> dict[str, Any]:
    if cfg.input_file:
        encrypted = _load_encrypted_from_file(cfg.input_file)
    else:
        encrypted = _fetch_encrypted_from_server(cfg.server_url, cfg.uuid)

    decrypted = _decrypt_cookiecloud_payload(encrypted, cfg.uuid, cfg.password)
    cookie_data = decrypted.get("cookie_data") or {}
    if not isinstance(cookie_data, dict):
        raise ValueError("Unexpected CookieCloud payload: cookie_data is not a dict")
    return cookie_data


def cookie_header_from_cookie_data(cookie_data: dict[str, Any], domain_suffix: str) -> str:
    merged: "OrderedDict[str, str]" = OrderedDict()
    for domain, cookies in cookie_data.items():
        if not isinstance(domain, str) or not _domain_matches(domain, domain_suffix):
            continue
        if not isinstance(cookies, list):
            continue
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name", "")).strip()
            if not name:
                continue
            value = cookie.get("value", "")
            merged[name] = "" if value is None else str(value)
    return "; ".join(f"{k}={v}" for k, v in merged.items())


def cookies_for_domain(cookie_data: dict[str, Any], domain_suffix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for domain, cookies in cookie_data.items():
        if not isinstance(domain, str) or not _domain_matches(domain, domain_suffix):
            continue
        if not isinstance(cookies, list):
            continue
        for cookie in cookies:
            if isinstance(cookie, dict):
                out.append(cookie)
    return out


def env_cookiecloud_config() -> CookieCloudConfig | None:
    # Accept both canonical and legacy env var spellings.
    uuid = (os.environ.get("COOKIECLOUD_UUID") or os.environ.get("COOKIECLOUDUUID") or "").strip()
    password = (os.environ.get("COOKIECLOUD_PASSWORD") or os.environ.get("COOKIECLOUDPASSWORD") or "").strip()
    if not uuid or not password:
        return None
    server_url = (
        os.environ.get("COOKIECLOUD_SERVER_URL")
        or os.environ.get("COOKIECLOUDSERVER_URL")
        or "http://127.0.0.1:8088"
    ).strip()
    input_file = (os.environ.get("COOKIECLOUD_INPUT_FILE") or "").strip() or None
    return CookieCloudConfig(server_url=server_url, uuid=uuid, password=password, input_file=input_file)


def first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def first_env_prefix(prefix: str) -> tuple[str, str] | None:
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        if value and str(value).strip():
            return key, str(value).strip()
    return None


def resolve_cookie_header(
    *,
    domain_suffix: str,
    cookie_arg: str | None,
    env_names: Iterable[str] = (),
    env_prefix: str | None = None,
) -> str:
    """
    Resolve a Cookie header string.

    Priority:
    1) `cookie_arg`
    2) `env_names` (first set)
    3) `env_prefix` (first matching env var)
    4) CookieCloud (COOKIECLOUD_* env vars)
    """
    if cookie_arg and cookie_arg.strip():
        return cookie_arg.strip()

    env_value = first_env(*list(env_names))
    if env_value:
        return env_value

    if env_prefix:
        pref = first_env_prefix(env_prefix)
        if pref:
            return pref[1]

    cfg = env_cookiecloud_config()
    if not cfg:
        raise SystemExit(
            "Missing cookies. Provide --cookie, set an env var, or set COOKIECLOUD_UUID/COOKIECLOUD_PASSWORD."
        )
    cookie_data = load_cookie_data(cfg)
    header = cookie_header_from_cookie_data(cookie_data, domain_suffix)
    if not header:
        raise SystemExit(f"No cookies found for domain suffix: {domain_suffix}")
    return header
