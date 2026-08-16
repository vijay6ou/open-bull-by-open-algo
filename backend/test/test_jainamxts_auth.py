"""Unit tests for Jainam XTS token packing and credential resolution."""

from backend.broker.jainamxts.xts_auth import (
    env_order_keys_present,
    pack_auth,
    resolve_market_keys,
    resolve_order_keys,
    split_auth,
)
from backend.broker.jainamxts.mapping.transform_data import map_exchange, map_order_type
from backend.broker.jainamxts.api.data import SUPPORTED_INTERVALS, TIMEFRAME_MAP


def test_pack_split_roundtrip():
    packed = pack_auth("interactive-token", "feed-token", "USER1")
    assert packed == "interactive-token:::feed-token:::USER1"
    assert split_auth(packed) == ("interactive-token", "feed-token", "USER1")


def test_split_plain_token():
    assert split_auth("just-a-token") == ("just-a-token", "", "")
    assert split_auth(None) == ("", "", "")


def test_resolve_keys_from_config():
    config = {
        "api_key": "order-key",
        "api_secret": "order-secret",
        "api_key_market": "mkt-key",
        "api_secret_market": "mkt-secret",
    }
    assert resolve_order_keys(config) == ("order-key", "order-secret")
    assert resolve_market_keys(config) == ("mkt-key", "mkt-secret")


def test_resolve_keys_prefer_config_over_env(monkeypatch):
    monkeypatch.setenv("BROKER_API_KEY", "env-order-key")
    monkeypatch.setenv("BROKER_API_SECRET", "env-order-secret")
    config = {"api_key": "cfg-key", "api_secret": "cfg-secret"}
    assert resolve_order_keys(config) == ("cfg-key", "cfg-secret")


def test_env_order_keys_present_from_openalgo_names(monkeypatch):
    monkeypatch.setattr(
        "backend.broker.jainamxts.xts_auth._settings_value", lambda _name: ""
    )
    monkeypatch.setenv("BROKER_API_KEY", "env-order-key")
    monkeypatch.setenv("BROKER_API_SECRET", "env-order-secret")
    assert env_order_keys_present() is True
    assert resolve_order_keys({}) == ("env-order-key", "env-order-secret")


def test_exchange_and_order_type_maps():
    assert map_exchange("NFO") == "NSEFO"
    assert map_exchange("BFO") == "BSEFO"
    assert map_order_type("SL") == "STOPLIMIT"
    assert map_order_type("SL-M") == "STOPMARKET"


def test_timeframe_map_has_openbull_intervals():
    for interval in ("1m", "5m", "15m", "1h", "D"):
        assert interval in TIMEFRAME_MAP
    assert "1h" in SUPPORTED_INTERVALS["hours"]
    assert "1m" in SUPPORTED_INTERVALS["minutes"]
