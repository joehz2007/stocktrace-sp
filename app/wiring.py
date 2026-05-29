"""Single assembly point: build real source-backed callables for services."""
from app.db.connection import DEFAULT_DB_PATH, connect
from app.db.repository import Repository
from app.services.low_freq import LowFreqSources
from app.sources import baidu, eastmoney, sina, tencent


def get_repo(db_path: str = DEFAULT_DB_PATH) -> Repository:
    return Repository(connect(db_path))


def quote_fn(codes):
    return tencent.fetch_quotes(codes)


def baidu_fn(code):
    try:
        return baidu.fetch_main_net_in(code)
    except Exception:
        return None


def index_fn(market):
    # Defensive: a data-source outage must not crash macro sync (the snapshot
    # endpoints stay usable). macro.sync_macro treats {} as empty fields.
    try:
        return tencent.fetch_index(market)
    except Exception:
        return {}


def breadth_fn(market):
    try:
        return eastmoney.fetch_breadth(market)
    except Exception:
        return {}


def search_fn(keyword):
    return tencent.search(keyword)


def low_freq_sources() -> LowFreqSources:
    return LowFreqSources(
        dividends_fn=eastmoney.fetch_dividends,
        fund_flow_fn=eastmoney.fetch_fund_flow,
        financial_fn=sina.fetch_financial,
        kline_fn=eastmoney.fetch_kline,
    )
