from app.sources.base import http_get_json


def parse_main_net_in(payload: dict):
    """Return main net inflow in 万元, or None. Baidu's real key may differ;
    keep this single accessor as the contract."""
    try:
        val = payload["Result"]["pankou_diagram"]["mainInflow"]
    except (KeyError, TypeError):
        return None
    if val in (None, ""):
        return None
    return float(val)


def fetch_main_net_in(code: str):
    """NOTE for maintainer: confirm Baidu 股市通 endpoint + query params with one
    real request; map response so parse_main_net_in extracts 万元 main inflow."""
    payload = http_get_json(
        "https://finance.pae.baidu.com/selfselect/getstockquotation",
        params={"code": code, "all": "1", "isIndex": "false", "finClientType": "pc"},
    )
    return parse_main_net_in(payload)
