from datetime import datetime, time

from apscheduler.schedulers.blocking import BlockingScheduler

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.email_sender import make_send_fn
from app.services import low_freq as low_freq_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.notify import notify

_AM = (time(9, 30), time(11, 35))
_PM = (time(13, 0), time(15, 10))


def should_run_intraday(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_AM[0] <= t <= _AM[1]) or (_PM[0] <= t <= _PM[1])


def intraday_job() -> None:
    if not should_run_intraday(datetime.now()):
        return
    repo = wiring.get_repo()
    codes = [s["code"] for s in repo.list_stocks()]
    macro_svc.sync_macro(repo, wiring.index_fn, wiring.breadth_fn)
    snapshot_svc.sync_snapshots(repo, codes, wiring.quote_fn, wiring.baidu_fn)
    try:
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        if cfg.get("recipients"):
            notify(repo, make_send_fn(cfg), cfg["recipients"])
    except Exception as exc:  # noqa: BLE001
        print(f"[notify fail] {exc}")


def low_freq_job() -> None:
    repo = wiring.get_repo()
    codes = [s["code"] for s in repo.list_stocks()]
    low_freq_svc.refresh_low_freq(repo, codes, wiring.low_freq_sources(),
                                  on_error=lambda c, item, exc: print(f"[low-freq fail] {c} {item}: {exc}"))


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler()
    sched.add_job(intraday_job, "interval", minutes=30, next_run_time=datetime.now(),
                  misfire_grace_time=1800, max_instances=1, coalesce=True)
    sched.add_job(low_freq_job, "cron", hour=20, minute=0, misfire_grace_time=3600, max_instances=1)
    return sched


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
