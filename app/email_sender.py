import smtplib
from email.mime.text import MIMEText


def make_send_fn(cfg: dict):
    """Build a send_fn(recipient, subject, body) from email config."""
    def send_fn(recipient: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = recipient
        host = cfg["smtp_host"]
        port = int(cfg.get("smtp_port", 465))
        with smtplib.SMTP_SSL(host, port) as server:
            if cfg.get("username"):
                server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["from_addr"], [recipient], msg.as_string())
    return send_fn
