"""
Jainam XTS market data — quotes, multiquotes, depth, history.
OpenBull contract: module-level TIMEFRAME_MAP + get_quotes / get_multi_quotes /
get_market_depth / get_history.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from backend.broker.jainamxts.api.auth_api import get_feed_token as refresh_feed_token
from backend.broker.jainamxts.baseurl import get_market_data_url
from backend.broker.jainamxts.xts_auth import split_auth
from backend.broker.upstox.mapping.order_data import (
    get_brsymbol_from_cache,
    get_token_from_cache,
)
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "1s": "1",
    "1m": "60",
    "2m": "120",
    "3m": "180",
    "5m": "300",
    "10m": "600",
    "15m": "900",
    "30m": "1800",
    "60m": "3600",
    "1h": "3600",
    "D": "D",
}

SUPPORTED_INTERVALS = {
    "seconds": ["1s"],
    "minutes": ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m"],
    "hours": ["1h"],
    "days": ["D"],
}

EXCHANGE_SEGMENT = {
    "NSE": 1,
    "NSE_INDEX": 1,
    "NFO": 2,
    "CDS": 3,
    "BSE": 11,
    "BSE_INDEX": 11,
    "BFO": 12,
    "MCX": 51,
}

EXCHANGE_SEGMENT_NAME = {
    "NSE": "NSECM",
    "BSE": "BSECM",
    "NFO": "NSEFO",
    "BFO": "BSEFO",
    "CDS": "NSECD",
    "MCX": "MCXFO",
    "NSE_INDEX": "NSECM",
    "BSE_INDEX": "BSECM",
}

_QUOTE_BATCH = 50
_QUOTE_DELAY = 0.1

_SEG_NAME_TO_ID = {
    **EXCHANGE_SEGMENT,
    "NSECM": 1,
    "NSEFO": 2,
    "NSECD": 3,
    "BSECM": 11,
    "BSEFO": 12,
    "MCXFO": 51,
}


def _quote_key(segment, instrument_id) -> str:
    """Match quote responses whether ExchangeSegment is 2 or 'NSEFO'."""
    if isinstance(segment, str):
        segment = _SEG_NAME_TO_ID.get(segment.upper(), segment)
    return f"{segment}_{instrument_id}"


def _ltp(touchline: dict) -> float:
    try:
        return float(touchline.get("LastTradedPrice") or touchline.get("Close") or 0)
    except (TypeError, ValueError):
        return 0.0


def _feed(auth_token: str) -> str:
    _, feed, _, _ = split_auth(auth_token)
    return feed or split_auth(auth_token)[0]


def _empty_quote() -> dict:
    return {
        "ltp": 0, "open": 0, "high": 0, "low": 0, "prev_close": 0,
        "volume": 0, "oi": 0, "bid": 0, "ask": 0, "bid_qty": 0, "ask_qty": 0,
    }


def _api(endpoint: str, auth_token: str, method: str = "GET", payload=None, params=None) -> dict:
    headers = {"authorization": _feed(auth_token), "Content-Type": "application/json"}
    url = f"{get_market_data_url()}{endpoint}"
    client = get_httpx_client()
    if method.upper() == "GET":
        response = client.get(url, headers=headers, params=params)
    else:
        response = client.post(url, headers=headers, json=payload)
    try:
        return response.json()
    except Exception:
        logger.error("Jainam market-data non-JSON response: %s", response.text[:500])
        return {}


def _maybe_refresh(auth_token: str, config: dict | None, error_msg: str) -> str | None:
    if "Invalid Token" not in (error_msg or ""):
        return None
    new_feed, _, err = refresh_feed_token(config)
    if err or not new_feed:
        logger.error("Failed to refresh Jainam feed token: %s", err)
        return None
    interactive, _, user_id, client_id = split_auth(auth_token)
    from backend.broker.jainamxts.xts_auth import pack_auth
    return pack_auth(interactive, new_feed, user_id, client_id)


def _instrument(symbol: str, exchange: str) -> dict:
    token = get_token_from_cache(symbol, exchange)
    if not token:
        br = get_brsymbol_from_cache(symbol, exchange) or symbol
        raise ValueError(f"Could not find exchange token for {exchange}:{br}")
    segment = EXCHANGE_SEGMENT.get(exchange)
    if segment is None:
        raise ValueError(f"Unknown exchange segment: {exchange}")
    return {"exchangeSegment": segment, "exchangeInstrumentID": int(token) if str(token).isdigit() else token}


def _fetch_quotes(token: dict, message_code: int, auth_token: str, config: dict | None) -> dict | None:
    payload = {"instruments": [token], "xtsMessageCode": message_code, "publishFormat": "JSON"}
    response = _api("/instruments/quotes", auth_token, method="POST", payload=payload)
    if not response or response.get("type") != "success":
        error_msg = (response or {}).get("description", "Unknown error")
        refreshed = _maybe_refresh(auth_token, config, error_msg)
        if refreshed:
            return _fetch_quotes(token, message_code, refreshed, None)
        logger.warning("Jainam quotes error (code %s): %s", message_code, error_msg)
        return None
    list_quotes = (response.get("result") or {}).get("listQuotes") or []
    if not list_quotes:
        return None
    raw = list_quotes[0]
    return json.loads(raw) if isinstance(raw, str) else raw


def get_quotes(symbol: str, exchange: str, auth_token: str, config: dict | None = None) -> dict:
    token = _instrument(symbol, exchange)
    market = _fetch_quotes(token, 1502, auth_token, config)
    if not market:
        raise Exception("Failed to fetch market data")
    touchline = market.get("Touchline") or {}
    quote = {
        "ask": touchline.get("AskInfo", {}).get("Price", 0) or 0,
        "bid": touchline.get("BidInfo", {}).get("Price", 0) or 0,
        "high": touchline.get("High", 0) or 0,
        "low": touchline.get("Low", 0) or 0,
        "ltp": _ltp(touchline),
        "open": touchline.get("Open", 0) or 0,
        "prev_close": touchline.get("Close", 0) or 0,
        "volume": touchline.get("TotalTradedQuantity", 0) or 0,
        "oi": 0,
        "bid_qty": touchline.get("BidInfo", {}).get("Size", 0) or 0,
        "ask_qty": touchline.get("AskInfo", {}).get("Size", 0) or 0,
    }
    try:
        oi_data = _fetch_quotes(token, 1510, auth_token, config)
        if oi_data and "OpenInterest" in oi_data:
            quote["oi"] = oi_data["OpenInterest"] or 0
    except Exception as e:
        logger.warning("Failed to fetch OI: %s", e)
    return quote


def get_multi_quotes(symbols_list: list[dict], auth_token: str, config: dict | None = None) -> list[dict]:
    if not symbols_list:
        return []
    if len(symbols_list) <= _QUOTE_BATCH:
        return _process_multiquotes_batch(symbols_list, auth_token, config)

    all_results: list[dict] = []
    for i in range(0, len(symbols_list), _QUOTE_BATCH):
        batch = symbols_list[i : i + _QUOTE_BATCH]
        all_results.extend(_process_multiquotes_batch(batch, auth_token, config))
        if i + _QUOTE_BATCH < len(symbols_list):
            time.sleep(_QUOTE_DELAY)
    return all_results


def _process_multiquotes_batch(symbols: list[dict], auth_token: str, config: dict | None) -> list[dict]:
    instruments = []
    symbol_map = {}
    skipped = []
    for item in symbols:
        symbol, exchange = item.get("symbol"), item.get("exchange")
        if not symbol or not exchange:
            skipped.append({"symbol": symbol, "exchange": exchange, "data": None, "error": "Missing symbol or exchange"})
            continue
        try:
            inst = _instrument(symbol, exchange)
        except Exception as e:
            skipped.append({"symbol": symbol, "exchange": exchange, "data": None, "error": str(e)})
            continue
        instruments.append(inst)
        symbol_map[_quote_key(inst["exchangeSegment"], inst["exchangeInstrumentID"])] = {
            "symbol": symbol, "exchange": exchange,
        }

    if not instruments:
        return skipped

    payload = {"instruments": instruments, "xtsMessageCode": 1502, "publishFormat": "JSON"}
    response = _api("/instruments/quotes", auth_token, method="POST", payload=payload)
    if not response or response.get("type") != "success":
        error_msg = (response or {}).get("description", "Unknown error")
        refreshed = _maybe_refresh(auth_token, config, error_msg)
        if refreshed:
            return _process_multiquotes_batch(symbols, refreshed, None)
        raise Exception(f"Error from Jainam XTS API: {error_msg}")

    results = []
    for raw in (response.get("result") or {}).get("listQuotes") or []:
        try:
            quote_data = json.loads(raw) if isinstance(raw, str) else raw
            key = _quote_key(
                quote_data.get("ExchangeSegment"),
                quote_data.get("ExchangeInstrumentID"),
            )
            original = symbol_map.get(key)
            if not original:
                continue
            touchline = quote_data.get("Touchline") or {}
            results.append({
                "symbol": original["symbol"],
                "exchange": original["exchange"],
                "data": {
                    "ask": touchline.get("AskInfo", {}).get("Price", 0) or 0,
                    "bid": touchline.get("BidInfo", {}).get("Price", 0) or 0,
                    "high": touchline.get("High", 0) or 0,
                    "low": touchline.get("Low", 0) or 0,
                    "ltp": _ltp(touchline),
                    "open": touchline.get("Open", 0) or 0,
                    "prev_close": touchline.get("Close", 0) or 0,
                    "volume": touchline.get("TotalTradedQuantity", 0) or 0,
                    "oi": 0,
                },
            })
        except Exception as e:
            logger.warning("Error parsing Jainam multiquote: %s", e)
    return skipped + results


def get_market_depth(symbol: str, exchange: str, auth_token: str, config: dict | None = None) -> dict:
    empty = {
        "bids": [{"price": 0, "quantity": 0} for _ in range(5)],
        "asks": [{"price": 0, "quantity": 0} for _ in range(5)],
        "totalbuyqty": 0, "totalsellqty": 0, "ltp": 0, "ltq": 0,
        "volume": 0, "open": 0, "high": 0, "low": 0, "prev_close": 0, "oi": 0,
    }
    try:
        token = _instrument(symbol, exchange)
        market = _fetch_quotes(token, 1502, auth_token, config)
        if not market:
            return empty
        oi = 0
        try:
            oi_data = _fetch_quotes(token, 1510, auth_token, config)
            if oi_data and "OpenInterest" in oi_data:
                oi = oi_data["OpenInterest"] or 0
        except Exception:
            pass
        touchline = market.get("Touchline") or {}
        bids = [{"price": b.get("Price", 0), "quantity": b.get("Size", 0)} for b in (market.get("Bids") or [])[:5]]
        asks = [{"price": a.get("Price", 0), "quantity": a.get("Size", 0)} for a in (market.get("Asks") or [])[:5]]
        while len(bids) < 5:
            bids.append({"price": 0, "quantity": 0})
        while len(asks) < 5:
            asks.append({"price": 0, "quantity": 0})
        return {
            "bids": bids, "asks": asks,
            "high": touchline.get("High", 0) or 0,
            "low": touchline.get("Low", 0) or 0,
            "ltp": _ltp(touchline),
            "ltq": touchline.get("LastTradedQunatity") or touchline.get("LastTradedQuantity") or 0,
            "open": touchline.get("Open", 0) or 0,
            "prev_close": touchline.get("Close", 0) or 0,
            "volume": touchline.get("TotalTradedQuantity", 0) or 0,
            "oi": oi,
            "totalbuyqty": touchline.get("TotalBuyQuantity", 0) or 0,
            "totalsellqty": touchline.get("TotalSellQuantity", 0) or 0,
        }
    except Exception as e:
        logger.error("Error in Jainam get_market_depth: %s", e)
        return empty


def get_history(
    symbol: str, exchange: str, interval: str,
    start_date: str, end_date: str,
    auth_token: str, config: dict | None = None,
) -> list[dict]:
    compression = TIMEFRAME_MAP.get(interval)
    if not compression:
        raise ValueError(f"Unsupported interval: {interval}. Supported: {list(TIMEFRAME_MAP)}")

    token = get_token_from_cache(symbol, exchange)
    if not token:
        raise ValueError(f"Could not find exchange token for {exchange}:{symbol}")
    exchange_segment = EXCHANGE_SEGMENT_NAME.get(exchange)
    if not exchange_segment:
        raise ValueError(f"Unsupported exchange: {exchange}")

    start = pd.to_datetime(start_date).tz_localize("Asia/Kolkata")
    end = pd.to_datetime(end_date).tz_localize("Asia/Kolkata")
    from_date = start.replace(hour=0, minute=0, second=0, microsecond=0)
    to_date = end.replace(hour=23, minute=59, second=59, microsecond=0)

    dfs = []
    current_start = from_date
    working_auth = auth_token
    while current_start <= to_date:
        current_end = min(current_start + timedelta(days=6), to_date)
        params = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": token,
            "startTime": current_start.strftime("%b %d %Y %H%M%S"),
            "endTime": current_end.strftime("%b %d %Y %H%M%S"),
            "compressionValue": compression,
        }
        response = _api("/instruments/ohlc", working_auth, method="GET", params=params)
        if not response or response.get("type") != "success":
            error_msg = (response or {}).get("description", "Unknown error")
            refreshed = _maybe_refresh(working_auth, config, error_msg)
            if refreshed:
                working_auth = refreshed
                response = _api("/instruments/ohlc", working_auth, method="GET", params=params)
            if not response or response.get("type") != "success":
                raise Exception(f"Error from Jainam XTS API: {(response or {}).get('description', error_msg)}")

        raw = (response.get("result") or {}).get("dataReponse") or ""
        if raw:
            rows = []
            for row in raw.strip().split(","):
                fields = row.split("|")
                if len(fields) < 6:
                    continue
                try:
                    rows.append({
                        "timestamp": int(fields[0]),
                        "open": float(fields[1]),
                        "high": float(fields[2]),
                        "low": float(fields[3]),
                        "close": float(fields[4]),
                        "volume": int(float(fields[5])),
                        "oi": int(float(fields[6])) if len(fields) > 6 and fields[6] else 0,
                    })
                except (ValueError, IndexError):
                    continue
            if rows:
                dfs.append(pd.DataFrame(rows))
        current_start = current_end + timedelta(days=1)

    if not dfs:
        return []

    final_df = pd.concat(dfs, ignore_index=True)
    final_df = final_df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    final_df["timestamp"] = pd.to_datetime(final_df["timestamp"], unit="s")
    if compression == "D":
        final_df["timestamp"] = final_df["timestamp"].apply(lambda x: x.replace(hour=0, minute=0, second=0))
    else:
        final_df["timestamp"] = final_df["timestamp"] - pd.Timedelta(hours=5, minutes=30)
        interval_minutes = int(compression) // 60
        if interval_minutes > 0:
            final_df["timestamp"] = final_df["timestamp"].dt.floor(f"{interval_minutes}min")
    final_df["timestamp"] = final_df["timestamp"].astype("int64") // 10**9
    if "oi" not in final_df.columns:
        final_df["oi"] = 0
    records = final_df[["timestamp", "open", "high", "low", "close", "volume", "oi"]].to_dict(orient="records")
    for row in records:
        row["oi"] = int(row.get("oi") or 0)
        row["volume"] = int(row.get("volume") or 0)
    return records
