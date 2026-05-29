import json
import os

from app.sources.baidu import parse_main_net_in

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_main_net_in():
    raw = json.load(open(os.path.join(_FIX, "baidu_fundflow.json"), encoding="utf-8"))
    assert parse_main_net_in(raw) == 1234.5


def test_parse_main_net_in_missing():
    assert parse_main_net_in({"Result": {}}) is None
