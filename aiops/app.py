import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from .ssh_client import run_command


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)


def load_inventory() -> dict:
    path = Path(
        os.getenv("SERVERS_FILE", str(PROJECT_ROOT / "config" / "servers.json"))
    )
    if not path.is_file():
        raise FileNotFoundError(
            f"Server inventory not found: {path}. Copy config/servers.example.json "
            "to config/servers.json and update the host values."
        )

    inventory = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(inventory, dict):
        raise ValueError("Server inventory must be a JSON object")
    return inventory


def _escape_prometheus_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def query_prometheus(query: str) -> dict:
    base_url = os.getenv("PROM_URL", "http://localhost:9090").rstrip("/")
    response = requests.get(
        f"{base_url}/api/v1/query",
        params={"query": query},
        timeout=10,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {result}")
    return result


def get_prometheus_metrics(instance: str) -> dict:
    label = _escape_prometheus_label(instance)
    cpu_query = f"""
    100 - (
      avg by(instance) (
        rate(node_cpu_seconds_total{{mode="idle",instance="{label}"}}[2m])
      ) * 100
    )
    """
    memory_query = f"""
    (1 - (
      node_memory_MemAvailable_bytes{{instance="{label}"}}
      / node_memory_MemTotal_bytes{{instance="{label}"}}
    )) * 100
    """
    disk_query = f"""
    (1 - (
      node_filesystem_avail_bytes{{instance="{label}",fstype!~"tmpfs|overlay"}}
      / node_filesystem_size_bytes{{instance="{label}",fstype!~"tmpfs|overlay"}}
    )) * 100
    """
    nginx_query = f'nginx_up{{instance="{label}"}}'

    return {
        "cpu": query_prometheus(cpu_query),
        "memory": query_prometheus(memory_query),
        "disk": query_prometheus(disk_query),
        "nginx": query_prometheus(nginx_query),
    }


def collect_evidence(host: str, user: str) -> dict:
    commands = {
        "top": "top -bn1 | head -20",
        "memory": "free -m",
        "disk": "df -h",
        "uptime": "uptime",
        "failed_services": "systemctl --failed",
        "top_cpu_process": "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10",
        "top_memory_process": "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -10",
        "journal_errors": "journalctl -p 3 -n 30 --no-pager",
        "nginx_status": "systemctl is-active nginx || true",
        "nginx_logs": "sudo -n journalctl -u nginx -n 30 --no-pager || true",
    }
    return {
        name: run_command(host, user, command)
        for name, command in commands.items()
    }


def _allowed_service(
    instance_config: dict,
    service_label: Optional[str],
) -> Optional[str]:
    if not service_label:
        return None
    services = instance_config.get("services", {})
    service = services.get(service_label) if isinstance(services, dict) else None
    if not isinstance(service, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]+", service):
        return None
    return service


def _remediate_nginx(host: str, user: str) -> str:
    before = run_command(host, user, "systemctl is-active nginx || true")
    config_test = run_command(host, user, "sudo -n nginx -t 2>&1")
    actions = [f"Nginx status before remediation:\n{before}", f"Nginx config test:\n{config_test}"]

    if "syntax is ok" in config_test.lower() and "test is successful" in config_test.lower():
        result = run_command(host, user, "sudo -n systemctl start nginx")
        actions.append(f"Nginx start result:\n{result}")
    else:
        actions.append("Nginx config test failed; start skipped.")

    after = run_command(host, user, "systemctl is-active nginx || true")
    actions.append(f"Nginx status after remediation:\n{after}")
    return "\n\n".join(actions)


def auto_remediate(
    alert_name: str,
    host: str,
    user: str,
    instance_config: dict,
    service_label: Optional[str],
) -> str:
    if os.getenv("AUTO_REMEDIATE", "false").lower() != "true":
        return "Auto-remediation is disabled."

    service = _allowed_service(instance_config, service_label)
    if alert_name in {"NginxDown", "NginxExporterDown"}:
        if service != "nginx":
            return "Nginx remediation skipped: nginx is not allowed in this host's inventory."
        return _remediate_nginx(host, user)

    if alert_name == "InstanceDown":
        if not service:
            return "InstanceDown detected; no allow-listed service was provided."
        result = run_command(host, user, f"sudo -n systemctl restart {service}")
        return f"Restarted service {service}:\n{result}"

    if alert_name == "HighCPUUsage":
        processes = run_command(
            host,
            user,
            "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10",
        )
        if service:
            result = run_command(host, user, f"sudo -n systemctl restart {service}")
            return f"Top CPU processes:\n{processes}\n\nRestarted {service}:\n{result}"
        return f"Collected top CPU processes; no allow-listed service to restart:\n{processes}"

    if alert_name == "HighMemoryUsage":
        return run_command(
            host,
            user,
            "sync; echo 3 | sudo -n tee /proc/sys/vm/drop_caches",
        )

    if alert_name == "HighDiskUsage":
        return run_command(
            host,
            user,
            "sudo -n journalctl --vacuum-time=1d && "
            "sudo -n find /tmp -type f -mtime +1 -delete",
        )

    return "No remediation rule matched this alert."


def _gemini_analysis(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=30000),
    )
    result = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"),
        contents=prompt,
    )
    if not result.text:
        raise RuntimeError("Gemini returned an empty analysis")
    return result.text


def _rag_context(
    alert_name: str,
    severity: str,
    instance: str,
    service: Optional[str],
) -> str:
    if os.getenv("RAG_ENABLED", "true").lower() != "true":
        return "RAG is disabled."
    from .rag_store import search_knowledge

    query = (
        f"Alert: {alert_name}\nSeverity: {severity}\n"
        f"Instance: {instance}\nService: {service or 'unknown'}"
    )
    return search_knowledge(query)


def _send_slack(message: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")
    response = requests.post(webhook, json={"text": message}, timeout=10)
    response.raise_for_status()


def _handle_alert(alert: dict, inventory: dict) -> str:
    labels = alert.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("Alert is missing its labels object")

    alert_name = labels.get("alertname", "Unknown")
    severity = labels.get("severity", "warning")
    instance = labels.get("instance", "unknown")
    service_label = labels.get("service")
    status = alert.get("status", "unknown")

    instance_config = inventory.get(instance, {})
    if not isinstance(instance_config, dict):
        instance_config = {}
    host = instance_config.get("host")
    user = instance_config.get("user", "ec2-user")
    metrics_before = get_prometheus_metrics(instance)
    rag_context = _rag_context(alert_name, severity, instance, service_label)

    if host:
        evidence_before = collect_evidence(host, user)
        if status == "firing":
            remediation = auto_remediate(
                alert_name,
                host,
                user,
                instance_config,
                service_label,
            )
        else:
            remediation = "Alert is resolved; remediation was not run."

        if remediation != "Auto-remediation is disabled." and status == "firing":
            time.sleep(max(0, int(os.getenv("REMEDIATION_VERIFY_DELAY", "10"))))
        metrics_after = get_prometheus_metrics(instance)
        evidence_after = collect_evidence(host, user)
    else:
        evidence_before = {"status": "No matching host in config/servers.json"}
        evidence_after = evidence_before
        remediation = "Host not found in inventory; remediation skipped."
        metrics_after = "Not available"

    prompt = f"""
You are a senior site reliability engineer. Analyze the incident using only the supplied evidence.

Alert: {alert_name}
Status: {status}
Severity: {severity}
Instance: {instance}
Service: {service_label or "unknown"}

Relevant runbook:
{rag_context}

Prometheus metrics before remediation:
{json.dumps(metrics_before, ensure_ascii=False)}

Server evidence before remediation:
{json.dumps(evidence_before, ensure_ascii=False)}

Remediation result:
{remediation}

Prometheus metrics after remediation:
{json.dumps(metrics_after, ensure_ascii=False)}

Server evidence after remediation:
{json.dumps(evidence_after, ensure_ascii=False)}

Return a concise Slack-ready report with root cause, impact, actions taken, verification,
recommended next steps, and preventive measures. Do not claim improvement unless the evidence shows it.
"""
    analysis = _gemini_analysis(prompt)
    return (
        "*AIOps Incident Analysis*\n"
        f"*Alert:* {alert_name}\n*Status:* {status}\n"
        f"*Instance:* {instance}\n*Severity:* {severity}\n"
        f"*Service:* {service_label or 'unknown'}\n\n{analysis}"
    )


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def health():
        return jsonify(
            status="running",
            auto_remediation=os.getenv("AUTO_REMEDIATE", "false").lower() == "true",
            rag_enabled=os.getenv("RAG_ENABLED", "true").lower() == "true",
        )

    @app.post("/alert")
    def alert():
        payload = request.get_json(silent=True)
        alerts = payload.get("alerts") if isinstance(payload, dict) else None
        if not isinstance(alerts, list) or not alerts:
            return jsonify(status="error", message="Invalid Alertmanager payload"), 400

        try:
            inventory = load_inventory()
            messages = [_handle_alert(item, inventory) for item in alerts]
            for message in messages:
                _send_slack(message)
            return jsonify(status="success", processed=len(messages))
        except Exception as error:
            logger.exception("Failed to process Alertmanager webhook")
            return jsonify(status="error", message=str(error)), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
