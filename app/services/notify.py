from app.services.signals import LEVEL_LABELS, SIGNAL_LABELS


class NotifyError(Exception):
    pass


def _format(signal) -> tuple[str, str]:
    stype = SIGNAL_LABELS.get(signal["signal_type"], signal["signal_type"])
    level = LEVEL_LABELS.get(signal["level"], signal["level"])
    subject = f"[StockTrace] {signal['code']} {signal['name'] or ''} {stype}"
    body = (f"股票：{signal['code']} {signal['name'] or ''}\n类型：{stype}\n级别：{level}\n"
            f"时间：{signal['snapshot_time']}\n说明：{signal['detail'] or ''}")
    return subject, body


def notify(repo, send_fn, recipients: list[str]) -> int:
    already = repo.notified_signal_recipient_pairs()
    sent_count = 0
    failures = []
    for sig in repo.all_signals():
        for recipient in recipients:
            if (sig["id"], recipient) in already:
                continue
            subject, body = _format(sig)
            try:
                send_fn(recipient, subject, body)
                repo.log_notification(sig["id"], recipient, "success", None)
                sent_count += 1
            except Exception as exc:  # noqa: BLE001
                repo.log_notification(sig["id"], recipient, "fail", str(exc))
                failures.append((sig["id"], recipient, str(exc)))
    if failures:
        raise NotifyError(f"{len(failures)} 封邮件发送失败: {failures}")
    return sent_count
