#!/bin/bash
# Public HTTPS name for the subscription. The hostname is chosen by Cloudflare.
set -u
TOKEN=$(awk -F= '/^TOKEN=/{print $2}' /etc/core-bridje/server.env)
stdbuf -oL -eL /usr/local/bin/cloudflared tunnel \
  --url http://127.0.0.1:2096 \
  --no-autoupdate \
  --protocol http2 \
  2>&1 | while IFS= read -r line; do
    printf '%s\n' "$line"
    host=$(printf '%s\n' "$line" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1 || true)
    if [ -n "${host}" ]; then
      printf '%s/sub/%s\n' "$host" "$TOKEN" > /etc/core-bridje/url.txt
    fi
  done
