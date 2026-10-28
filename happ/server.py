#!/usr/bin/env python3
"""Happ subscription. Secrets come from /etc/core-bridje/server.env, not from git."""

from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENV_PATH = Path("/etc/core-bridje/server.env")
RULES = Path("/opt/core-bridje/rules")
LISTEN = ("127.0.0.1", 2096)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def ident(kind: str, value: str) -> str:
    if kind in {"keyword", "geosite", "geoip", "regexp"}:
        return f"{kind}:{value}"
    return f"{kind}:{value.encode('idna').decode('ascii')}"


def unique(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


def load_matchers(path: Path) -> list[str]:
    found: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" in line and line.split(":", 1)[0] in {"domain", "keyword", "full", "regexp", "geosite"}:
            kind, value = line.split(":", 1)
            found.append(ident(kind, value))
        else:
            found.append(ident("domain", line))
    return unique(found)


def load_ips(path: Path) -> list[str]:
    found: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            found.append(line)
    return unique(found)


ENV = load_env(ENV_PATH)
TOKEN = ENV["TOKEN"]
TITLE = ENV.get("PROFILE_TITLE", "Core Bridge")
REMARKS = ENV.get("REMARKS", "🇪🇸 Core Bridge Spain")
ANNOUNCE = base64.b64encode(
    ENV.get(
        "ANNOUNCE",
        "Российские сервисы и MAX напрямую, остальное через VPN",
    ).encode()
).decode()


def profile() -> dict:
    server_ip = ENV.get("SERVER_IP", "")
    direct_ips = []
    if server_ip:
        direct_ips.append(f"{server_ip}/32")
    direct_ips.extend(load_ips(RULES / "direct-ips.txt"))
    return {
        "remarks": REMARKS,
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
                "tag": "socks",
            },
            {
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http",
                "settings": {"allowTransparent": False},
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
                "tag": "http",
            },
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "tag": "proxy",
                "settings": {
                    "vnext": [
                        {
                            "address": ENV["SERVER_IP"],
                            "port": int(ENV.get("PORT", "8443")),
                            "users": [
                                {
                                    "id": ENV["UUID"],
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "raw",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "fingerprint": ENV.get("FINGERPRINT", "qq"),
                        "serverName": ENV.get("SNI", "eh.vk.com"),
                        "publicKey": ENV["PUBLIC_KEY"],
                        "shortId": ENV["SHORT_ID"],
                        "spiderX": "/",
                    },
                },
            },
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "domainMatcher": "hybrid",
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "ip": unique(direct_ips), "outboundTag": "direct"},
                {"type": "field", "domain": load_matchers(RULES / "block.txt"), "outboundTag": "block"},
                {"type": "field", "domain": load_matchers(RULES / "proxy.txt"), "outboundTag": "proxy"},
                {"type": "field", "ip": load_ips(RULES / "proxy-ips.txt"), "outboundTag": "proxy"},
                {"type": "field", "domain": load_matchers(RULES / "direct.txt"), "outboundTag": "direct"},
                {"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct"},
                {"type": "field", "network": "udp", "port": "443", "outboundTag": "block"},
                {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"},
            ],
        },
    }


def subscription_body() -> bytes:
    return json.dumps([profile()], ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path != f"/sub/{TOKEN}":
            body = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = subscription_body()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("profile-update-interval", "1")
        self.send_header("profile-title", TITLE)
        self.send_header("announce", f"base64:{ANNOUNCE}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main() -> None:
    ThreadingHTTPServer(LISTEN, Handler).serve_forever()


if __name__ == "__main__":
    main()
