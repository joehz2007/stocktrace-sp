import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (StockTrace)"}


def http_get(url: str, *, params: dict | None = None, timeout: float = 10.0,
             headers: dict | None = None, encoding: str | None = None) -> str:
    resp = requests.get(url, params=params, timeout=timeout, headers={**_HEADERS, **(headers or {})})
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return resp.text


def http_get_json(url: str, *, params: dict | None = None, timeout: float = 10.0,
                  headers: dict | None = None) -> dict:
    resp = requests.get(url, params=params, timeout=timeout, headers={**_HEADERS, **(headers or {})})
    resp.raise_for_status()
    return resp.json()
