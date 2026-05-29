import time

import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (StockTrace)"}
_RETRIES = 3
_BACKOFF = 0.6  # seconds, multiplied by attempt number


def _get(url: str, *, params, timeout, headers) -> requests.Response:
    """GET with a few retries — these data APIs (and flaky egress proxies)
    intermittently reset connections; a couple of backed-off retries make real
    runs far more reliable without masking genuine 4xx/5xx responses."""
    last_exc = None
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                 headers={**_HEADERS, **(headers or {})})
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc  # transient: connection reset / proxy drop / timeout
            if attempt < _RETRIES:
                time.sleep(_BACKOFF * attempt)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (502, 503, 504) and attempt < _RETRIES:
                last_exc = exc  # transient gateway/proxy error — retry
                time.sleep(_BACKOFF * attempt)
            else:
                raise  # genuine 4xx (and 5xx other than gateway) — do not retry
    raise last_exc


def http_get(url: str, *, params: dict | None = None, timeout: float = 10.0,
             headers: dict | None = None, encoding: str | None = None) -> str:
    resp = _get(url, params=params, timeout=timeout, headers=headers)
    if encoding:
        resp.encoding = encoding
    return resp.text


def http_get_json(url: str, *, params: dict | None = None, timeout: float = 10.0,
                  headers: dict | None = None) -> dict:
    return _get(url, params=params, timeout=timeout, headers=headers).json()
