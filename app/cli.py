import argparse

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.db.connection import DEFAULT_DB_PATH, init_db
from app.email_sender import make_send_fn
from app.services import backfill as backfill_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.low_freq import refresh_low_freq
from app.services.notify import notify
from app.services.stock_pool import resolve, split_inputs

DB_PATH = DEFAULT_DB_PATH


def _repo():
    return wiring.get_repo(DB_PATH)


def _do_sync(repo, codes, low_freq=False, do_notify=False):
    if codes is None:
        codes = [s["code"] for s in repo.list_stocks()]
    if low_freq:
        refresh_low_freq(repo, codes, wiring.low_freq_sources(),
                         on_error=lambda c, item, exc: print(f"[low-freq fail] {c} {item}: {exc}"))
    macro_svc.sync_macro(repo, wiring.index_fn, wiring.breadth_fn)
    snaps = snapshot_svc.sync_snapshots(repo, codes, wiring.quote_fn, wiring.baidu_fn)
    for s in snaps:
        print(f"{s['code']} {s.get('name') or ''} price={s.get('price')} "
              f"主力净流入(万)={s.get('main_net_in')} 来源={s.get('main_net_in_source')}")
    if do_notify:
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        notify(repo, make_send_fn(cfg), cfg.get("recipients", []))
    return snaps


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_add = sub.add_parser("add")
    p_add.add_argument("text")
    sub.add_parser("list")
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("codes", nargs="*")
    p_sync.add_argument("--low-freq", action="store_true")
    p_sync.add_argument("--notify", action="store_true")
    p_snap = sub.add_parser("snapshots")
    p_snap.add_argument("code")
    p_snap.add_argument("--limit", type=int, default=10)
    p_sig = sub.add_parser("signals")
    p_sig.add_argument("code", nargs="?")
    p_sig.add_argument("--limit", type=int, default=20)
    p_regen = sub.add_parser("regen-signals")
    p_regen.add_argument("date")
    p_macro = sub.add_parser("macro")
    p_macro.add_argument("--limit", type=int, default=10)
    sub.add_parser("notify")
    p_fc = sub.add_parser("forecast")
    p_fc.add_argument("code")
    p_fc.add_argument("--eps", type=float)
    p_fc.add_argument("--net-profit-yi", type=float)
    p_fc.add_argument("--source", default="manual")
    p_fin = sub.add_parser("financial")
    p_fin.add_argument("code")
    p_fin.add_argument("report_date")
    p_fin.add_argument("--net-profit", type=float)
    p_fin.add_argument("--equity", type=float)
    p_fin.add_argument("--total-assets", type=float)
    p_fin.add_argument("--total-liabilities", type=float)

    args = parser.parse_args(argv)

    if args.cmd == "init":
        init_db(DB_PATH)
        print(f"initialized {DB_PATH}")
        return
    repo = _repo()
    if args.cmd == "add":
        for token in split_inputs(args.text):
            try:
                r = resolve(token, wiring.search_fn)
                repo.add_stock(r["code"], r["name"])
                print(f"added {r['code']} {r['name']}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip {token}: {exc}")
    elif args.cmd == "list":
        for s in repo.list_stocks():
            print(f"{s['code']} {s['name']}")
    elif args.cmd == "sync":
        _do_sync(repo, args.codes or None, args.low_freq, args.notify)
    elif args.cmd == "snapshots":
        for s in repo.snapshots_for(args.code, args.limit):
            print(f"{s['snapshot_time']} price={s['price']} chg={s['change_pct']}")
    elif args.cmd == "signals":
        rows = repo.signals_for(args.code, args.limit) if args.code else repo.recent_signals(args.limit)
        for s in rows:
            print(f"{s['snapshot_time']} {s['code']} {s['signal_type']} {s['level']}")
    elif args.cmd == "regen-signals":
        n = backfill_svc.regen_signals(repo, args.date)
        print(f"regenerated {n} signals for {args.date}")
    elif args.cmd == "macro":
        for m in repo.recent_macro(args.limit):
            print(f"{m['snapshot_time']} {m['market']} {m['index_point']} {m['change_pct']}")
    elif args.cmd == "notify":
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        n = notify(repo, make_send_fn(cfg), cfg.get("recipients", []))
        print(f"sent {n}")
    elif args.cmd == "forecast":
        repo.upsert_forecast({"code": args.code, "forecast_eps": args.eps,
                              "forecast_net_profit_yi": args.net_profit_yi, "source": args.source})
        print(f"forecast saved for {args.code}")
    elif args.cmd == "financial":
        repo.upsert_financial({"code": args.code, "report_date": args.report_date,
                               "net_profit_attr": args.net_profit, "equity_attr": args.equity,
                               "total_assets": args.total_assets, "total_liabilities": args.total_liabilities})
        print(f"financial saved for {args.code} {args.report_date}")


if __name__ == "__main__":
    main()
