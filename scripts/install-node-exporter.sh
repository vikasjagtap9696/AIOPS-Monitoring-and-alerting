#!/usr/bin/env bash
set -euo pipefail

NODE_EXPORTER_VERSION="${NODE_EXPORTER_VERSION:-1.11.1}"
WORK_DIR="$(mktemp -d)"
ARCHIVE="node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${ARCHIVE}"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

curl --fail --location --silent --show-error "$URL" -o "${WORK_DIR}/${ARCHIVE}"
tar -xzf "${WORK_DIR}/${ARCHIVE}" -C "$WORK_DIR"

if ! id node_exporter >/dev/null 2>&1; then
    sudo useradd --system --no-create-home --shell /sbin/nologin node_exporter
fi

sudo install -o root -g root -m 0755 \
    "${WORK_DIR}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter" \
    /usr/local/bin/node_exporter

sudo tee /etc/systemd/system/node_exporter.service >/dev/null <<'EOF'
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
sudo systemctl status node_exporter --no-pager
