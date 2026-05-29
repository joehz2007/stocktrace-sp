import html

from flask import Flask, redirect, request

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.db.connection import DEFAULT_DB_PATH
from app.email_sender import make_send_fn
from app.services import backfill as backfill_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.low_freq import refresh_low_freq
from app.services.notify import notify
from app.services.signals import LEVEL_LABELS, SIGNAL_LABELS, SIGNAL_THRESHOLDS
from app.services.stock_pool import resolve, split_inputs

_PAGE = "<html><head><meta charset='utf-8'><title>StockTrace</title></head><body>{body}</body></html>"


def _esc(v):
    return html.escape("" if v is None else str(v))


def _table(headers, rows):
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table border='1' cellpadding='4'><tr>{head}</tr>{body}</table>"


def create_app(db_path: str = DEFAULT_DB_PATH) -> Flask:
    app = Flask(__name__)

    def repo():
        return wiring.get_repo(db_path)

    def run_sync(codes=None, low_freq=False, do_notify=False):
        r = repo()
        if codes is None:
            codes = [s["code"] for s in r.list_stocks()]
        if low_freq:
            try:
                refresh_low_freq(r, codes, wiring.low_freq_sources())
            except Exception:  # web swallows low-freq errors
                pass
        macro_svc.sync_macro(r, wiring.index_fn, wiring.breadth_fn)
        snapshot_svc.sync_snapshots(r, codes, wiring.quote_fn, wiring.baidu_fn)
        if do_notify:
            cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
            notify(r, make_send_fn(cfg), cfg.get("recipients", []))

    @app.route("/")
    def index():
        r = repo()
        sort = request.args.get("sort", "code")
        direction = request.args.get("dir", "asc")
        # Render the whole pool: every stock shows, with its latest snapshot merged in
        # if one exists (a freshly-added stock has no snapshot until the first sync).
        latest_by_code = {s["code"]: dict(s) for s in r.latest_snapshot_per_stock()}
        snaps = []
        for stock in r.list_stocks():
            row = {"code": stock["code"], "name": stock["name"]}
            row.update(latest_by_code.get(stock["code"], {}))
            snaps.append(row)
        if snaps and sort in snaps[0]:
            snaps.sort(key=lambda s: (s.get(sort) is None, s.get(sort)), reverse=(direction == "desc"))
        cols = [("code", "代码"), ("name", "名称"), ("price", "现价"), ("change_pct", "涨跌幅"),
                ("pe_ttm", "PE_TTM"), ("roe", "ROE"), ("pb", "PB"), ("dividend_yield_ttm", "股息率TTM"),
                ("dist_ma20_pct", "距MA20"), ("dist_ma60_pct", "距MA60"),
                ("debt_to_asset_ratio", "资产负债率"), ("main_net_in", "主力净流入(万)")]
        headers = [f'<a href="/?sort={c}&dir={"desc" if direction == "asc" else "asc"}">{label}</a>'
                   for c, label in cols]
        rows = [[s.get(c) for c, _ in cols] for s in snaps]
        sources = {}
        for s in snaps:
            src = s.get("main_net_in_source") or "无"
            sources[src] = sources.get(src, 0) + 1
        times = [v["snapshot_time"] for v in latest_by_code.values() if v.get("snapshot_time")]
        latest_time = max(times) if times else "无"
        sh, sz = r.latest_macro("sh"), r.latest_macro("sz")
        macro_html = "".join(f"<p>{m['market']}: {m['index_point']} ({m['change_pct']}%)</p>"
                             for m in (sh, sz) if m)
        form = ('<form method="post" action="/add"><input name="text" placeholder="代码/名称,批量">'
                '<button>添加</button></form>'
                '<a href="/sync">立即同步</a> | <a href="/sync?low_freq=1">同步+低频</a> | '
                '<a href="/signals">信号</a> | <a href="/macro">宏观</a> | <a href="/snapshots">快照历史</a>')
        body = (f"<h1>StockTrace</h1>{form}<h2>沪深宏观</h2>{macro_html}"
                f"<p>最新快照时间: {_esc(latest_time)}</p>"
                f"<p>主力净流入来源: {_esc(sources)}</p>"
                f"<table border='1' cellpadding='4'><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"
                + "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows)
                + "</table>")
        return _PAGE.format(body=body)

    @app.route("/stock/<code>")
    def stock(code):
        r = repo()
        snaps = r.snapshots_for(code, 100)
        sigs = r.signals_for(code, 30)
        latest = dict(snaps[0]) if snaps else {}
        card = "".join(f"<p>{_esc(k)}: {_esc(v)}</p>" for k, v in latest.items())
        snap_tbl = _table(["时间", "现价", "涨跌幅", "距MA20", "距MA60"],
                          [[s["snapshot_time"], s["price"], s["change_pct"], s["dist_ma20_pct"], s["dist_ma60_pct"]] for s in snaps])
        sig_tbl = _table(["时间", "类型", "级别"],
                         [[s["snapshot_time"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]), LEVEL_LABELS.get(s["level"], s["level"])] for s in sigs])
        body = (f"<h1>{_esc(code)}</h1><a href='/sync?code={_esc(code)}'>只同步该股</a> | "
                f"<a href='/sync?code={_esc(code)}&low_freq=1'>只同步该股+低频</a> | <a href='/'>返回</a>"
                f"<h2>指标</h2>{card}<h2>最近100条快照</h2>{snap_tbl}<h2>最近30条信号</h2>{sig_tbl}")
        return _PAGE.format(body=body)

    @app.route("/signals")
    def signals_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]),
                 LEVEL_LABELS.get(s["level"], s["level"])] for s in r.recent_signals(200)]
        thresholds = "".join(f"<li>{_esc(SIGNAL_LABELS[k])}: {_esc(v)}</li>" for k, v in SIGNAL_THRESHOLDS.items())
        body = (f"<h1>信号</h1><a href='/'>返回</a>"
                f"<h2>阈值说明</h2><ul>{thresholds}</ul>"
                f"<h2>最近200条</h2>{_table(['时间', '代码', '名称', '类型', '级别'], rows)}")
        return _PAGE.format(body=body)

    @app.route("/macro")
    def macro_page():
        r = repo()
        rows = [[m["snapshot_time"], m["market"], m["index_point"], m["change_pct"],
                 m["up_count"], m["down_count"], m["flat_count"], m["total_count"]] for m in r.recent_macro(200)]
        body = f"<h1>宏观</h1><a href='/'>返回</a>{_table(['时间', '市场', '点位', '涨跌幅', '涨', '跌', '平', '总'], rows)}"
        return _PAGE.format(body=body)

    @app.route("/snapshots")
    def snapshots_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], s["price"], s["change_pct"]] for s in r.recent_snapshots(500)]
        body = f"<h1>快照历史</h1><a href='/'>返回</a>{_table(['时间', '代码', '名称', '现价', '涨跌幅'], rows)}"
        return _PAGE.format(body=body)

    @app.route("/add", methods=["POST"])
    def add():
        r = repo()
        for token in split_inputs(request.form.get("text", "")):
            try:
                res = resolve(token, wiring.search_fn)
                r.add_stock(res["code"], res["name"])  # batch ignores custom name by design
            except Exception:
                continue
        return redirect("/")

    @app.route("/sync")
    def sync():
        code = request.args.get("code")
        low_freq = request.args.get("low_freq") == "1"
        do_notify = request.args.get("notify") == "1"
        run_sync([code] if code else None, low_freq, do_notify)
        return redirect(f"/stock/{code}" if code else "/")

    @app.route("/backfill")
    def backfill_route():
        r = repo()
        start = request.args.get("start")
        end = request.args.get("end")
        codes = [s["code"] for s in r.list_stocks()]
        n = backfill_svc.backfill(r, codes, start, end)
        return _PAGE.format(body=f"<p>backfilled {n} signals</p><a href='/'>返回</a>")

    @app.route("/notify")
    def notify_route():
        r = repo()
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        try:
            n = notify(r, make_send_fn(cfg), cfg.get("recipients", []))
            msg = f"sent {n}"
        except Exception as exc:  # noqa: BLE001
            msg = f"notify error: {exc}"
        return _PAGE.format(body=f"<p>{_esc(msg)}</p><a href='/'>返回</a>")

    return app


def main() -> None:
    from app.config import web_host_port
    host, port = web_host_port()
    create_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
