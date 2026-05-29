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
    """NOTE for maintainer: verified live (scripts/verify_baidu.py) that a bare
    request returns {"ResultCode":"403","Result":[]} — this endpoint needs a
    cookie / signed token. Until that auth is supplied, this returns None and the
    snapshot logic falls back to local daily fund_flow (by design). To enable
    Baidu, add the required auth and confirm the authenticated Result shape, then
    adjust parse_main_net_in's accessor to extract 万元 main inflow."""
    payload = http_get_json(
        "https://finance.pae.baidu.com/selfselect/getstockquotation",
        params={"code": code, "all": "1", "isIndex": "false", "finClientType": "pc"},
    )
    return parse_main_net_in(payload)
