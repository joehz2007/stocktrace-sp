import json

from app.config import load_email_config, web_host_port


def test_email_config_prefers_env(monkeypatch, tmp_path):
    cfg_file = tmp_path / "email_config.json"
    cfg_file.write_text(json.dumps({"smtp_host": "file-host", "username": "u", "password": "p", "from_addr": "f", "recipients": ["r@x.com"]}))
    monkeypatch.setenv("EMAIL_SMTP_HOST", "env-host")
    monkeypatch.setenv("EMAIL_USERNAME", "eu")
    monkeypatch.setenv("EMAIL_PASSWORD", "ep")
    monkeypatch.setenv("EMAIL_FROM", "ef@x.com")
    monkeypatch.setenv("EMAIL_RECIPIENTS", "a@x.com,b@x.com")
    cfg = load_email_config(str(cfg_file))
    assert cfg["smtp_host"] == "env-host"
    assert cfg["recipients"] == ["a@x.com", "b@x.com"]


def test_email_config_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS", raising=False)
    cfg_file = tmp_path / "email_config.json"
    cfg_file.write_text(json.dumps({"smtp_host": "file-host", "recipients": ["r@x.com"]}))
    cfg = load_email_config(str(cfg_file))
    assert cfg["smtp_host"] == "file-host"


def test_web_host_port_defaults(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert web_host_port() == ("127.0.0.1", 5001)


def test_web_host_port_env_override(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "5000")
    assert web_host_port() == ("0.0.0.0", 5000)
