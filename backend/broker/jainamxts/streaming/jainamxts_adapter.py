"""
Jainam XTS streaming adapter.

Wraps the OpenAlgo Socket.IO client so it matches OpenBull's BaseBrokerAdapter:
connect / subscribe(symbols, mode) / unsubscribe / disconnect, and publishes
normalized ticks on the ZMQ bus.
"""

from __future__ import annotations

import logging
import threading
import time

from backend.broker.jainamxts.streaming.jainamxts_mapping import JainamXTSExchangeMapper
from backend.broker.jainamxts.streaming.jainamxts_websocket import JainamXTSWebSocketClient
from backend.broker.jainamxts.xts_auth import resolve_market_keys, split_auth
from backend.broker.upstox.mapping.order_data import (
    get_symbol_exchange_from_token,
    get_token_from_cache,
)
from backend.websocket_proxy.base_adapter import (
    BaseBrokerAdapter,
    MODE_DEPTH,
    MODE_LTP,
    MODE_QUOTE,
)

logger = logging.getLogger("jainamxts_stream")

NSE_INDEX_TOKENS = {"26000", "26001", "26008", "26009", "26037"}
BSE_INDEX_TOKENS = {"1", "12"}


class JainamXTSAdapter(BaseBrokerAdapter):
    def __init__(self, auth_token: str, broker_config: dict):
        super().__init__(auth_token, broker_config)
        _, feed_token, user_id, _ = split_auth(auth_token)
        api_key, api_secret = resolve_market_keys(broker_config)
        self._api_key = api_key
        self._api_secret = api_secret
        self._feed_token = feed_token
        self._user_id = user_id or ""
        self._client: JainamXTSWebSocketClient | None = None
        self._connected = False
        self._subscriptions: dict[tuple[str, str], int] = {}
        self._sub_lock = threading.Lock()
        self._last_close: dict[str, float] = {}

    def connect(self) -> None:
        if not self._api_key or not self._api_secret:
            raise ConnectionError(
                "Jainam XTS streaming requires market-data API key and secret. "
                "Save them on Broker Configuration."
            )
        self._running = True
        self._client = JainamXTSWebSocketClient(
            api_key=self._api_key,
            api_secret=self._api_secret,
            user_id=self._user_id,
        )
        self._client.on_open = self._on_open
        self._client.on_close = self._on_close
        self._client.on_error = self._on_error
        self._client.on_data = self._on_data
        logger.info("Connecting Jainam XTS Socket.IO market-data feed")
        self._client.connect()

    def subscribe(self, symbols: list[dict], mode: int) -> None:
        if not self._client:
            return
        instruments = []
        with self._sub_lock:
            for item in symbols:
                symbol, exchange = item.get("symbol"), item.get("exchange")
                if not symbol or not exchange:
                    continue
                token = get_token_from_cache(symbol, exchange)
                if not token:
                    logger.warning("No token for %s/%s — skip subscribe", symbol, exchange)
                    continue
                segment = JainamXTSExchangeMapper.get_exchange_type(exchange)
                instruments.append({
                    "exchangeSegment": segment,
                    "exchangeInstrumentID": str(token),
                })
                prev = self._subscriptions.get((symbol, exchange), 0)
                self._subscriptions[(symbol, exchange)] = max(prev, mode)
        if not instruments:
            return
        correlation_id = f"ob_{mode}_{int(time.time() * 1000)}"
        try:
            self._client.subscribe(correlation_id, mode, instruments)
        except Exception:
            logger.exception("Jainam subscribe failed")

    def unsubscribe(self, symbols: list[dict], mode: int) -> None:
        if not self._client:
            return
        instruments = []
        with self._sub_lock:
            for item in symbols:
                symbol, exchange = item.get("symbol"), item.get("exchange")
                if not symbol or not exchange:
                    continue
                token = get_token_from_cache(symbol, exchange)
                if token:
                    instruments.append({
                        "exchangeSegment": JainamXTSExchangeMapper.get_exchange_type(exchange),
                        "exchangeInstrumentID": str(token),
                    })
                self._subscriptions.pop((symbol, exchange), None)
        if not instruments:
            return
        try:
            self._client.unsubscribe(f"ob_{mode}_unsub", mode, instruments)
        except Exception:
            logger.exception("Jainam unsubscribe failed")

    def disconnect(self) -> None:
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                logger.exception("Error disconnecting Jainam XTS client")
            self._client = None
        self._connected = False

    def _on_open(self, _wsapp) -> None:
        self._connected = True
        logger.info("Jainam XTS Socket.IO connected")
        with self._sub_lock:
            grouped: dict[int, list[dict]] = {}
            for (symbol, exchange), mode in self._subscriptions.items():
                token = get_token_from_cache(symbol, exchange)
                if not token:
                    continue
                grouped.setdefault(mode, []).append({
                    "exchangeSegment": JainamXTSExchangeMapper.get_exchange_type(exchange),
                    "exchangeInstrumentID": str(token),
                })
        if self._client:
            for mode, instruments in grouped.items():
                try:
                    self._client.subscribe(f"ob_resync_{mode}", mode, instruments)
                except Exception:
                    logger.exception("Jainam resubscribe failed for mode %s", mode)

    def _on_close(self, _wsapp) -> None:
        self._connected = False
        logger.info("Jainam XTS Socket.IO closed")

    def _on_error(self, _wsapp, error) -> None:
        logger.error("Jainam XTS Socket.IO error: %s", error)

    def _resolve_symbol(self, instrument_id, exchange_segment: int) -> tuple[str, str] | None:
        token_str = str(instrument_id)
        if exchange_segment == 1 and token_str in NSE_INDEX_TOKENS:
            info = get_symbol_exchange_from_token(token_str)
            if info and info[1] == "NSE_INDEX":
                return info
            # try anyway
            if info:
                return info[0], "NSE_INDEX"
        if exchange_segment == 11 and token_str in BSE_INDEX_TOKENS:
            info = get_symbol_exchange_from_token(token_str)
            if info:
                return info[0], "BSE_INDEX"
        info = get_symbol_exchange_from_token(token_str)
        if info:
            return info
        return None

    def _on_data(self, _wsapp, message) -> None:
        if not isinstance(message, dict):
            return
        exchange_segment = message.get("ExchangeSegment")
        instrument_id = message.get("ExchangeInstrumentID")
        resolved = self._resolve_symbol(instrument_id, exchange_segment)
        if not resolved:
            return
        symbol, exchange = resolved
        ltp = self._extract_ltp(message)
        if not ltp:
            return
        token_str = str(instrument_id)
        close = message.get("Close") or (message.get("Touchline") or {}).get("Close") or self._last_close.get(token_str, 0) or 0
        if close:
            self._last_close[token_str] = float(close)
        change = round(ltp - float(close), 4) if close else 0.0
        change_pct = round((ltp - float(close)) / float(close) * 100, 4) if close else 0.0
        ltt = message.get("LastTradedTime") or (message.get("Touchline") or {}).get("LastTradedTime") or int(time.time())

        ltp_data = {
            "symbol": symbol, "exchange": exchange, "mode": "ltp",
            "ltp": ltp, "ltt": ltt, "cp": close, "change": change, "change_percent": change_pct,
        }
        self.publish(f"{exchange}_{symbol}_LTP", ltp_data)

        with self._sub_lock:
            sub_mode = self._subscriptions.get((symbol, exchange), MODE_LTP)

        if sub_mode >= MODE_QUOTE:
            touch = message.get("Touchline") or {}
            quote_data = {
                "symbol": symbol, "exchange": exchange, "mode": "quote",
                "ltp": ltp, "ltt": ltt,
                "open": message.get("Open") or touch.get("Open") or 0,
                "high": message.get("High") or touch.get("High") or 0,
                "low": message.get("Low") or touch.get("Low") or 0,
                "close": close,
                "volume": message.get("TotalTradedQuantity") or touch.get("TotalTradedQuantity") or 0,
                "oi": message.get("OpenInterest") or 0,
                "average_price": message.get("AverageTradedPrice") or touch.get("AverageTradedPrice") or 0,
                "total_buy_quantity": message.get("TotalBuyQuantity") or touch.get("TotalBuyQuantity") or 0,
                "total_sell_quantity": message.get("TotalSellQuantity") or touch.get("TotalSellQuantity") or 0,
                "cp": close, "change": change, "change_percent": change_pct,
            }
            self.publish(f"{exchange}_{symbol}_QUOTE", quote_data)

        if sub_mode >= MODE_DEPTH:
            bids = message.get("Bids") or []
            asks = message.get("Asks") or []
            depth_data = {
                "symbol": symbol, "exchange": exchange, "mode": "depth",
                "ltp": ltp,
                "bids": [{"price": b.get("Price", 0), "quantity": b.get("Size", 0)} for b in bids[:5]],
                "asks": [{"price": a.get("Price", 0), "quantity": a.get("Size", 0)} for a in asks[:5]],
                "oi": message.get("OpenInterest") or 0,
            }
            while len(depth_data["bids"]) < 5:
                depth_data["bids"].append({"price": 0, "quantity": 0})
            while len(depth_data["asks"]) < 5:
                depth_data["asks"].append({"price": 0, "quantity": 0})
            self.publish(f"{exchange}_{symbol}_DEPTH", depth_data)

    @staticmethod
    def _extract_ltp(message: dict) -> float:
        if message.get("LastTradedPrice"):
            try:
                return float(message["LastTradedPrice"])
            except (TypeError, ValueError):
                pass
        touch = message.get("Touchline") or {}
        if touch.get("LastTradedPrice"):
            try:
                return float(touch["LastTradedPrice"])
            except (TypeError, ValueError):
                pass
        return 0.0
