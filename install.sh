#!/bin/bash
# Install Core Bridje vpn on a fresh server. Keys and the server address
# are created here and stored in /etc/core-bridje, not in git.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Запусти от root: sudo bash install.sh" >&2
  exit 1
fi

SRC=$(cd "$(dirname "$0")" && pwd)
ENV_FILE=/etc/core-bridje/server.env
umask 077

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl ca-certificates python3 openssl

if ! command -v xray >/dev/null 2>&1; then
  bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
fi

if [ ! -x /usr/local/bin/cloudflared ]; then
  case "$(uname -m)" in
    x86_64) CF_ASSET=cloudflared-linux-amd64 ;;
    aarch64) CF_ASSET=cloudflared-linux-arm64 ;;
    *) echo "Неподдерживаемая архитектура: $(uname -m)" >&2; exit 1 ;;
  esac
  curl -fsSL -o /usr/local/bin/cloudflared \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/${CF_ASSET}"
  chmod 755 /usr/local/bin/cloudflared
fi

mkdir -p /etc/core-bridje /opt/core-bridje
rm -rf /opt/core-bridje/rules
cp -a "$SRC/rules" /opt/core-bridje/rules
cp "$SRC/happ/server.py" /opt/core-bridje/server.py
cp "$SRC/happ/tunnel.sh" /opt/core-bridje/tunnel.sh
chmod 755 /opt/core-bridje/tunnel.sh /opt/core-bridje/server.py

if [ ! -f "$ENV_FILE" ]; then
  SERVER_IP=$(curl -4 -fsS --max-time 20 https://ifconfig.me)
  UUID=$(xray uuid)
  KEYS=$(xray x25519)
  PRIVATE_KEY=$(printf '%s\n' "$KEYS" | awk -F': ' '/^PrivateKey:/{print $2}')
  PUBLIC_KEY=$(printf '%s\n' "$KEYS" | awk -F': ' '/PublicKey:/{print $2}')
  SHORT_ID=$(openssl rand -hex 4)
  TOKEN=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
  cat > "$ENV_FILE" <<EOF
SERVER_IP=${SERVER_IP}
PORT=8443
UUID=${UUID}
PRIVATE_KEY=${PRIVATE_KEY}
PUBLIC_KEY=${PUBLIC_KEY}
SHORT_ID=${SHORT_ID}
SNI=eh.vk.com
DEST=eh.vk.com:443
FINGERPRINT=qq
TOKEN=${TOKEN}
PROFILE_TITLE=Core Bridge
REMARKS=🇪🇸 Core Bridge Spain
ANNOUNCE=Российские сервисы и MAX напрямую, остальное через VPN
EOF
  chmod 600 "$ENV_FILE"
fi

python3 - "$ENV_FILE" <<'PY'
import json
import sys
from pathlib import Path

env = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    env[key.strip()] = value.strip()

config = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "tag": "vless-reality",
            "listen": "0.0.0.0",
            "port": int(env.get("PORT", "8443")),
            "protocol": "vless",
            "settings": {
                "clients": [
                    {
                        "id": env["UUID"],
                        "flow": "xtls-rprx-vision",
                        "email": "core-bridje",
                    }
                ],
                "decryption": "none",
            },
            "streamSettings": {
                "network": "raw",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "dest": env.get("DEST", "eh.vk.com:443"),
                    "xver": 0,
                    "serverNames": [env.get("SNI", "eh.vk.com")],
                    "privateKey": env["PRIVATE_KEY"],
                    "shortIds": [env["SHORT_ID"]],
                },
            },
            "sniffing": {
                "enabled": True,
                "destOverride": ["http", "tls", "quic"],
            },
        }
    ],
    "outbounds": [
        {"tag": "direct", "protocol": "freedom", "settings": {}},
        {"tag": "block", "protocol": "blackhole", "settings": {}},
    ],
}
path = Path("/usr/local/etc/xray/config.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY

cp "$SRC/happ/happ-sub.service" /etc/systemd/system/happ-sub.service
cp "$SRC/happ/happ-tunnel.service" /etc/systemd/system/happ-tunnel.service
systemctl daemon-reload
systemctl enable xray happ-sub happ-tunnel
systemctl restart xray happ-sub happ-tunnel

echo "Жду публичную ссылку..."
for _ in $(seq 1 40); do
  if [ -s /etc/core-bridje/url.txt ]; then
    break
  fi
  sleep 1
done

echo
if [ -s /etc/core-bridje/url.txt ]; then
  echo "Ссылка Happ:"
  cat /etc/core-bridje/url.txt
else
  echo "Туннель ещё не выдал ссылку. Смотри: journalctl -u happ-tunnel -n 40"
fi
echo "Ключи лежат только в ${ENV_FILE}"
