# 🤖 AI-Powered Self-Healing AIOps Platform
 
> **Prometheus + Alertmanager + Grafana + Flask AIOps Engine + OpenAI GPT + RAG (ChromaDB) + Auto-Remediation + Slack**
 
An end-to-end AIOps and auto-healing platform on AWS. It detects infrastructure failures, collects live metrics and SSH evidence, retrieves troubleshooting runbooks from a vector database (RAG), performs AI-driven Root Cause Analysis (RCA), automatically fixes the issue (for example restarts Nginx), verifies recovery, and sends an AI-generated incident report to Slack.
 
![Architecture](architecture.png)
 
---
 
## 📑 Table of Contents
 
1. [Overview & Flow](#1-overview--flow)
2. [Servers used in this project (read this first)](#2-servers-used-in-this-project-read-this-first)
3. [How to read the steps](#3-how-to-read-the-steps)
4. [Part A – Prepare AWS & Slack](#part-a--prepare-aws--slack)
5. [Part B – Phase 1: Monitoring & Alerting](#part-b--phase-1-monitoring--alerting)
6. [Part C – Phase 2: Add AI (RCA)](#part-c--phase-2-add-ai-rca)
7. [Part D – Phase 3: SSH Investigation](#part-d--phase-3-ssh-based-investigation)
8. [Part E – Phase 4: Auto-Remediation](#part-e--phase-4-auto-remediation)
9. [Part F – Phase 5: Nginx Self-Healing + RAG](#part-f--phase-5-nginx-self-healing--rag)
10. [Part G – Clean Up](#part-g--clean-up)
11. [Appendix A – Final `app.py`](#appendix-a--final-apppy)
12. [Appendix B – `rag_store.py`](#appendix-b--rag_storepy)
13. [Troubleshooting](#troubleshooting)
14. [Security Notes](#security-notes)
15. [Roadmap](#roadmap)
---
 
## 1. Overview & Flow
 
```
Linux Servers
      ↓
Node Exporter + Nginx Exporter
      ↓
Prometheus            (collects metrics, evaluates alert rules)
      ↓
Alertmanager          (groups / routes alerts)
      ↓  Webhook (HTTP POST)
Flask AIOps Engine    (runs on Monitoring Server, port 5000)
      ↓
Prometheus Metrics → SSH Evidence → RAG Runbook (ChromaDB)
      ↓
OpenAI Root Cause Analysis
      ↓
Auto Remediation → Verification
      ↓
Slack Incident Report
```
 
**Project is built in 5 phases:**
 
| Phase | What you build |
|-------|----------------|
| 1 | Prometheus + Grafana + Alertmanager + Node Exporter, alerts go to Slack |
| 2 | Flask AIOps service – alerts go to AI, AI does RCA using Prometheus metrics |
| 3 | AI logs in to the affected EC2 via SSH and collects live evidence |
| 4 | Safe auto-remediation (restart service, clear cache, clean logs) |
| 5 | Nginx exporter + RAG runbook (ChromaDB) → AI auto-heals Nginx and verifies |
 
---
 
## 2. Servers used in this project (read this first)
 
You will work on **3 EC2 instances**. Every step below tells you **exactly which one** to run it on.
 
| Name | Role | OS / Size | Tag(s) | What runs on it |
|------|------|-----------|--------|-----------------|
| 🖥️ **Monitoring Server** | Brain of the project | Amazon Linux 2023, `c7i-flex.large`, 30 GB, IAM Role (Admin) | `Name = monitoring` | Prometheus, Alertmanager, Grafana, Node Exporter, Flask AIOps app, ChromaDB |
| 🟢 **Test-1** | Monitored / target server | Amazon Linux 2023, `t3.micro` | `monitor = node_server`, `Name = Test-1` | Node Exporter, `stress`, **Nginx + Nginx Exporter** |
| 🟡 **Test-2** | Monitored / target server | Amazon Linux 2023, `t3.micro` | `monitor = node_server`, `Name = Test-2` | Node Exporter |
 
Other places you will work:
 
| Icon | Place |
|------|-------|
| ☁️ | AWS Console |
| 💬 | Slack (web) |
| 🌐 | Your browser (Prometheus / Alertmanager / Grafana UI) |
 
**Ports to open in the Security Groups**
 
| Server | Port | Purpose | Allow from |
|--------|------|---------|-----------|
| Monitoring | 22 | SSH | Your IP |
| Monitoring | 9090 | Prometheus UI | Your IP |
| Monitoring | 9093 | Alertmanager UI | Your IP |
| Monitoring | 3000 | Grafana UI | Your IP |
| Monitoring | 5000 | AIOps webhook | Monitoring SG (itself) |
| Test-1 / Test-2 | 22 | SSH | Your IP **and** Monitoring Server SG (AI uses SSH) |
| Test-1 / Test-2 | 9100 | Node Exporter | Monitoring Server SG |
| Test-1 | 9113 | Nginx Exporter | Monitoring Server SG |
 
---
 
## 3. How to read the steps
 
Each step starts with a **📍 Run on:** line. Always check it before you type a command.
 
* `# on 🖥️ Monitoring Server` – connect to the monitoring server and run it there
* `# on 🟢 Test-1` – connect to Test-1 and run it there
* Replace anything in `< >` with your own value (private IPs, keys, etc.).
* **Use private IPs** (e.g. `172.31.x.x`) for all server-to-server communication.
> 💡 Becoming root on the Monitoring Server (needed from Phase 2 onwards):
> ```bash
> sudo -i
> ```
 
---
 
# Part A – Prepare AWS & Slack
 
### Step 1 – Launch the Monitoring Server
📍 **Run on:** ☁️ AWS Console
 
1. EC2 → **Launch instance**
2. Name: `monitoring`
3. AMI: **Amazon Linux 2023**
4. Instance type: **c7i-flex.large**
5. Storage: **30 GB**
6. Key pair: create/select one (you will need the `.pem` file later)
7. Security group: open ports from the table in [section 2](#2-servers-used-in-this-project-read-this-first)
8. **Advanced details → IAM instance profile:** attach an IAM Role. (The lab uses Admin; the minimum needed is `ec2:DescribeInstances` for Prometheus EC2 service discovery.)
9. Launch.
### Step 2 – Launch Test-1 and Test-2
📍 **Run on:** ☁️ AWS Console
 
1. Launch **2 instances**, Amazon Linux 2023, **t3.micro**, same region (`ap-south-1`) and same VPC as the monitoring server.
2. Use the same key pair.
3. Add these **tags** (very important – Prometheus discovers servers using the tag):
| Instance | Tag key | Tag value |
|----------|---------|-----------|
| Test-1 | `monitor` | `node_server` |
| Test-1 | `Name` | `Test-1` |
| Test-2 | `monitor` | `node_server` |
| Test-2 | `Name` | `Test-2` |
 
4. Note down the **private IPs** of all three servers:
```
Monitoring private IP : ____________
Test-1 private IP     : ____________
Test-2 private IP     : ____________
```
 
### Step 3 – Create the Slack webhook
📍 **Run on:** 💬 Slack
 
1. Sign in at <https://app.slack.com> and create a new **channel** (e.g. `#aiops-alerts`).
2. Open <https://api.slack.com/apps> → **Create New App** → **From scratch** (or *Starter app → Blank app*). Enter an app name and select your workspace.
3. Left menu → **Incoming Webhooks** → switch **Activate Incoming Webhooks = ON**.
4. Click **Add New Webhook to Workspace**, choose your channel and copy the **Webhook URL**. Keep it safe.
---
 
# Part B – Phase 1: Monitoring & Alerting
 
Goal: Prometheus automatically discovers Test-1 / Test-2, alerts fire, and Slack receives them.
 
### Step 4 – Run the all-in-one install script
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
# on 🖥️ Monitoring Server  (login as ec2-user)
export SLACK_WEBHOOK_URL="<your-slack-webhook-url>"
 
vi allinoneinstallation.sh        # paste the script from this repo
chmod +x allinoneinstallation.sh
./allinoneinstallation.sh
```
 
The script does everything:
 
| It installs | Port | Config file |
|-------------|------|-------------|
| Prometheus 2.55.1 | 9090 | `/etc/prometheus/prometheus.yml`, `/etc/prometheus/alert.rules.yml` |
| Alertmanager 0.27.0 | 9093 | `/etc/alertmanager/alertmanager.yml` |
| Node Exporter 1.11.1 | 9100 | `/etc/systemd/system/node_exporter.service` |
| Grafana | 3000 | login `admin` / `admin` |
 
It also creates the alert rules (`InstanceDown`, `HighCPUUsage`, `HighMemoryUsage`, `HighDiskUsage`), configures **EC2 service discovery** (`tag:monitor = node_server`) and the Alertmanager → Slack receiver, and starts all services.
 
> ⚠️ Alert thresholds in the script are **10 %** on purpose, so alerts fire quickly during the demo. You will set realistic values (80 %) in Step 27.
 
If Grafana fails to install, see [Grafana repo fix](#grafana-repo-fix).
 
### Step 5 – Install Node Exporter on the test servers
📍 **Run on:** 🟢 **Test-1** and 🟡 **Test-2** (do it on both, one by one)
 
```bash
# on 🟢 Test-1  AND  🟡 Test-2
vi node.sh              # paste contents of node-exporter.sh
chmod +x node.sh
./node.sh
```
 
Node Exporter now runs on port **9100** and Prometheus (service discovery with the tag) will pick it up automatically.
 
Check:
```bash
systemctl status node_exporter
```
 
### Step 6 – Verify discovery and alerts
📍 **Run on:** 🌐 Browser
 
| What | URL | Expected |
|------|-----|----------|
| Prometheus targets | `http://<monitoring-public-ip>:9090/targets` | Both EC2 instances discovered and **UP** |
| Prometheus alerts | `http://<monitoring-public-ip>:9090/alerts` | Alerts turn yellow (**pending**), after some time **firing** |
| Alertmanager | `http://<monitoring-public-ip>:9093` | Alerts appear after a while |
| Slack | your channel | Alert messages arrive |
 
If no targets are discovered, run this on the 🖥️ Monitoring Server:
```bash
aws ec2 describe-instances --region ap-south-1 | grep node_server
```
 
### Step 7 – Grafana data source & dashboard
📍 **Run on:** 🌐 Browser → `http://<monitoring-public-ip>:3000`
 
1. Login `admin` / `admin` (set a new password).
2. **Connections → Data sources → Add data source → Prometheus**
3. URL: `http://localhost:9090` → **Save & test**.
4. **Dashboards → Import → ID `1860`** (Node Exporter Full) → select the Prometheus data source.
5. **Alerting → Alert rules** – you can see the Prometheus rules (system-alerts).
✅ **Phase 1 complete:** Monitoring + Alerting + Slack working.
 
---
 
# Part C – Phase 2: Add AI (RCA)
 
Now alerts will **not** go directly to Slack. They go to your **Flask AIOps service**, which asks AI for the root cause and then posts to Slack.
 
### Step 8 – Create the AIOps project folder
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
# on 🖥️ Monitoring Server
sudo -i
mkdir -p /opt/aiops
cd /opt/aiops
 
dnf install python3-pip -y
pip3 install flask requests gunicorn
```
 
Create the `.env` file for secrets (never hard-code keys in code):
 
```bash
vi /opt/aiops/.env
```
```ini
SLACK_WEBHOOK=<your-slack-webhook-url>
OPENAI_API_KEY=<your-openai-api-key>
AUTO_REMEDIATE=false
```
```bash
chmod 600 /opt/aiops/.env
```
 
> 🔑 Get the OpenAI key from <https://platform.openai.com/api-keys>.
 
### Step 9 – Create the first (basic) AI application
📍 **Run on:** 🖥️ **Monitoring Server** (as root, in `/opt/aiops`)
 
This first version only proves that Alertmanager → Flask → Slack works.
 
```bash
vi /opt/aiops/app.py
```
```python
import os
from flask import Flask, request
import requests
 
app = Flask(__name__)
 
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
 
 
@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    alert = data["alerts"][0]
 
    alert_name = alert["labels"].get("alertname", "Unknown")
    severity = alert["labels"].get("severity", "warning")
 
    message = f"""
🚨 AI Incident Analysis
 
Alert: {alert_name}
 
Severity: {severity}
 
Possible Causes:
- High workload
- Resource exhaustion
- Application issue
 
Recommended Actions:
- Check system resources
- Verify application logs
- Scale if required
 
Generated By: AIOps Engine
"""
    requests.post(SLACK_WEBHOOK, json={"text": message})
    return {"status": "received"}
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```
 
Run it once in the foreground (keep this terminal open):
```bash
cd /opt/aiops
set -a; source .env; set +a
python3 /opt/aiops/app.py
```
 
### Step 10 – Point Alertmanager to the AI application
📍 **Run on:** 🖥️ **Monitoring Server** (open a **second terminal**)
 
Alertmanager is the component that receives alerts from Prometheus and decides what to do with them. We remove Slack from it and add the AI webhook.
 
```bash
sudo vi /etc/alertmanager/alertmanager.yml
```
Replace the whole file with:
```yaml
global:
  resolve_timeout: 5m
 
route:
  receiver: aiops
 
receivers:
- name: aiops
  webhook_configs:
  - url: "http://localhost:5000/alert"
```
```bash
sudo systemctl restart alertmanager
sudo systemctl status alertmanager
```
 
### Step 11 – Create a test alert
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
sudo vi /etc/prometheus/alert.rules.yml
```
Add this rule inside the existing `rules:` list (same indentation as the other alerts):
```yaml
  - alert: TestAI
    expr: vector(1)
    for: 10s
    labels:
      severity: critical
    annotations:
      summary: "Testing AI"
```
```bash
promtool check rules /etc/prometheus/alert.rules.yml
curl -X POST http://localhost:9090/-/reload
sudo systemctl restart prometheus        # lowercase 'p'
```
 
Verify the alert in 🌐 Prometheus → Alerts, 🌐 Alertmanager, and 💬 Slack.
 
> Now press **Ctrl + C** in the terminal where `app.py` was running (we will run it as a service next).
 
### Step 12 – Run the AI app as a systemd service
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
sudo vi /etc/systemd/system/aiops.service
```
```ini
[Unit]
Description=AIOps Service
After=network.target
 
[Service]
User=root
WorkingDirectory=/opt/aiops
EnvironmentFile=/opt/aiops/.env
ExecStart=/usr/bin/python3 /opt/aiops/app.py
Restart=always
 
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable aiops
sudo systemctl start aiops
sudo systemctl status aiops
 
journalctl -u aiops -f                    # live logs
journalctl -u aiops -n 100 --no-pager     # last 100 lines
```
 
Whenever an alert arrives you will see `POST /alert HTTP/1.1 200` in the logs.
 
### Step 13 – Generate a real issue (High CPU)
📍 **Run on:** 🟢 **Test-1**
 
```bash
# on 🟢 Test-1
sudo dnf install stress -y
stress --cpu 4 --timeout 300
```
 
📍 Then on 🌐 Prometheus → Alerts: `HighCPUUsage` → pending → firing. Check 💬 Slack.
 
> **No alert in Slack?** On 🖥️ Monitoring Server check `sudo journalctl -u alertmanager -f`. If you see `permission denied` for `/var/lib/alertmanager`, see [Alertmanager permission fix](#alertmanager-permission-fix).
 
### Step 14 – Upgrade to real AI RCA (Prometheus metrics + OpenAI)
📍 **Run on:** 🖥️ **Monitoring Server**
 
Now AI receives live CPU / Memory / Disk metrics and produces a Root Cause Analysis.
 
```bash
pip3 install flask requests openai
pip3 list | grep -E "flask|requests|openai"
 
vi /opt/aiops/app.py        # replace the entire file
```
```python
import os
from flask import Flask, request
import requests
from openai import OpenAI
 
app = Flask(__name__)
 
PROM_URL = "http://localhost:9090"
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
 
 
def query_prometheus(query):
    response = requests.get(f"{PROM_URL}/api/v1/query", params={"query": query})
    return response.json()
 
 
@app.route("/alert", methods=["POST"])
def alert():
    data = request.json
    alert = data["alerts"][0]
    alert_name = alert["labels"]["alertname"]
 
    cpu_query = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)'
    memory_query = '((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100'
    disk_query = '((node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes) * 100'
 
    cpu = query_prometheus(cpu_query)
    memory = query_prometheus(memory_query)
    disk = query_prometheus(disk_query)
 
    prompt = f"""
You are a Senior SRE.
 
Alert:
{alert_name}
 
Current Metrics:
 
CPU:
{cpu}
 
Memory:
{memory}
 
Disk:
{disk}
 
Provide:
 
1. Root Cause
2. Impact
3. Recommended Fix
4. Severity
"""
    result = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    analysis = result.choices[0].message.content
 
    requests.post(SLACK_WEBHOOK, json={"text": analysis})
    return {"status": "ok"}
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```
```bash
systemctl daemon-reload
systemctl enable aiops
systemctl restart aiops
systemctl status aiops
```
 
Make sure Alertmanager still points to the AI app (Step 10 config) and restart it if you changed it:
```bash
systemctl restart alertmanager
```
 
### Step 15 – Test AI RCA
📍 **Run on:** 🟢 **Test-1**
 
```bash
stress --cpu 4 --timeout 300
```
Wait a few minutes → 🌐 Prometheus shows `HighCPUUsage` pending/firing → 💬 Slack shows the **AI-generated RCA**.
 
✅ **Phase 2 complete:** Alert → AI → Slack.
 
---
 
# Part D – Phase 3: SSH-Based Investigation
 
Goal: the AI service **logs in to the affected EC2 server** and collects live evidence (`top`, `free`, `df`, `journalctl`…).
 
```
Alert → AI Service → SSH to affected EC2 → Collect live evidence → OpenAI → RCA → Slack
```
 
### Step 16 – Install Paramiko and create the SSH key
📍 **Run on:** 🖥️ **Monitoring Server** (as root)
 
```bash
# on 🖥️ Monitoring Server
pip3 install flask requests openai paramiko
pip3 list | grep paramiko
 
ssh-keygen -t rsa -b 4096          # press Enter for all prompts
cat ~/.ssh/id_rsa.pub              # copy this whole line – you need it in Step 17
```
 
| Library | Why |
|---------|-----|
| Flask | Receives alerts |
| Requests | Calls Slack / Prometheus |
| Paramiko | SSH to EC2 |
| OpenAI | RCA analysis |
 
Also bring your AWS key-pair file to the monitoring server so you can log in to the test servers the first time:
 
```bash
vi MyKey.pem          # paste the contents of your AWS .pem file
chmod 400 MyKey.pem
```
 
### Step 17 – Authorize the monitoring server's key on Test-1 and Test-2
📍 **Run on:** 🟢 **Test-1** then 🟡 **Test-2** (each one separately)
 
First, from the 🖥️ Monitoring Server, log in to the test server (type the command manually – copy/paste often gives *Permission denied*):
 
```bash
# on 🖥️ Monitoring Server
ssh -i MyKey.pem ec2-user@<Test-1-private-IP>
```
 
Now you are on 🟢 Test-1. Stay as **ec2-user – do not use sudo**:
 
```bash
# on 🟢 Test-1
mkdir -p ~/.ssh
chmod 700 ~/.ssh
 
vi ~/.ssh/authorized_keys
```
Delete the old content and paste the public key from the monitoring server (`/root/.ssh/id_rsa.pub`, the line starting with `ssh-rsa ...`).
 
```bash
chmod 600 ~/.ssh/authorized_keys
exit
```
 
Back on 🖥️ Monitoring Server, test the passwordless login:
```bash
ssh -i ~/.ssh/id_rsa ec2-user@<Test-1-private-IP>
exit
```
 
🔁 **Repeat the same for 🟡 Test-2** using its private IP.
 
### Step 18 – Create the server inventory
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
vi /opt/aiops/servers.json
```
```json
{
  "Test-1": {
    "host": "<Test-1-private-IP>",
    "user": "ec2-user"
  },
 
  "Test-2": {
    "host": "<Test-2-private-IP>",
    "user": "ec2-user"
  }
}
```
 
> The key (`Test-1`) must match the `instance` label of the alert. Prometheus sets this label from the EC2 `Name` tag, which is why Step 2 asked you to create the `Name` tag.
 
Validate (be careful with commas):
```bash
python3 -m json.tool /opt/aiops/servers.json
```
 
### Step 19 – Create the SSH module and test it
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
vi /opt/aiops/ssh_client.py
```
```python
import paramiko
 
KEY = "/root/.ssh/id_rsa"
 
 
def run_command(host, user, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
 
    ssh.connect(hostname=host, username=user, key_filename=KEY)
 
    stdin, stdout, stderr = ssh.exec_command(command)
    output = stdout.read().decode()
 
    ssh.close()
    return output
```
 
Test:
```bash
cd /opt/aiops
vi test.py
```
```python
from ssh_client import run_command
 
print(run_command("<Test-1-private-IP>", "ec2-user", "uptime"))
```
```bash
python3 test.py
```
 
Collect live data (optional check):
```bash
vi collect.py
```
```python
from ssh_client import run_command
 
host = "<Test-1-private-IP>"
 
print(run_command(host, "ec2-user", "top -bn1 | head -15"))
print(run_command(host, "ec2-user", "free -m"))
print(run_command(host, "ec2-user", "df -h"))
print(run_command(host, "ec2-user", "uptime"))
print(run_command(host, "ec2-user", "systemctl --failed"))
```
```bash
python3 collect.py
```
 
### Step 20 – Install the AIOps engine with SSH evidence
📍 **Run on:** 🖥️ **Monitoring Server**
 
1. Replace `/opt/aiops/app.py` with the code in **[Appendix A – Final `app.py`](#appendix-a--final-apppy)**.
   *(It already contains SSH evidence collection, auto-remediation and RAG. Auto-remediation stays **OFF** because `AUTO_REMEDIATE=false` in `.env`, and RAG stays off until Phase 5.)*
2. Update the systemd service so it loads the `.env` file (already done in Step 12). Then:
```bash
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable aiops
systemctl restart aiops
systemctl status aiops
journalctl -u aiops -f
```
 
> Secrets (`SLACK_WEBHOOK`, `OPENAI_API_KEY`) come from `/opt/aiops/.env`, so do not hard-code them in `app.py`.
 
### Step 21 – Test SSH-based RCA
📍 **Run on:** 🟢 **Test-1**
 
```bash
stress --cpu 4 --timeout 300
```
 
Then:
 
- 🌐 Prometheus → Alerts: `HighCPUUsage` → pending → firing
- 💬 Slack: RCA that now contains real `top`, `free`, `df` data
- 🖥️ `journalctl -u aiops -f` to see logs
Quick test without waiting for Prometheus (on 🖥️ Monitoring Server):
```bash
curl -X POST http://localhost:5000/alert \
-H "Content-Type: application/json" \
-d '{
  "alerts": [{
    "labels": {
      "alertname": "TestAlert",
      "severity": "critical",
      "instance": "Test-1"
    }
  }]
}'
```
 
**If alerts don't reach Slack:** on 🖥️ edit `/etc/alertmanager/alertmanager.yml` and replace `localhost` with the **private IP of the monitoring server**, then:
```bash
systemctl restart alertmanager
systemctl restart aiops
journalctl -u alertmanager -f
```
(It can take a little time for the message to appear.)
 
#### Optional – Slack directly from Grafana
📍 **Run on:** 🌐 Grafana
 
1. **Alerting → Notification configuration (Contact points) → New contact point** → Name `slacknoti`, Integration **Slack**, paste webhook URL.
2. Open the *Node Exporter Full* dashboard → pick `Test-1` → panel **CPU Busy → ⋮ → More → New alert rule**.
3. Condition: query **is above 10**, create folder `CPU`, evaluation group `CPU` every `1m`, contact point `slacknoti` → **Create**.
4. Run `stress` on 🟢 Test-1 again → alert in Slack, and *Alerting → Alert rules* shows it **firing**.
✅ **Phase 3 complete:** AI collects real evidence over SSH.
 
---
 
# Part E – Phase 4: Auto-Remediation
 
Goal: after RCA the platform fixes the problem itself.
 
| Alert | Auto-fix performed |
|-------|--------------------|
| `InstanceDown` | restart service |
| `HighCPUUsage` | find top CPU process, optionally restart service |
| `HighMemoryUsage` | clear cache (`drop_caches`), optionally restart service |
| `HighDiskUsage` | clean old journal logs and `/tmp` files |
 
```
Prometheus Alert → Flask AIOps → Collect Metrics → AI RCA → Auto Fix → Slack Report
```
 
### Step 22 – Enable auto-remediation
📍 **Run on:** 🖥️ **Monitoring Server**
 
(The final `app.py` from Step 20 already contains this logic.)
 
```bash
vi /opt/aiops/.env
```
Change:
```ini
AUTO_REMEDIATE=true
```
Make sure the service reads the env file (in `/etc/systemd/system/aiops.service` you must have `EnvironmentFile=/opt/aiops/.env`):
 
```bash
sudo systemctl daemon-reload
sudo systemctl restart aiops
sudo journalctl -u aiops -f
```
 
Check: `curl http://localhost:5000/` → `"auto_remediation": true`
 
### Step 23 – Test auto-remediation
📍 **Run on:** 🟢 **Test-1**
 
```bash
stress --cpu 4 --timeout 300
```
Wait a few minutes → 💬 Slack message with: alert details, root cause, **before / after metrics**, action taken, and whether the issue improved.
 
✅ **Phase 4 complete.**
 
---
 
# Part F – Phase 5: Nginx Self-Healing + RAG
 
```
Nginx stopped on EC2
        ↓
Prometheus detects nginx_up == 0
        ↓
Alertmanager → Flask AIOps
        ↓
AIOps checks RAG runbook
        ↓
AIOps SSH into EC2
        ↓
Restart nginx
        ↓
Verify nginx status
        ↓
Slack report
```
 
### Step 24 – Install Nginx
📍 **Run on:** 🟢 **Test-1**
 
```bash
sudo dnf install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```
 
### Step 25 – Install the Nginx Prometheus Exporter
📍 **Run on:** 🟢 **Test-1**
 
```bash
cd /tmp
wget https://github.com/nginxinc/nginx-prometheus-exporter/releases/download/v1.1.0/nginx-prometheus-exporter_1.1.0_linux_amd64.tar.gz
tar -xvf nginx-prometheus-exporter_1.1.0_linux_amd64.tar.gz
sudo mv nginx-prometheus-exporter /usr/local/bin/
```
 
Enable the Nginx status page:
```bash
sudo vi /etc/nginx/conf.d/status.conf
```
```nginx
server {
    listen 8080;
 
    location /stub_status {
        stub_status;
        allow 127.0.0.1;
        deny all;
    }
}
```
```bash
sudo nginx -t
sudo systemctl restart nginx
curl http://127.0.0.1:8080/stub_status
```
 
Create the exporter service:
```bash
sudo vi /etc/systemd/system/nginx-exporter.service
```
```ini
[Unit]
Description=Nginx Prometheus Exporter
After=network.target nginx.service
 
[Service]
ExecStart=/usr/local/bin/nginx-prometheus-exporter -nginx.scrape-uri=http://127.0.0.1:8080/stub_status
Restart=always
 
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable nginx-exporter
sudo systemctl start nginx-exporter
sudo systemctl status nginx-exporter
 
curl http://localhost:9113/metrics | grep nginx_up     # should show nginx_up 1
```
 
### Step 26 – Add the Nginx exporter to Prometheus
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
sudo vi /etc/prometheus/prometheus.yml
```
Append this job at the end of `scrape_configs:` (keep the existing jobs). **Do NOT add `relabel_configs` here** – it would change the port to `:9100` and Nginx alerts would never fire.
 
```yaml
  - job_name: "nginx"
    static_configs:
      - targets:
          - "<Test-1-private-IP>:9113"
        labels:
          service: "nginx"
```
```bash
promtool check config /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
```
🌐 Check `http://<monitoring-public-ip>:9090/targets` – the `nginx` target must be **UP**.
 
### Step 27 – Add the Nginx alert, set real thresholds, remove TestAI
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
sudo vi /etc/prometheus/alert.rules.yml
```
 
1. **Add at the end** of the file (a new group, no indentation before `- name`):
```yaml
- name: nginx-alerts
  rules:
  - alert: NginxDown
    expr: nginx_up == 0
    for: 30s
    labels:
      severity: critical
      service: nginx
    annotations:
      summary: "Nginx is down"
      description: "Nginx service is down on {{ $labels.instance }}"
```
2. **Change test values to real ones:** `HighCPUUsage`, `HighMemoryUsage`, `HighDiskUsage` thresholds `> 10` → `> 80` so that only Nginx fires during the demo.
3. **Delete the `TestAI` rule** (it causes endless alerts).
```bash
promtool check rules /etc/prometheus/alert.rules.yml
grep -R "TestAI" /etc/prometheus/        # should return nothing
sudo systemctl restart prometheus
```
🌐 Prometheus → Alerts → everything should be **green**.
 
### Step 28 – Create the RAG runbook
📍 **Run on:** 🖥️ **Monitoring Server**
 
A **RAG runbook** is a normal operations runbook stored as a document. When an alert arrives, the AI searches these documents and uses the relevant content for the analysis and fix – the knowledge is not hard-coded in Python.
 
```bash
sudo mkdir -p /opt/aiops/knowledge
sudo vi /opt/aiops/knowledge/nginx_runbook.txt
```
```text
NginxDown Runbook:
 
Symptoms:
- nginx_up is 0
- Nginx service is stopped or exporter cannot scrape status endpoint
- Website may return connection refused or 502/503
 
Investigation:
- Run systemctl status nginx
- Run journalctl -u nginx -n 50 --no-pager
- Run nginx -t to validate configuration
- Run curl http://localhost:80
 
Safe Remediation:
- If nginx is stopped, run sudo systemctl start nginx
- If nginx failed due to bad config, do not restart repeatedly
- Validate config with sudo nginx -t before restart
- After start, verify with systemctl is-active nginx
- Verify nginx_up becomes 1
 
Rollback:
- If nginx fails to start, check /var/log/nginx/error.log
- Restore last known good config
```
 
### Step 29 – Install RAG dependencies and ingest the runbook
📍 **Run on:** 🖥️ **Monitoring Server**
 
```bash
cd /opt/aiops
pip3 install chromadb langchain-text-splitters openai
```
 
Create `rag_store.py` from **[Appendix B](#appendix-b--rag_storepy)**:
```bash
sudo vi /opt/aiops/rag_store.py
```
 
Ingest the runbook into ChromaDB:
```bash
export OPENAI_API_KEY="<your-openai-api-key>"
cd /opt/aiops
python3 -c "from rag_store import ingest_file; ingest_file('/opt/aiops/knowledge/nginx_runbook.txt')"
```
Expected output: `Ingested N chunks`
 
### Step 30 – Update the server inventory for Nginx
📍 **Run on:** 🖥️ **Monitoring Server**
 
The Nginx alert's `instance` label is `<Test-1-IP>:9113`, so the inventory needs that key too.
 
```bash
sudo vi /opt/aiops/servers.json
```
```json
{
  "Test-1": {
    "host": "<Test-1-private-IP>",
    "user": "ec2-user"
  },
 
  "Test-2": {
    "host": "<Test-2-private-IP>",
    "user": "ec2-user"
  },
 
  "<Test-1-private-IP>:9113": {
    "host": "<Test-1-private-IP>",
    "user": "ec2-user",
    "services": {
      "nginx": "nginx"
    }
  }
}
```
```bash
python3 -m json.tool /opt/aiops/servers.json      # every block needs a comma between entries
```
 
### Step 31 – Final Alertmanager configuration
📍 **Run on:** 🖥️ **Monitoring Server**
 
Grouping is tuned so Nginx alerts are delivered quickly.
 
```bash
sudo vi /etc/alertmanager/alertmanager.yml
```
```yaml
global:
  resolve_timeout: 5m
 
route:
  receiver: aiops
  group_by:
    - alertname
    - instance
    - service
  group_wait: 5s
  group_interval: 10s
  repeat_interval: 1m
 
receivers:
- name: aiops
  webhook_configs:
  - url: "http://<monitoring-private-IP>:5000/alert"
    send_resolved: true
```
```bash
amtool check-config /etc/alertmanager/alertmanager.yml
sudo systemctl restart alertmanager
sudo journalctl -u alertmanager -f
```
 
### Step 32 – Restart the AIOps service with the final code
📍 **Run on:** 🖥️ **Monitoring Server**
 
1. Confirm `/opt/aiops/app.py` is the **final version** from [Appendix A](#appendix-a--final-apppy).
2. Confirm `/opt/aiops/.env` has your real Slack webhook, OpenAI key and `AUTO_REMEDIATE=true`.
```bash
sudo systemctl daemon-reload
sudo systemctl restart prometheus
sudo systemctl restart alertmanager
sudo systemctl restart aiops
sudo systemctl status aiops
sudo journalctl -u aiops -f
 
curl http://localhost:5000/
# {"auto_remediation":true,"rag_enabled":true,"status":"running"}
```
 
### Step 33 – Final test: stop Nginx and watch it heal itself
📍 **Run on:** 🟢 **Test-1**
 
```bash
sudo systemctl stop nginx
sudo systemctl status nginx                       # inactive (dead)
curl localhost:9113/metrics | grep nginx_up       # nginx_up 0
```
 
Now watch the flow:
 
| Where | What you should see |
|-------|---------------------|
| 🌐 Prometheus → Alerts | `NginxDown` pending → firing |
| 🌐 Alertmanager `:9093/#/alerts` | `NginxDown` alert |
| 🖥️ Monitoring Server `journalctl -u aiops -f` | alert received, SSH commands, OpenAI call |
| 🟢 Test-1 `sudo systemctl status nginx` | Nginx is **active (running)** again |
| 💬 Slack | AI incident report: RCA, RAG runbook match, action taken, status improved |
 
Test without waiting for Prometheus (on 🖥️ Monitoring Server):
```bash
curl -X POST http://localhost:5000/alert \
-H "Content-Type: application/json" \
-d '{
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "NginxDown",
      "severity": "critical",
      "instance": "<Test-1-private-IP>:9113",
      "service": "nginx"
    }
  }]
}'
```
 
If Nginx is **not** restarted automatically:
- Check the `nginx` job in `prometheus.yml` has **no** `relabel_configs`.
- Check `servers.json` has the `<IP>:9113` key.
- Check `journalctl -u aiops -f` and `curl http://localhost:9093/api/v2/alerts | jq`.
- Check `AUTO_REMEDIATE=true`.
✅ **Phase 5 complete – you now have a self-healing AIOps platform!**
 
---
 
# Part G – Clean Up
 
📍 **Run on:** ☁️ AWS Console / OpenAI / Slack
 
1. **Delete the OpenAI API key.**
2. Remove/regenerate the Slack webhook.
3. **Terminate all EC2 instances** (Monitoring Server, Test-1, Test-2).
4. Delete unused security groups, key pairs and IAM roles.
---
 
# Appendix A – Final `app.py`
 
📍 **File location:** 🖥️ Monitoring Server → `/opt/aiops/app.py`
 
This single version includes: Prometheus metrics, SSH evidence, auto-remediation (InstanceDown / CPU / Memory / Disk / Nginx), RAG (optional), before/after verification and Slack reporting.
 
```python
from flask import Flask, request
import requests
import json
import os
import time
 
from openai import OpenAI
from ssh_client import run_command
 
try:
    from rag_store import search_knowledge
    RAG_ENABLED = True
except Exception:
    RAG_ENABLED = False
 
 
app = Flask(__name__)
 
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
AUTO_REMEDIATE = os.getenv("AUTO_REMEDIATE", "false").lower() == "true"
 
if not SLACK_WEBHOOK:
    raise ValueError("SLACK_WEBHOOK is not set")
 
if not OPENAI_KEY:
    raise ValueError("OPENAI_API_KEY is not set")
 
client = OpenAI(api_key=OPENAI_KEY)
 
 
with open("/opt/aiops/servers.json") as f:
    INVENTORY = json.load(f)
 
 
def query_prometheus(query):
    try:
        response = requests.get(
            f"{PROM_URL}/api/v1/query",
            params={"query": query},
            timeout=10
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}
 
 
def send_slack(message):
    try:
        response = requests.post(
            SLACK_WEBHOOK,
            json={"text": message},
            timeout=10
        )
        print("Slack status:", response.status_code)
        print("Slack response:", response.text)
    except Exception as e:
        print("Slack Error:", e)
 
 
def get_prometheus_metrics(instance):
    cpu_query = f'''
    100 - (
      avg by(instance) (
        rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[2m])
      ) * 100
    )
    '''
 
    memory_query = f'''
    (1 - (
      node_memory_MemAvailable_bytes{{instance="{instance}"}}
      /
      node_memory_MemTotal_bytes{{instance="{instance}"}}
    )) * 100
    '''
 
    disk_query = f'''
    (1 - (
      node_filesystem_avail_bytes{{instance="{instance}",fstype!~"tmpfs|overlay"}}
      /
      node_filesystem_size_bytes{{instance="{instance}",fstype!~"tmpfs|overlay"}}
    )) * 100
    '''
 
    nginx_query = f'''
    nginx_up{{instance="{instance}"}}
    '''
 
    return {
        "cpu": query_prometheus(cpu_query),
        "memory": query_prometheus(memory_query),
        "disk": query_prometheus(disk_query),
        "nginx": query_prometheus(nginx_query)
    }
 
 
def collect_evidence(host, user):
    return {
        "top": run_command(host, user, "top -bn1 | head -20"),
        "memory": run_command(host, user, "free -m"),
        "disk": run_command(host, user, "df -h"),
        "uptime": run_command(host, user, "uptime"),
        "failed_services": run_command(host, user, "systemctl --failed"),
        "top_cpu_process": run_command(
            host, user,
            "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10"
        ),
        "top_memory_process": run_command(
            host, user,
            "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -10"
        ),
        "journal_errors": run_command(
            host, user,
            "journalctl -p 3 -n 30 --no-pager"
        ),
        "nginx_status": run_command(
            host, user,
            "systemctl is-active nginx || true"
        ),
        "nginx_logs": run_command(
            host, user,
            "sudo -n journalctl -u nginx -n 30 --no-pager || true"
        )
    }
 
 
def get_rag_context(alert_name, severity, instance, service_name):
    if not RAG_ENABLED:
        return "RAG is not enabled or rag_store.py is not available."
 
    try:
        query = f"""
        Alert: {alert_name}
        Severity: {severity}
        Instance: {instance}
        Service: {service_name}
        Find matching runbook, previous incident, root cause and remediation.
        """
        return search_knowledge(query)
    except Exception as e:
        return f"RAG search failed: {str(e)}"
 
 
def remediate_nginx(host, user):
    actions = []
 
    before = run_command(host, user, "systemctl is-active nginx || true")
    actions.append(f"Nginx status before remediation:\n{before}")
 
    config_test = run_command(host, user, "sudo -n nginx -t 2>&1")
    actions.append(f"Nginx config test:\n{config_test}")
 
    if "syntax is ok" in config_test.lower() or "test is successful" in config_test.lower():
        start_result = run_command(host, user, "sudo -n systemctl start nginx")
        actions.append(f"Nginx start result:\n{start_result}")
    else:
        actions.append("Nginx config test failed. Start skipped for safety.")
 
    after = run_command(host, user, "systemctl is-active nginx || true")
    actions.append(f"Nginx status after remediation:\n{after}")
 
    logs = run_command(
        host, user,
        "sudo -n journalctl -u nginx -n 30 --no-pager || true"
    )
    actions.append(f"Nginx recent logs:\n{logs}")
 
    return "\n\n".join(actions)
 
 
def auto_remediate(alert_name, host, user, service_name=None):
    actions = []
 
    if not AUTO_REMEDIATE:
        return "Auto-remediation is disabled. Set AUTO_REMEDIATE=true to enable."
 
    if alert_name in ["NginxDown", "NginxExporterDown"] or service_name == "nginx":
        actions.append(remediate_nginx(host, user))
 
    elif alert_name == "InstanceDown":
        if service_name:
            cmd = f"sudo -n systemctl restart {service_name}"
            result = run_command(host, user, cmd)
            actions.append(f"Restarted service: {service_name}\n{result}")
        else:
            actions.append("InstanceDown detected, but no service label was provided.")
 
    elif alert_name == "HighCPUUsage":
        result = run_command(
            host, user,
            "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10"
        )
        actions.append(f"Top CPU processes:\n{result}")
 
        if service_name:
            restart = run_command(
                host, user,
                f"sudo -n systemctl restart {service_name}"
            )
            actions.append(f"Restarted high CPU service: {service_name}\n{restart}")
        else:
            actions.append("No service label provided. Restart skipped for safety.")
 
    elif alert_name == "HighMemoryUsage":
        result = run_command(
            host, user,
            "sync; echo 3 | sudo -n tee /proc/sys/vm/drop_caches"
        )
        actions.append(f"Cleared OS cache:\n{result}")
 
        if service_name:
            restart = run_command(
                host, user,
                f"sudo -n systemctl restart {service_name}"
            )
            actions.append(f"Restarted memory-heavy service: {service_name}\n{restart}")
 
    elif alert_name == "HighDiskUsage":
        clean_logs = run_command(
            host, user,
            "sudo -n journalctl --vacuum-time=1d && sudo -n find /tmp -type f -mtime +1 -delete"
        )
        actions.append(f"Cleaned logs and tmp files:\n{clean_logs}")
 
    else:
        actions.append("No remediation rule matched this alert.")
 
    return "\n\n".join(actions)
 
 
@app.route("/alert", methods=["POST"])
def alert():
    try:
        data = request.json
 
        if not data or "alerts" not in data:
            return {"status": "error", "message": "Invalid Alertmanager payload"}, 400
 
        alert = data["alerts"][0]
 
        alert_name = alert["labels"].get("alertname", "Unknown")
        severity = alert["labels"].get("severity", "warning")
        instance = alert["labels"].get("instance", "unknown")
        service_name = alert["labels"].get("service", None)
        alert_status = alert.get("status", "unknown")
 
        if instance in INVENTORY:
            host = INVENTORY[instance]["host"]
            user = INVENTORY[instance]["user"]
        else:
            host = "UNKNOWN"
            user = "UNKNOWN"
 
        metrics_before = get_prometheus_metrics(instance)
        rag_context = get_rag_context(alert_name, severity, instance, service_name)
 
        if host != "UNKNOWN":
            evidence = collect_evidence(host, user)
 
            remediation_result = auto_remediate(
                alert_name, host, user, service_name
            )
 
            time.sleep(10)
            metrics_after = get_prometheus_metrics(instance)
            evidence_after = collect_evidence(host, user)
 
        else:
            evidence = {
                "top": "N/A",
                "memory": "N/A",
                "disk": "N/A",
                "uptime": "N/A",
                "failed_services": "N/A",
                "top_cpu_process": "N/A",
                "top_memory_process": "N/A",
                "journal_errors": "N/A",
                "nginx_status": "N/A",
                "nginx_logs": "N/A"
            }
 
            evidence_after = evidence
            remediation_result = "Host not found in servers.json. Auto-remediation skipped."
            metrics_after = "N/A"
 
        prompt = f"""
You are a Senior Site Reliability Engineer.
 
Analyze this production incident using live evidence, Prometheus metrics, RAG runbook context, and auto-remediation output.
 
Alert Status:
{alert_status}
 
Alert Name:
{alert_name}
 
Severity:
{severity}
 
Instance:
{instance}
 
Service:
{service_name}
 
RAG / Runbook Context:
{rag_context}
 
Prometheus Metrics Before Remediation:
{metrics_before}
 
Server Evidence Before Remediation:
 
TOP:
{evidence["top"]}
 
TOP CPU PROCESSES:
{evidence["top_cpu_process"]}
 
TOP MEMORY PROCESSES:
{evidence["top_memory_process"]}
 
MEMORY:
{evidence["memory"]}
 
DISK:
{evidence["disk"]}
 
UPTIME:
{evidence["uptime"]}
 
FAILED SERVICES:
{evidence["failed_services"]}
 
JOURNAL ERRORS:
{evidence["journal_errors"]}
 
NGINX STATUS:
{evidence["nginx_status"]}
 
NGINX LOGS:
{evidence["nginx_logs"]}
 
Auto-Remediation Result:
{remediation_result}
 
Prometheus Metrics After Remediation:
{metrics_after}
 
Server Evidence After Remediation:
NGINX STATUS:
{evidence_after["nginx_status"]}
 
FAILED SERVICES:
{evidence_after["failed_services"]}
 
Provide a Slack-friendly incident report with:
 
1. Root Cause Analysis
2. RAG Runbook Match
3. Current CPU / Memory / Disk / Nginx Status
4. Business Impact
5. Auto-Remediation Action Taken
6. Whether the Issue Improved
7. Recommended Next Action
8. Preventive Measures
 
Do not give generic answers.
Use only the evidence provided.
Keep it clear and professional.
"""
 
        result = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
 
        analysis = result.choices[0].message.content
 
        slack_message = f"""
🚨 *AIOps Incident Analysis*
 
*Alert:* {alert_name}
*Status:* {alert_status}
*Instance:* {instance}
*Severity:* {severity}
*Service:* {service_name}
*Auto Remediation Enabled:* {AUTO_REMEDIATE}
*RAG Enabled:* {RAG_ENABLED}
 
{analysis}
"""
 
        send_slack(slack_message)
        print(slack_message)
 
        return {"status": "success"}
 
    except Exception as e:
        error_message = f"""
🚨 *AIOps Failure*
 
Error:
{str(e)}
"""
        print(error_message)
        send_slack(error_message)
 
        return {"status": "error", "message": str(e)}, 500
 
 
@app.route("/")
def home():
    return {
        "status": "running",
        "auto_remediation": AUTO_REMEDIATE,
        "rag_enabled": RAG_ENABLED
    }
 
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```
 
---
 
# Appendix B – `rag_store.py`
 
📍 **File location:** 🖥️ Monitoring Server → `/opt/aiops/rag_store.py`
 
```python
import os
import chromadb
from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
 
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
 
if not OPENAI_KEY:
    raise ValueError("OPENAI_API_KEY is not set")
 
client = OpenAI(api_key=OPENAI_KEY)
 
CHROMA_PATH = "/opt/aiops/vector_db"
COLLECTION_NAME = "aiops_knowledge"
 
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
 
 
def get_embedding(text):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding
 
 
def ingest_file(file_path):
    with open(file_path, "r") as f:
        content = f.read()
 
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )
 
    chunks = splitter.split_text(content)
 
    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
 
        collection.upsert(
            ids=[f"{file_path}-{i}"],
            documents=[chunk],
            embeddings=[embedding],
            metadatas=[{"source": file_path}]
        )
 
    print(f"Ingested {len(chunks)} chunks")
 
 
def search_knowledge(query, top_k=3):
    embedding = get_embedding(query)
 
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k
    )
 
    docs = results.get("documents", [[]])[0]
 
    return "\n\n".join(docs)
```
 
---
 
# Troubleshooting
 
| Problem | Where | Fix |
|---------|-------|-----|
| EC2 not discovered | 🖥️ | `aws ec2 describe-instances --region ap-south-1 \| grep node_server`; check tag `monitor=node_server` and IAM role |
| Changed alert rules | 🖥️ | `vi /etc/prometheus/alert.rules.yml` → `promtool check rules ...` → `systemctl restart prometheus` (lowercase **p**) |
| Config locations | 🖥️ | Alertmanager: `/etc/alertmanager/alertmanager.yml` · Rules: `/etc/prometheus/alert.rules.yml` |
| No alerts in Slack | 🖥️ | `journalctl -u alertmanager -f`; use monitoring **private IP** instead of `localhost` in the webhook URL; `curl http://localhost:9093/api/v2/alerts \| jq` |
| Nginx alert slow | 🖥️ | Use the grouping settings in Step 31 |
| `Permission denied` on SSH | 🖥️ | Use `ec2-user` (not root), `chmod 700 ~/.ssh`, `chmod 600 ~/.ssh/authorized_keys`, type the command manually |
| `servers.json` error | 🖥️ | `python3 -m json.tool /opt/aiops/servers.json` – check commas |
| AIOps won't start | 🖥️ | `journalctl -u aiops -n 100 --no-pager` – check `.env` values |
| Grafana datasource fails | 🌐 | URL must be `http://localhost:9090` (**9090**, not 9000) |
 
### Alertmanager permission fix
 
Error: `open /var/lib/alertmanager/nflog...: permission denied`
 
```bash
# on 🖥️ Monitoring Server
sudo systemctl stop alertmanager
sudo mkdir -p /var/lib/alertmanager
sudo chown -R prometheus:prometheus /var/lib/alertmanager
sudo chmod -R 755 /var/lib/alertmanager
sudo systemctl start alertmanager
sudo systemctl status alertmanager
sudo journalctl -u alertmanager -f
```
 
### Grafana repo fix
 
```bash
# on 🖥️ Monitoring Server
grep -R "grafana" /etc/yum.repos.d/
sudo rm -f /etc/yum.repos.d/*grafana*
ls -l /etc/yum.repos.d/
sudo dnf clean all
sudo rm -rf /var/cache/dnf
 
sudo tee /etc/yum.repos.d/grafana.repo >/dev/null <<'EOF'
[grafana]
name=Grafana
baseurl=https://rpm.grafana.com
enabled=1
gpgcheck=1
repo_gpgcheck=1
gpgkey=https://rpm.grafana.com/gpg.key
EOF
 
cat /etc/yum.repos.d/grafana.repo
sudo dnf makecache
sudo dnf repolist
sudo dnf install -y grafana
sudo systemctl enable grafana-server --now
```
 
---
 
# Security Notes
 
- Never commit `.env`, API keys or Slack webhooks. Rotate any key that was ever pasted into a document or chat.
- Use a least-privilege IAM role (`ec2:DescribeInstances`) instead of Admin for real use.
- Don't expose 9090 / 9093 / 3000 / 5000 to `0.0.0.0/0`.
- Change the default Grafana password.
- Keep `AUTO_REMEDIATE=false` until you trust the behaviour, and never run AI-generated commands directly.
---
 
# Roadmap
 
- [ ] Kubernetes support (cAdvisor, kube-state-metrics, `kubectl` remediation)
- [ ] Blackbox Exporter
- [ ] ServiceNow / Jira / Email / PagerDuty integrations
- [ ] More runbooks (CPU, memory, disk, DB)
- [ ] Upgrade to GPT-4o with structured JSON RCA
- [ ] Human approval via Slack buttons before risky fixes
---
 
## Key Technologies
 
Python · Flask · Prometheus · Alertmanager · Grafana · Node Exporter · Nginx Exporter · OpenAI GPT · RAG · ChromaDB · Paramiko (SSH) · Linux · systemd · Slack Webhooks · AWS EC2 · PromQL
 
