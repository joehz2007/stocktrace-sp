import json
import os

DATA_DIR = os.environ.get("STOCKTRACE_DATA_DIR", "data")
DEFAULT_EMAIL_CONFIG_PATH = os.path.join(DATA_DIR, "email_config.json")


def load_email_config(path: str = DEFAULT_EMAIL_CONFIG_PATH) -> dict:
    cfg: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    env_map = {
        "EMAIL_SMTP_HOST": "smtp_host",
        "EMAIL_SMTP_PORT": "smtp_port",
        "EMAIL_USERNAME": "username",
        "EMAIL_PASSWORD": "password",
        "EMAIL_FROM": "from_addr",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            cfg[cfg_key] = val
    recipients = os.environ.get("EMAIL_RECIPIENTS")
    if recipients is not None:
        cfg["recipients"] = [r.strip() for r in recipients.split(",") if r.strip()]
    return cfg


def web_host_port() -> tuple[str, int]:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))
    return host, port
