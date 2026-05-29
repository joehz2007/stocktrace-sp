from app.sources.baidu import parse_main_net_in


def _row(t, main):
    # 9 comma-separated fields; mainForce at index 2
    return f"{t},3.20,{main},-50.0,80.0,20.0,10.0,5.0,3.20"


def test_parse_main_net_in_takes_last_minute():
    ud = ";".join([_row("0930", "100.5"), _row("0931", "150.0"), _row("0932", "175.5")])
    payload = {"ResultCode": "0", "Result": {"update_data": ud}}
    assert parse_main_net_in(payload) == 175.5


def test_parse_main_net_in_accepts_int_result_code():
    payload = {"ResultCode": 0, "Result": {"update_data": _row("0930", "42.0")}}
    assert parse_main_net_in(payload) == 42.0


def test_parse_main_net_in_rejected_403():
    assert parse_main_net_in({"ResultCode": "403", "Result": []}) is None


def test_parse_main_net_in_empty():
    assert parse_main_net_in({"ResultCode": "0", "Result": {"update_data": ""}}) is None
