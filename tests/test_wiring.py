import app.wiring as wiring
from app.sources import eastmoney, tencent


def test_breadth_fn_swallows_errors(monkeypatch):
    def boom(market):
        raise RuntimeError("502 Bad Gateway")
    monkeypatch.setattr(eastmoney, "fetch_breadth", boom)
    assert wiring.breadth_fn("sh") == {}  # must not raise -> macro sync stays alive


def test_index_fn_swallows_errors(monkeypatch):
    def boom(market):
        raise RuntimeError("connection reset")
    monkeypatch.setattr(tencent, "fetch_index", boom)
    assert wiring.index_fn("sh") == {}


def test_baidu_fn_swallows_errors(monkeypatch):
    def boom(code):
        raise RuntimeError("403")
    monkeypatch.setattr("app.sources.baidu.fetch_main_net_in", boom)
    assert wiring.baidu_fn("600519") is None
