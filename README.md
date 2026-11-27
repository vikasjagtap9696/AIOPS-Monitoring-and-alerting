# AI-Powered AIOps Incident Management Platform

A lab project for monitoring AWS EC2 instances and enriching alerts with Prometheus metrics, SSH evidence, Google Gemini analysis, ChromaDB runbooks, optional remediation, and Slack notifications.

![AIOps Architecture](architecture.png)

> Deploy in order. The maintained application is in `aiops/`; do not copy old prototype code into the service. Replace every ALL-CAPS value with your own. Keep remediation disabled until every action is reviewed. This repository is a learning lab, not a production-ready deployment.

## Project structure

```text
.
|-- aiops/                 Flask service, SSH evidence, RAG utilities
|-- config/                Prometheus, Alertmanager, and inventory examples
|-- knowledge/             Operational runbooks
|-- scripts/               Linux installation scripts
|-- systemd/               AIOps systemd unit
|-- tests/                 Focused application tests
|-- .env.example           Environment variable template
|-- requirements.txt       Runtime dependencies
|-- requirements-dev.txt   Development dependencies
|-- architecture.png       Architecture diagram
`-- README.md              This deployment guide
```

`.env`, `config/servers.json`, SSH private keys, and generated ChromaDB data are local-only and ignored by Git. Never commit secrets or real webhook URLs.

## Prerequisites

- AWS account and permission to launch EC2 instances, configure security groups, and attach an IAM instance profile.
- One Amazon Linux 2023 monitoring server and two Amazon Linux 2023 test servers. Example sizes: `c7i-flex.large` for monitoring and `t3.micro` for each test server.
- Monitoring-server instance profile with `ec2:DescribeInstances` permission.
- Slack Incoming Webhook URL and Google Gemini API key.
- Git, Python 3.9+, and network access to download packages on the monitoring host.

### EC2 tags

Set the EC2 Name tags to `Test-1` and `Test-2`. Also add this tag to each test instance; Prometheus uses it for discovery.

| Key | Value |
| --- | --- |
| `monitor` | `node_server` |

### Security groups

Restrict browser-facing ports to your own IP. Do not expose Prometheus, Grafana, Alertmanager, SSH, or Node Exporter to the public internet.

| Destination | Port | Source |
| --- | ---: | --- |
| Monitoring server: Prometheus UI | 9090 | Your IP |
| Monitoring server: Alertmanager UI | 9093 | Your IP |
| Monitoring server: Grafana UI | 3000 | Your IP |
| Test servers: SSH | 22 | Monitoring server security group |
| Test servers: Node Exporter | 9100 | Monitoring server security group |
| Nginx test server: exporter | 9113 | Monitoring server security group |

The AIOps webhook listens only on `127.0.0.1:5000`; do not open port 5000 to the internet.

## Step 1: Install the monitoring stack

Create a Slack app with Incoming Webhooks enabled and copy the channel webhook URL. Keep it private.

On the monitoring server, from a clone of this repository, set the AWS region and enter the webhook when prompted:

```bash
export AWS_REGION="ap-south-1"
read -rsp "Slack Incoming Webhook URL: " SLACK_WEBHOOK_URL; echo
export SLACK_WEBHOOK_URL
bash scripts/install-monitoring.sh
unset SLACK_WEBHOOK_URL AWS_REGION
```

The script installs Prometheus, Alertmanager, Grafana, and a local Node Exporter. Review it before running; it updates the OS and writes system configuration.

## Step 2: Install Node Exporter on both test servers

Run this on Test-1 and Test-2 (download from a trusted checkout/release URL):

```bash
curl --fail --location --output /tmp/install-node-exporter.sh https://raw.githubusercontent.com/vikasjagtap9696/AIOPS-Monitoring-and-alerting/main/scripts/install-node-exporter.sh
sudo bash /tmp/install-node-exporter.sh
sudo systemctl status node_exporter --no-pager
```

## Step 3: Confirm monitoring works

1. Open `http://MONITORING_PUBLIC_IP:9090/targets`; both Node Exporter targets should be **UP**.
2. Open `http://MONITORING_PUBLIC_IP:9090/alerts` and `http://MONITORING_PUBLIC_IP:9093`.
3. Open `http://MONITORING_PUBLIC_IP:3000`. Sign in with the Grafana initial credentials (`admin` / `admin`) and change the password.
4. In Grafana, add a Prometheus data source with URL `http://localhost:9090`.
5. Confirm an alert notification reaches Slack.

## Step 4: Install the AIOps service

Clone the repository to `/opt/aiops` on the monitoring server. Skip cloning if it is already checked out there.

```bash
sudo git clone https://github.com/vikasjagtap9696/AIOPS-Monitoring-and-alerting.git /opt/aiops
cd /opt/aiops
sudo bash scripts/install-aiops.sh
```

Edit `/opt/aiops/.env`. Add your Gemini key and Slack webhook, and leave remediation disabled:

```dotenv
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
SLACK_WEBHOOK_URL=YOUR_SLACK_WEBHOOK_URL
AUTO_REMEDIATE=false
```

The installer creates `/opt/aiops/config/servers.json` from the example. Set each host to its EC2 private IP; keep the keys and names as shown. Include the Nginx exporter mapping for the server running Nginx:

```json
{
  "Test-1": {"host": "TEST_1_PRIVATE_IP", "user": "ec2-user"},
  "Test-2": {"host": "TEST_2_PRIVATE_IP", "user": "ec2-user"},
  "TEST_1_PRIVATE_IP:9113": {
    "host": "TEST_1_PRIVATE_IP",
    "user": "ec2-user",
    "services": {"nginx": "nginx"}
  }
}
```

### Configure SSH evidence collection

Generate a key as the service user. Copy only its public key to `~ec2-user/.ssh/authorized_keys` on each test server. Preserve existing authorized-key entries; never copy the private key off the monitoring server.

```bash
sudo -u aiops ssh-keygen -t ed25519 -f /opt/aiops/.ssh/id_ed25519 -N ""
sudo cat /opt/aiops/.ssh/id_ed25519.pub
```

On each test server, append the copied public key as `ec2-user`:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
echo 'PASTE_MONITORING_SERVER_PUBLIC_KEY_HERE' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

From the monitoring server, connect once as `aiops` to each host. Verify host fingerprints before accepting them; Paramiko uses the recorded host keys.

```bash
sudo -u aiops ssh -i /opt/aiops/.ssh/id_ed25519 ec2-user@TEST_1_PRIVATE_IP
sudo -u aiops ssh -i /opt/aiops/.ssh/id_ed25519 ec2-user@TEST_2_PRIVATE_IP
```

### Configure Prometheus and Alertmanager

Copy the repository configuration files, then replace the AWS region and Nginx private IP in `prometheus.yml`:

```bash
sudo cp /opt/aiops/config/prometheus.yml.example /etc/prometheus/prometheus.yml
sudo cp /opt/aiops/config/alert.rules.yml /etc/prometheus/alert.rules.yml
sudo cp /opt/aiops/config/alertmanager-aiops.yml.example /etc/alertmanager/alertmanager.yml
sudo vi /etc/prometheus/prometheus.yml
sudo promtool check config /etc/prometheus/prometheus.yml
sudo promtool check rules /etc/prometheus/alert.rules.yml
sudo amtool check-config /etc/alertmanager/alertmanager.yml
sudo systemctl restart prometheus alertmanager
```

### Load the runbook and start the service

The Nginx runbook is in `knowledge/nginx_runbook.md`. Load its chunks into ChromaDB and start the AIOps systemd service:

```bash
cd /opt/aiops
sudo -u aiops /opt/aiops/venv/bin/python -m aiops.rag_store
sudo systemctl enable --now aiops
sudo systemctl status aiops --no-pager
curl http://127.0.0.1:5000/
```

The service receives alerts at `/alert`, collects Prometheus metrics and SSH evidence, asks Gemini for an evidence-based analysis, and reports the result to Slack. The implementation is in `aiops/app.py`, `aiops/ssh_client.py`, and `aiops/rag_store.py`.

## Step 5: Optional Nginx alert and runbook

On Test-1, install and start Nginx:

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx
```

Configure the local Nginx status page and exporter. Allow inbound TCP 9113 only from the monitoring server security group.

```bash
sudo tee /etc/nginx/conf.d/status.conf >/dev/null <<'EOF'
server {
    listen 8080;
    location /stub_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }
}
EOF
sudo nginx -t
sudo systemctl reload nginx
```

Install the Nginx Prometheus exporter on Test-1:

```bash
cd /tmp
curl --fail --location --output nginx-exporter.tar.gz https://github.com/nginxinc/nginx-prometheus-exporter/releases/download/v1.1.0/nginx-prometheus-exporter_1.1.0_linux_amd64.tar.gz
tar -xzf nginx-exporter.tar.gz
sudo install -m 0755 nginx-prometheus-exporter /usr/local/bin/nginx-prometheus-exporter
```

Then create `/etc/systemd/system/nginx-exporter.service`:

```ini
[Unit]
Description=Nginx Prometheus Exporter
After=network.target nginx.service

[Service]
ExecStart=/usr/local/bin/nginx-prometheus-exporter -nginx.scrape-uri=http://127.0.0.1:8080/stub_status
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Start the exporter and confirm it exposes the Nginx metric:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nginx-exporter
curl http://localhost:9113/metrics | grep nginx_up
```

The scrape target is included in `config/prometheus.yml.example`. Ensure the private IP and `servers.json` instance key match the Prometheus `instance` label. Check `http://MONITORING_PUBLIC_IP:9090/targets` for the exporter.

To trigger a lab alert, stop Nginx on Test-1 and confirm the alert and Slack report. Start Nginx again after the demonstration:

```bash
sudo systemctl stop nginx
sudo systemctl start nginx
```

## Optional auto-remediation

Auto-remediation is disabled by default. The examples can start/restart services, clear filesystem caches, or delete old files under `/tmp`. Review the handlers in `aiops/app.py` and service allow-list in `config/servers.json`; only enable this on an isolated lab host if you explicitly accept the risks.

## Troubleshooting and cleanup

Check service state and logs on the monitoring server:

```bash
sudo systemctl status prometheus alertmanager aiops --no-pager
sudo journalctl -u prometheus -n 100 --no-pager
sudo journalctl -u alertmanager -n 100 --no-pager
sudo journalctl -u aiops -n 100 --no-pager
```

After the lab, revoke the Gemini key, remove the Slack webhook, and terminate the lab EC2 instances. Keep dashboards private and do not leave test credentials or private keys in the repository.