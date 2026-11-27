import json

from aiops.app import create_app


def test_health_endpoint_defaults_to_safe_mode(monkeypatch):
    monkeypatch.setenv("AUTO_REMEDIATE", "false")
    client = create_app().test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["auto_remediation"] is False


def test_alert_endpoint_rejects_empty_payload():
    client = create_app().test_client()

    response = client.post("/alert", json={"alerts": []})

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_load_inventory_reads_configured_file(tmp_path, monkeypatch):
    from aiops.app import load_inventory

    inventory_path = tmp_path / "servers.json"
    inventory_path.write_text(json.dumps({"Test-1": {"host": "10.0.0.1"}}))
    monkeypatch.setenv("SERVERS_FILE", str(inventory_path))

    assert load_inventory()["Test-1"]["host"] == "10.0.0.1"
