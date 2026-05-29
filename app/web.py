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

_STYLE = """
*{box-sizing:border-box}
body{margin:0;background:#f5f6f8;color:#1f2329;
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
.container{max-width:1180px;margin:0 auto;padding:22px 24px 48px;}
h1{font-size:20px;margin:0 0 2px;font-weight:650;}
h2{font-size:14px;margin:24px 0 8px;color:#5b6168;font-weight:600;}
nav{margin:12px 0 4px;}
nav a{display:inline-block;margin:0 6px 6px 0;padding:6px 13px;background:#fff;border:1px solid #e2e6ea;
 border-radius:7px;color:#2563c9;text-decoration:none;font-size:13px;}
nav a:hover{background:#eef3fb;border-color:#cdd9ee;}
form{margin:10px 0;display:flex;gap:8px;flex-wrap:wrap;}
input[name=text]{flex:1;min-width:240px;padding:7px 11px;border:1px solid #dfe3e8;border-radius:7px;font-size:14px;}
button{padding:7px 16px;border:0;border-radius:7px;background:#2563c9;color:#fff;cursor:pointer;font-size:14px;}
button:hover{background:#1d50a8;}
.meta{color:#6b7178;font-size:13px;margin:4px 0;}
.macro{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0;}
.macro .m{background:#fff;border:1px solid #e2e6ea;border-radius:8px;padding:8px 14px;font-size:13px;}
table{border-collapse:separate;border-spacing:0;width:100%;background:#fff;border:1px solid #e2e6ea;
 border-radius:10px;overflow:hidden;font-variant-numeric:tabular-nums;}
th,td{padding:8px 11px;text-align:right;border-bottom:1px solid #eef1f4;white-space:nowrap;}
tbody tr:last-child td{border-bottom:0;}
th{background:#f4f6f9;font-weight:600;font-size:13px;color:#42474e;}
th a{color:#42474e;text-decoration:none;} th a:hover{color:#2563c9;}
td.t,th.t{text-align:left;}
tbody tr:hover td{background:#f9fafc;}
.up{color:#d33a2c;} .down{color:#1f9d57;} .muted{color:#aab0b6;}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0;}
.cards .c{background:#fff;border:1px solid #e2e6ea;border-radius:8px;padding:8px 12px;}
.cards .c .k{color:#8a9098;font-size:12px;} .cards .c .v{font-size:15px;font-weight:600;}
ul{padding-left:18px;} li{margin:3px 0;color:#42474e;}
"""

_PAGE = ("<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
         "<meta name='viewport' content='width=device-width,initial-scale=1'>"
         "<title>StockTrace</title><style>{style}</style></head>"
         "<body><div class='container'>{body}</div></body></html>")

# columns whose numeric sign drives 红涨绿跌 coloring
_SIGNED = {"change_pct", "dist_ma20_pct", "dist_ma60_pct", "main_net_in"}


def _esc(v):
    return html.escape("" if v is None else str(v))


def _td(value, *, left=False, signed=False):
    cls = "t" if left else ""
    if value is None:
        return f"<td class='{cls} muted'>-</td>"
    txt = f"{value:.2f}" if isinstance(value, float) else _esc(value)
    if signed and isinstance(value, (int, float)) and value != 0:
        cls = (cls + (" up" if value > 0 else " down")).strip()
    return f"<td class='{cls}'>{txt}</td>"


def _table(headers, rows, left_cols=(0, 1), signed_cols=()):
    head = "".join(f"<th class='{'t' if i in left_cols else ''}'>{_esc(h)}</th>"
                   for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(_td(c, left=(i in left_cols), signed=(i in signed_cols))
                         for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


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
        sources = {}
        for s in snaps:
            src = s.get("main_net_in_source") or "无"
            sources[src] = sources.get(src, 0) + 1
        times = [v["snapshot_time"] for v in latest_by_code.values() if v.get("snapshot_time")]
        latest_time = max(times) if times else "无"
        sources_txt = "、".join(f"{k}×{v}" for k, v in sources.items())

        def macro_card(m):
            chg = m["change_pct"] or 0
            cls = "up" if chg > 0 else ("down" if chg < 0 else "")
            return (f"<div class='m'><b>{_esc(m['market']).upper()}</b> {_esc(m['index_point'])} "
                    f"<span class='{cls}'>{chg:+.2f}%</span></div>")
        sh, sz = r.latest_macro("sh"), r.latest_macro("sz")
        macro_html = "<div class='macro'>" + "".join(macro_card(m) for m in (sh, sz) if m) + "</div>"

        form = ('<form method="post" action="/add">'
                '<input name="text" placeholder="代码 / 名称 / 简称,可批量(逗号、顿号、换行分隔)">'
                '<button>添加</button></form>')
        nav = ('<nav><a href="/sync">立即同步</a><a href="/sync?low_freq=1">同步+低频</a>'
               '<a href="/signals">信号</a><a href="/macro">宏观</a><a href="/snapshots">快照历史</a></nav>')
        thead = "".join(
            f"<th class='{'t' if i < 2 else ''}'>"
            f"<a href=\"/?sort={c}&dir={'desc' if direction == 'asc' else 'asc'}\">{label}</a></th>"
            for i, (c, label) in enumerate(cols))
        tbody = "".join(
            "<tr>" + "".join(_td(s.get(c), left=(i < 2), signed=(c in _SIGNED))
                             for i, (c, _) in enumerate(cols)) + "</tr>"
            for s in snaps)
        table = f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"
        body = (f"<h1>StockTrace</h1>{form}{nav}<h2>沪深宏观</h2>{macro_html}"
                f"<p class='meta'>最新快照时间 {_esc(latest_time)}　｜　主力净流入来源 {_esc(sources_txt or '无')}</p>"
                f"<h2>股票池</h2>{table}")
        return _PAGE.format(style=_STYLE, body=body)

    @app.route("/stock/<code>")
    def stock(code):
        r = repo()
        snaps = r.snapshots_for(code, 100)
        sigs = r.signals_for(code, 30)
        latest = dict(snaps[0]) if snaps else {}
        card_fields = [("price", "现价"), ("change_pct", "涨跌幅"), ("pe_ttm", "PE_TTM"), ("pe_static", "PE静"),
                       ("pb", "PB"), ("market_cap_yi", "总市值(亿)"), ("float_market_cap_yi", "流通市值(亿)"),
                       ("turnover_pct", "换手率"), ("volume_ratio", "量比"), ("amount_wan", "成交额(万)"),
                       ("roe", "ROE"), ("dividend_yield_ttm", "股息率TTM"), ("debt_to_asset_ratio", "资产负债率"),
                       ("ma20", "MA20"), ("ma60", "MA60"), ("dist_ma20_pct", "距MA20"),
                       ("dist_ma60_pct", "距MA60"), ("trend_status", "趋势"), ("main_net_in", "主力净流入(万)")]

        def card_val(k):
            v = latest.get(k)
            if v is None:
                return "<span class='muted'>-</span>"
            if isinstance(v, float):
                txt = f"{v:.2f}"
                if k in _SIGNED and v != 0:
                    return f"<span class='{'up' if v > 0 else 'down'}'>{txt}</span>"
                return txt
            return _esc(v)
        if latest:
            card = "<div class='cards'>" + "".join(
                f"<div class='c'><div class='k'>{_esc(lbl)}</div><div class='v'>{card_val(k)}</div></div>"
                for k, lbl in card_fields) + "</div>"
        else:
            card = "<p class='meta'>暂无快照,点上方“只同步该股”后查看。</p>"
        snap_tbl = _table(["时间", "现价", "涨跌幅", "距MA20", "距MA60"],
                          [[s["snapshot_time"], s["price"], s["change_pct"], s["dist_ma20_pct"], s["dist_ma60_pct"]] for s in snaps],
                          left_cols=(0,), signed_cols=(2, 3, 4))
        sig_tbl = _table(["时间", "类型", "级别"],
                         [[s["snapshot_time"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]), LEVEL_LABELS.get(s["level"], s["level"])] for s in sigs],
                         left_cols=(0, 1, 2))
        nav = (f"<nav><a href='/sync?code={_esc(code)}'>只同步该股</a>"
               f"<a href='/sync?code={_esc(code)}&low_freq=1'>＋低频</a><a href='/'>返回</a></nav>")
        title = f"{_esc(latest.get('name') or code)} <span class='muted'>{_esc(code)}</span>"
        body = (f"<h1>{title}</h1>{nav}<h2>核心指标</h2>{card}"
                f"<h2>最近100条快照</h2>{snap_tbl}<h2>最近30条信号</h2>{sig_tbl}")
        return _PAGE.format(style=_STYLE, body=body)

    @app.route("/signals")
    def signals_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]),
                 LEVEL_LABELS.get(s["level"], s["level"])] for s in r.recent_signals(200)]
        thresholds = "".join(f"<li>{_esc(SIGNAL_LABELS[k])}: {_esc(v)}</li>" for k, v in SIGNAL_THRESHOLDS.items())
        body = (f"<h1>信号</h1><nav><a href='/'>返回</a></nav>"
                f"<h2>阈值说明</h2><ul>{thresholds}</ul>"
                f"<h2>最近200条</h2>{_table(['时间', '代码', '名称', '类型', '级别'], rows, left_cols=(0, 1, 2, 3, 4))}")
        return _PAGE.format(style=_STYLE, body=body)

    @app.route("/macro")
    def macro_page():
        r = repo()
        rows = [[m["snapshot_time"], m["market"], m["index_point"], m["change_pct"],
                 m["up_count"], m["down_count"], m["flat_count"], m["total_count"]] for m in r.recent_macro(200)]
        body = (f"<h1>宏观</h1><nav><a href='/'>返回</a></nav>"
                f"{_table(['时间', '市场', '点位', '涨跌幅', '涨', '跌', '平', '总'], rows, left_cols=(0, 1), signed_cols=(3,))}")
        return _PAGE.format(style=_STYLE, body=body)

    @app.route("/snapshots")
    def snapshots_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], s["price"], s["change_pct"]] for s in r.recent_snapshots(500)]
        body = (f"<h1>快照历史</h1><nav><a href='/'>返回</a></nav>"
                f"{_table(['时间', '代码', '名称', '现价', '涨跌幅'], rows, left_cols=(0, 1, 2), signed_cols=(4,))}")
        return _PAGE.format(style=_STYLE, body=body)

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
        return _PAGE.format(style=_STYLE, body=f"<p>backfilled {n} signals</p><a href='/'>返回</a>")

    @app.route("/notify")
    def notify_route():
        r = repo()
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        try:
            n = notify(r, make_send_fn(cfg), cfg.get("recipients", []))
            msg = f"sent {n}"
        except Exception as exc:  # noqa: BLE001
            msg = f"notify error: {exc}"
        return _PAGE.format(style=_STYLE, body=f"<p>{_esc(msg)}</p><a href='/'>返回</a>")

    return app


def main() -> None:
    from app.config import web_host_port
    host, port = web_host_port()
    create_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
