#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pycryptodome>=3.20.0",
#   "requests>=2.31.0",
# ]
# ///
"""
Decrypt CookieCloud cookies and export them into a dotenv-style file.

This is a sanitized, skill-scoped variant of a typical CookieCloud decrypt/export script:
- No RSSHub dependency.
- No user-specific defaults.
- Exports only the cookies you need for these skills by default:
  - BILIBILI_COOKIE (or BILIBILI_COOKIE_<uid> if --bilibili-uid is set)
  - ZHIHU_COOKIES
  - XIAOHONGSHU_COOKIE

Usage examples:
- Export the 3 platform cookies into ./favorites.env
  python cookiecloud_export_env.py http://127.0.0.1:8088 <uuid> <password> --env-file favorites.env

- Print only env keys (no cookie values) and do not write files:
  python cookiecloud_export_env.py http://127.0.0.1:8088 <uuid> <password> --dry-run

Security:
- Avoid using --show-cookies unless you fully trust your terminal history/logging.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from base64 import b64decode
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util.Padding import unpad
except ImportError:  # pragma: no cover
    from Crypto.Cipher import AES  # type: ignore
    from Crypto.Util.Padding import unpad  # type: ignore


@dataclass(frozen=True)
class ExportRule:
    env: str
    match: tuple[str, ...]


def default_rules(*, bilibili_uid: str | None) -> tuple[ExportRule, ...]:
    bili_env = f"BILIBILI_COOKIE_{bilibili_uid}" if bilibili_uid else "BILIBILI_COOKIE"
    return (
        ExportRule(env=bili_env, match=("bilibili.com",)),
        ExportRule(env="ZHIHU_COOKIES", match=("zhihu.com",)),
        ExportRule(env="XIAOHONGSHU_COOKIE", match=("xiaohongshu.com",)),
    )


_ENV_KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


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


def _cookie_kv_pairs(cookies: Iterable[dict[str, Any]]) -> Iterable[tuple[str, str]]:
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name", "")).strip()
        if not name:
            continue
        value = cookie.get("value", "")
        yield name, "" if value is None else str(value)


def _cookie_header_from_kv_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    merged: "OrderedDict[str, str]" = OrderedDict()
    for name, value in pairs:
        merged[name] = value
    return "; ".join(f"{name}={value}" for name, value in merged.items())


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
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
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


def _format_env_assignment(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def _update_env_file(path: str, updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_lines = f.read().splitlines()

    seen: set[str] = set()
    out_lines: list[str] = []

    for line in existing_lines:
        m = _ENV_KV_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1)
        if key in updates:
            out_lines.append(_format_env_assignment(key, updates[key]))
            seen.add(key)
        else:
            out_lines.append(line)

    for key in sorted(updates.keys()):
        if key not in seen:
            out_lines.append(_format_env_assignment(key, updates[key]))

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines).rstrip("\n") + "\n")


def _build_exports(
    cookie_data: dict[str, Any],
    *,
    rules: tuple[ExportRule, ...],
) -> dict[str, str]:
    if not isinstance(cookie_data, dict):
        raise ValueError("cookie_data must be a dict")

    domains: list[str] = [k for k in cookie_data.keys() if isinstance(k, str)]
    updates: dict[str, str] = {}

    for rule in rules:
        matched_domains = [
            domain for domain in domains if any(_domain_matches(domain, pattern) for pattern in rule.match)
        ]
        if not matched_domains:
            continue

        all_pairs: list[tuple[str, str]] = []
        for domain in sorted(matched_domains, key=_normalize_domain):
            cookies = cookie_data.get(domain, [])
            if not isinstance(cookies, list):
                continue
            all_pairs.extend(_cookie_kv_pairs(cookies))
        cookie_header = _cookie_header_from_kv_pairs(all_pairs)
        if cookie_header:
            updates[rule.env] = cookie_header

    return updates


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Decrypt CookieCloud cookies and export platform cookie env vars.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("server_url", help="CookieCloud server URL, e.g. http://127.0.0.1:8088")
    parser.add_argument("uuid", help="CookieCloud UUID")
    parser.add_argument("password", help="CookieCloud password")
    parser.add_argument("--input-file", help="Read encrypted JSON from a local file instead of CookieCloud server")
    parser.add_argument("--env-file", default="favorites.env", help="Write/update this env file")
    parser.add_argument(
        "--bilibili-uid",
        help="If set, export Bilibili cookies into BILIBILI_COOKIE_<uid> instead of BILIBILI_COOKIE.",
    )
    parser.add_argument("--list-domains", action="store_true", help="List decrypted domain keys and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files; just print keys")
    parser.add_argument("--show-cookies", action="store_true", help="Print cookie values (may leak secrets)")
    args = parser.parse_args(argv)

    try:
        if args.input_file:
            encrypted = _load_encrypted_from_file(args.input_file)
        else:
            encrypted = _fetch_encrypted_from_server(args.server_url, args.uuid)

        decrypted = _decrypt_cookiecloud_payload(encrypted, args.uuid, args.password)
        cookie_data = decrypted.get("cookie_data") or {}

        if args.list_domains:
            domains = [k for k in cookie_data.keys() if isinstance(k, str)]
            for domain in sorted(domains, key=_normalize_domain):
                print(domain)
            return 0

        rules = default_rules(bilibili_uid=(str(args.bilibili_uid).strip() or None))
        updates = _build_exports(cookie_data, rules=rules)

        if not updates:
            print("No cookies matched export rules.", file=sys.stderr)
            return 2

        if args.show_cookies:
            for k in sorted(updates.keys()):
                print(f"{k}={updates[k]}")
        else:
            for k in sorted(updates.keys()):
                print(k)

        if args.dry_run:
            return 0

        _update_env_file(args.env_file, updates)
        print(f"Updated {args.env_file} ({len(updates)} entries).")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

