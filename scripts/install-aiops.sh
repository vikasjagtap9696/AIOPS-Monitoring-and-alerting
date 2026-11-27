#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$APP_DIR" != "/opt/aiops" ]]; then
    echo "Clone this repository to /opt/aiops before running the installer." >&2
    exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

if ! id aiops >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /sbin/nologin aiops
fi

install -d -o aiops -g aiops -m 0750 \
    "$APP_DIR/data" "$APP_DIR/.ssh"

if [[ ! -f "$APP_DIR/.env" ]]; then
    install -o root -g aiops -m 0640 "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

if [[ ! -f "$APP_DIR/config/servers.json" ]]; then
    install -o root -g aiops -m 0640 \
        "$APP_DIR/config/servers.example.json" "$APP_DIR/config/servers.json"
fi

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

install -o root -g root -m 0644 \
    "$APP_DIR/systemd/aiops.service" /etc/systemd/system/aiops.service
systemctl daemon-reload

echo "AIOps dependencies and systemd unit installed."
echo "Edit $APP_DIR/.env and $APP_DIR/config/servers.json before starting the service."
