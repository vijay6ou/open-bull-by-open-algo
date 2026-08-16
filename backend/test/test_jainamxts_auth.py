"""Unit tests for Jainam DMA token packing, Symphony URLs, and credentials."""

from backend.broker.jainamxts.api.auth_api import _interactive_session_url
from backend.broker.jainamxts.api.data import SUPPORTED_INTERVALS, TIMEFRAME_MAP
from backend.broker.jainamxts.baseurl import (
    DEFAULT_BASE_URL,
    get_base_url,
    get_hostlookup_url,
    get_interactive_url,
    get_market_data_url,
)
from backend.broker.jainamxts.mapping.transform_data import map_exchange, map_order_type
from backend.broker.jainamxts.xts_auth import (
    env_order_keys_present,
    pack_auth,
    resolve_client_id,
    resolve_market_keys,
    resolve_order_keys,
    split_auth,
)


def test_pack_split_roundtrip():
    packed = pack_auth("interactive-token", "feed-token", "USER1", "ITC3278A06")
    assert packed == "interactive-token:::feed-token:::USER1:::ITC3278A06"
    assert split_auth(packed) == ("interactive-token", "feed-token", "USER1", "ITC3278A06")


def test_split_plain_token():
    assert split_auth("just-a-token") == ("just-a-token", "", "", "")
    assert split_auth(None) == ("", "", "", "")


def test_split_legacy_three_part_token():
    assert split_auth("interactive:::feed:::USER1") == ("interactive", "feed", "USER1", "")


def test_resolve_keys_from_config():
    config = {
        "api_key": "order-key",
        "api_secret": "order-secret",
        "api_key_market": "mkt-key",
        "api_secret_market": "mkt-secret",
        "client_id": "ITC3278A06",
    }
    assert resolve_order_keys(config) == ("order-key", "order-secret")
    assert resolve_market_keys(config) == ("mkt-key", "mkt-secret")
    assert resolve_client_id(config) == "ITC3278A06"


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


def test_resolve_client_id_from_env(monkeypatch):
    monkeypatch.setattr(
        "backend.broker.jainamxts.xts_auth._settings_value", lambda _name: ""
    )
    monkeypatch.setenv("JAINAMXTS_CLIENT_ID", "ITC3278A06")
    assert resolve_client_id({}) == "ITC3278A06"
    assert resolve_client_id({"client_id": ""}) == "ITC3278A06"


def test_dma_urls_are_symphony_not_retail_xts(monkeypatch):
    monkeypatch.setattr(
        "backend.broker.jainamxts.baseurl._settings_value", lambda _name: ""
    )
    monkeypatch.delenv("JAINAM_BASE_URL", raising=False)
    monkeypatch.delenv("JAINAM_ACTIVE_SYMPHONY_SERVER", raising=False)
    assert get_base_url() == "https://smpa.jainam.in:6543"
    assert get_hostlookup_url() == "https://smpa.jainam.in:6543/hostlookup"
    assert get_interactive_url() == "https://smpa.jainam.in:6543/interactive"
    assert get_market_data_url() == "https://smpa.jainam.in:6543/apibinarymarketdata"
    assert "jtrade" not in get_base_url()
    assert DEFAULT_BASE_URL == "https://smpa.jainam.in:6543"


def test_symphony_server_letter(monkeypatch):
    monkeypatch.setattr(
        "backend.broker.jainamxts.baseurl._settings_value", lambda _name: ""
    )
    monkeypatch.setenv("JAINAM_ACTIVE_SYMPHONY_SERVER", "B")
    assert get_base_url() == "https://smpb.jainam.in:4143"
    monkeypatch.setenv("JAINAM_ACTIVE_SYMPHONY_SERVER", "C")
    assert get_base_url() == "https://smpc.jainam.in:14543"


def test_interactive_session_url_from_hostlookup(monkeypatch):
    monkeypatch.setattr(
        "backend.broker.jainamxts.baseurl._settings_value", lambda _name: ""
    )
    monkeypatch.delenv("JAINAM_BASE_URL", raising=False)
    monkeypatch.delenv("JAINAM_ACTIVE_SYMPHONY_SERVER", raising=False)
    assert (
        _interactive_session_url("https://smpa.jainam.in:6543/1interactive")
        == "https://smpa.jainam.in:6543/1interactive/user/session"
    )
    assert (
        _interactive_session_url("/1interactive")
        == "https://smpa.jainam.in:6543/1interactive/user/session"
    )
    assert (
        _interactive_session_url(None)
        == "https://smpa.jainam.in:6543/interactive/user/session"
    )


def test_exchange_and_order_type_maps():
    assert map_exchange("NFO") == "NSEFO"
    assert map_exchange("BFO") == "BSEFO"
    assert map_order_type("SL") == "STOPLIMIT"
    assert map_order_type("SL-M") == "STOPMARKET"


def test_authenticate_skips_dummy_retail_access_token(monkeypatch):
    """DMA login must not send retail XTS dummy accessToken=jainamxts."""
    posted: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def post(self, url, json=None, headers=None, timeout=None):
            posted.append((url, json or {}))
            if url.endswith("/hostlookup"):
                return _Resp(
                    200,
                    {
                        "type": True,
                        "description": "Hostlookup successful",
                        "result": {
                            "uniqueKey": "uk-1",
                            "connectionString": "https://smpa.jainam.in:6543/1hostlookup",
                        },
                    },
                )
            if url.endswith("/user/session"):
                return _Resp(
                    200,
                    {"type": "success", "result": {"token": "int-tok", "userID": "USER1"}},
                )
            if url.endswith("/auth/login"):
                return _Resp(
                    200,
                    {"type": "success", "result": {"token": "feed-tok", "userID": "USER1"}},
                )
            return _Resp(404, {"type": "error", "description": url})

    monkeypatch.setattr(
        "backend.broker.jainamxts.api.auth_api.get_httpx_client", lambda: _Client()
    )
    monkeypatch.setattr(
        "backend.broker.jainamxts.baseurl._settings_value", lambda _name: ""
    )
    monkeypatch.delenv("JAINAM_BASE_URL", raising=False)
    monkeypatch.delenv("JAINAM_ACTIVE_SYMPHONY_SERVER", raising=False)

    from backend.broker.jainamxts.api.auth_api import authenticate_broker

    token, error = authenticate_broker(
        "jainamxts",
        {
            "api_key": "order-key",
            "api_secret": "order-secret",
            "api_key_market": "mkt-key",
            "api_secret_market": "mkt-secret",
            "client_id": "ITC3278A06",
        },
    )
    assert error is None
    assert token == "int-tok:::feed-tok:::USER1:::ITC3278A06"
    assert posted[0][0] == "https://smpa.jainam.in:6543/hostlookup"
    assert posted[1][0] == "https://smpa.jainam.in:6543/1hostlookup/user/session"
    session_posts = [body for url, body in posted if url.endswith("/user/session")]
    assert session_posts
    assert session_posts[0]["source"] == "WEBAPI"
    assert session_posts[0]["uniqueKey"] == "uk-1"
    assert "accessToken" not in session_posts[0]
    assert "jtrade" not in "".join(url for url, _ in posted)

