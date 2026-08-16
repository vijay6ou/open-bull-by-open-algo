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
    resolve_rms_client_id,
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
                    {
                        "type": "success",
                        "result": {
                            "token": "int-tok",
                            "userID": "USER1",
                            "clientCodes": ["ITC3278"],
                            "isInvestorClient": False,
                        },
                    },
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
    assert token == "int-tok:::feed-tok:::USER1:::ITC3278"
    assert posted[0][0] == "https://smpa.jainam.in:6543/hostlookup"
    assert posted[1][0] == "https://smpa.jainam.in:6543/1hostlookup/user/session"
    session_posts = [body for url, body in posted if url.endswith("/user/session")]
    assert session_posts
    assert session_posts[0]["source"] == "WEBAPI"
    assert session_posts[0]["uniqueKey"] == "uk-1"
    assert "accessToken" not in session_posts[0]
    assert "jtrade" not in "".join(url for url, _ in posted)


def test_strip_dealer_user_suffix():
    from backend.broker.jainamxts.xts_auth import (
        dealer_client_candidates,
        pick_trading_client_id,
        strip_dealer_user_suffix,
    )

    assert strip_dealer_user_suffix("ITC3278A06") == "ITC3278"
    assert strip_dealer_user_suffix("ITC3278") == ""
    assert strip_dealer_user_suffix("DLL7182") == ""
    assert pick_trading_client_id(
        {"client_id": "ITC3278A06"},
        {"clientCodes": ["ITC3278"], "userID": "ITC3278A06"},
    ) == "ITC3278"
    assert pick_trading_client_id({"client_id": "ITC3278A06"}, {}) == "ITC3278"
    packed = "tok:::feed:::USER:::ITC3278A06"
    candidates = dealer_client_candidates(packed)
    assert "ITC3278A06" in candidates
    assert "ITC3278" in candidates
    assert candidates[-1] is None


def test_rms_client_id_is_login_user_not_parent_book():
    """Funds/RMS must use ITC3278A06; positions keep packed trading client ITC3278."""
    packed = pack_auth("int-tok", "feed-tok", "ITC3278A06", "ITC3278")
    assert resolve_rms_client_id(packed, {"client_id": "ITC3278A06"}) == "ITC3278A06"
    assert resolve_rms_client_id(packed, {}) == "ITC3278A06"
    # Packed trading client (part 4) must not win even if user_id is missing
    # a dealer suffix — configured login user is preferred.
    packed_market_user = pack_auth("int-tok", "feed-tok", "USER1", "ITC3278")
    assert (
        resolve_rms_client_id(packed_market_user, {"client_id": "ITC3278A06"})
        == "ITC3278A06"
    )


def test_get_margin_data_queries_login_user(monkeypatch):
    captured: list[str] = []

    class _Resp:
        def json(self):
            return {
                "type": "success",
                "result": {
                    "BalanceList": [
                        {
                            "limitObject": {
                                "RMSSubLimits": {
                                    "netMarginAvailable": 1225432.37,
                                    "collateral": 0,
                                    "UnrealizedMTM": -98246.10,
                                    "RealizedMTM": 12.5,
                                    "marginUtilized": 13774567.63,
                                }
                            }
                        }
                    ]
                },
            }

    class _Client:
        def get(self, url, headers=None):
            captured.append(url)
            return _Resp()

    monkeypatch.setattr(
        "backend.broker.jainamxts.api.funds.get_httpx_client", lambda: _Client()
    )
    monkeypatch.setattr(
        "backend.broker.jainamxts.baseurl._settings_value", lambda _name: ""
    )
    monkeypatch.setattr(
        "backend.broker.jainamxts.xts_auth._settings_value", lambda _name: ""
    )
    monkeypatch.delenv("JAINAM_BASE_URL", raising=False)
    monkeypatch.delenv("JAINAM_ACTIVE_SYMPHONY_SERVER", raising=False)
    monkeypatch.delenv("JAINAMXTS_CLIENT_ID", raising=False)

    from backend.broker.jainamxts.api.funds import get_margin_data

    packed = pack_auth("int-tok", "feed-tok", "ITC3278A06", "ITC3278")
    data = get_margin_data(packed, {"client_id": "ITC3278A06"})
    assert captured
    assert "clientID=ITC3278A06" in captured[0]
    assert "clientID=ITC3278&" not in captured[0]
    assert not captured[0].endswith("clientID=ITC3278")
    assert data["availablecash"] == "1225432.37"
    assert data["m2munrealized"] == "-98246.10"
    assert data["m2mrealized"] == "12.50"
    assert data["utiliseddebits"] == "13774567.63"


def test_quote_key_normalizes_segment_name():
    from backend.broker.jainamxts.api.data import _quote_key, _ltp

    assert _quote_key(2, 12345) == _quote_key("NSEFO", 12345)
    assert _quote_key(1, "26000") == _quote_key("NSECM", "26000")
    assert _ltp({"LastTradedPrice": 0, "Close": 24366}) == 24366.0


def test_map_position_data_dealer_payload():
    from backend.broker.jainamxts.mapping.order_data import (
        map_position_data,
        transform_positions_data,
    )

    raw = {
        "type": "success",
        "result": {
            "positionList": [
                {
                    "AccountID": "ITC3278",
                    "TradingSymbol": "NIFTY 18AUG2026 CE 24450",
                    "ExchangeSegment": "NSEFO",
                    "ExchangeInstrumentId": 111,
                    "ProductType": "NRML",
                    "Quantity": "-520",
                    "SellAveragePrice": 120.5,
                    "LastTradedPrice": 130.0,
                    "UnrealizedMTM": -4940,
                }
            ]
        },
    }
    mapped = map_position_data(raw)
    rows = transform_positions_data(mapped)
    assert len(rows) == 1
    assert rows[0]["quantity"] == -520
    assert rows[0]["exchange"] == "NFO"
    assert rows[0]["symbol"]
    assert rows[0]["pnl"] == -4940.0
    assert rows[0]["average_price"] == 120.5
    assert isinstance(rows[0]["average_price"], float)

