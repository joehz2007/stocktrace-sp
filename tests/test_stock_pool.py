from app.services.stock_pool import split_inputs, normalize_code, resolve, StockResolveError


def test_split_inputs_all_separators():
    text = "600519, 三七互娱、华钰股份；000858\n000001\t300750"
    assert split_inputs(text) == ["600519", "三七互娱", "华钰股份", "000858", "000001", "300750"]


def test_normalize_code_pads_and_validates():
    assert normalize_code("600519") == "600519"
    assert normalize_code("1") == "000001"
    assert normalize_code("abc") is None


def test_resolve_via_search():
    def search(kw):
        return [{"code": "600519", "name": "贵州茅台"}] if kw == "茅台" else []
    assert resolve("茅台", search) == {"code": "600519", "name": "贵州茅台"}


def test_resolve_numeric_fallback_when_search_empty():
    def search(kw):
        return []
    assert resolve("600519", search) == {"code": "600519", "name": "600519"}


def test_resolve_strips_suffix_and_retries():
    calls = []

    def search(kw):
        calls.append(kw)
        return [{"code": "000001", "name": "平安银行"}] if kw == "平安" else []
    assert resolve("平安股份", search) == {"code": "000001", "name": "平安银行"}
    assert calls == ["平安股份", "平安"]


def test_resolve_raises_friendly_error():
    def search(kw):
        return []
    try:
        resolve("不存在的票", search)
        assert False
    except StockResolveError as e:
        assert "不存在的票" in str(e)
