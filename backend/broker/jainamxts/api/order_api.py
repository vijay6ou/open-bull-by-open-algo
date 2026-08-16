"""
Jainam XTS order API — place / modify / cancel + books.
Adapted from OpenAlgo's jainamxts order_api.py for the OpenBull contract.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from backend.broker.jainamxts.baseurl import get_interactive_url
from backend.broker.jainamxts.mapping.transform_data import (
    map_exchange,
    map_product_type,
    transform_data,
    transform_modify_order_data,
)
from backend.broker.jainamxts.xts_auth import dealer_client_candidates, resolve_client_id, split_auth
from backend.broker.upstox.mapping.order_data import (
    get_brsymbol_from_cache,
    get_token_from_cache,
)
from backend.utils.httpx_client import get_httpx_client

logger = logging.getLogger(__name__)


def _interactive(auth: str) -> str:
    token, _, _, _ = split_auth(auth)
    return token


def _client_id(auth: str) -> str:
    _, _, _, client_id = split_auth(auth)
    return client_id or resolve_client_id({})


_UNSET = object()


def _with_client(endpoint: str, client_id: str) -> str:
    if not client_id:
        return endpoint
    sep = "&" if "?" in endpoint else "?"
    return f"{endpoint}{sep}clientID={client_id}"


def get_api_response(endpoint: str, auth: str, method: str = "GET", payload=None, client_id=_UNSET) -> dict:
    cid = _client_id(auth) if client_id is _UNSET else (client_id or "")
    headers = {
        "authorization": _interactive(auth),
        "Content-Type": "application/json",
    }
    url = f"{get_interactive_url()}{_with_client(endpoint, cid)}"
    if isinstance(payload, dict) and cid and "clientID" not in payload:
        payload = {**payload, "clientID": cid}
    client = get_httpx_client()
    if method == "GET":
        response = client.get(url, headers=headers)
    elif method == "POST":
        response = client.post(url, headers=headers, json=payload)
    elif method == "PUT":
        response = client.put(url, headers=headers, json=payload)
    elif method == "DELETE":
        response = client.delete(url, headers=headers)
    else:
        response = client.request(method, url, headers=headers, json=payload)
    response.status = response.status_code
    try:
        return response.json()
    except Exception:
        return {"type": "error", "description": response.text, "status_code": response.status_code}


def _position_rows(data: dict) -> list:
    result = (data or {}).get("result")
    if isinstance(result, dict):
        rows = result.get("positionList") or result.get("PositionList") or []
        return rows if isinstance(rows, list) else []
    if isinstance(result, list):
        return result
    return []


def _result_rows(data: dict) -> list:
    result = (data or {}).get("result")
    if isinstance(result, dict):
        for key in ("positionList", "PositionList", "orderBook", "tradeBook", "orders", "trades"):
            rows = result.get(key)
            if isinstance(rows, list):
                return rows
        return []
    if isinstance(result, list):
        return result
    return []


def _dealer_first(regular: str, dealer: str, auth: str, nonempty=None) -> dict:
    """DMA dealer accounts reject investor endpoints; try dealer books with several clientIDs."""
    last: dict = {}
    for cid in dealer_client_candidates(auth):
        data = get_api_response(dealer, auth, client_id=cid)
        last = data
        if data.get("type") == "success":
            if nonempty is None or nonempty(data):
                return data
    data = get_api_response(regular, auth)
    if data.get("type") == "success":
        return data
    return last or data


def get_order_book(auth: str) -> dict:
    return _dealer_first(
        "/orders",
        "/orders/dealerorderbook",
        auth,
        nonempty=lambda data: bool(_result_rows(data)),
    )


def get_trade_book(auth: str) -> dict:
    return _dealer_first(
        "/orders/trades",
        "/orders/dealertradebook",
        auth,
        nonempty=lambda data: bool(_result_rows(data)),
    )


def get_positions(auth: str) -> dict:
    return _dealer_first(
        "/portfolio/positions?dayOrNet=NetWise",
        "/portfolio/dealerpositions?dayOrNet=NetWise",
        auth,
        nonempty=lambda data: bool(_position_rows(data)),
    )


def get_holdings(auth: str) -> dict:
    return get_api_response("/portfolio/holdings", auth)


_symbol_locks: dict[str, threading.Lock] = {}
_symbol_locks_lock = threading.Lock()
_position_cache: dict = {}
_position_cache_lock = threading.Lock()
_POSITION_CACHE_TTL = 1.0


def _get_symbol_lock(symbol: str, exchange: str, product: str) -> threading.Lock:
    key = f"{symbol}:{exchange}:{product}"
    with _symbol_locks_lock:
        if key not in _symbol_locks:
            _symbol_locks[key] = threading.Lock()
        return _symbol_locks[key]


def _get_cached_positions(auth: str) -> dict:
    with _position_cache_lock:
        now = time.monotonic()
        cached = _position_cache.get(auth)
        if cached and (now - cached["timestamp"]) < _POSITION_CACHE_TTL:
            return cached["data"]
    positions_data = get_positions(auth)
    with _position_cache_lock:
        _position_cache[auth] = {"data": positions_data, "timestamp": time.monotonic()}
    return positions_data


def _invalidate_position_cache(auth: str) -> None:
    with _position_cache_lock:
        _position_cache.pop(auth, None)


def get_open_position(tradingsymbol: str, exchange: str, producttype: str, auth: str) -> str:
    br_symbol = get_brsymbol_from_cache(tradingsymbol, exchange) or tradingsymbol
    xts_exchange = map_exchange(exchange)
    positions_data = _get_cached_positions(auth)
    net_qty = "0"
    if positions_data and positions_data.get("type") == "success":
        for position in (positions_data.get("result") or {}).get("positionList", []) or []:
            if (
                position.get("TradingSymbol") == br_symbol
                and position.get("ExchangeSegment") == xts_exchange
                and position.get("ProductType") == producttype
            ):
                net_qty = str(position.get("Quantity", 0))
                break
    return net_qty


def place_order_api(data: dict, auth: str) -> tuple:
    if all(k in data for k in ("exchangeSegment", "exchangeInstrumentID", "productType", "orderType")):
        newdata = data
    else:
        token = get_token_from_cache(data["symbol"], data["exchange"]) or ""
        newdata = transform_data(data, token)

    client = get_httpx_client()
    payload = newdata if isinstance(newdata, dict) else newdata
    if isinstance(payload, dict):
        client_id = _client_id(auth)
        if client_id:
            payload = {**payload, "clientID": client_id}
    response = client.post(
        f"{get_interactive_url()}{_with_client('/orders', _client_id(auth))}",
        headers={"authorization": _interactive(auth), "Content-Type": "application/json"},
        json=payload,
    )
    response.status = response.status_code
    try:
        response_data = response.json()
    except json.JSONDecodeError:
        response_data = {"error": "Invalid JSON response from server", "raw_response": response.text}

    orderid = (
        response_data.get("result", {}).get("AppOrderID")
        if response_data.get("type") == "success"
        else None
    )
    if orderid is not None:
        orderid = str(orderid)
    return response, response_data, orderid


def place_smartorder_api(data: dict, auth: str) -> tuple:
    res = None
    symbol = data.get("symbol")
    exchange = data.get("exchange")
    product = data.get("product")
    symbol_lock = _get_symbol_lock(symbol, exchange, product)

    with symbol_lock:
        position_size = int(data.get("position_size", "0"))
        current_position = int(get_open_position(symbol, exchange, map_product_type(product), auth))

        if position_size == 0 and current_position == 0 and int(data["quantity"]) != 0:
            res, response, orderid = place_order_api(data, auth)
            _invalidate_position_cache(auth)
            return res, response, orderid

        if position_size == current_position:
            if int(data["quantity"]) == 0:
                response = {"status": "success", "message": "No OpenPosition Found. Not placing Exit order."}
            else:
                response = {"status": "success", "message": "No action needed. Position size matches current position"}
            return res, response, None

        if position_size == 0 and current_position > 0:
            action, quantity = "SELL", abs(current_position)
        elif position_size == 0 and current_position < 0:
            action, quantity = "BUY", abs(current_position)
        elif current_position == 0:
            action, quantity = ("BUY" if position_size > 0 else "SELL"), abs(position_size)
        elif position_size > current_position:
            action, quantity = "BUY", position_size - current_position
        else:
            action, quantity = "SELL", current_position - position_size

        order_data = data.copy()
        order_data["action"] = action
        order_data["quantity"] = str(quantity)
        res, response, orderid = place_order_api(order_data, auth)
        _invalidate_position_cache(auth)
        return res, response, orderid


def close_all_positions(current_api_key, auth):
    positions_response = get_positions(auth)
    positions_list = (positions_response.get("result") or {}).get("positionList") or []
    if not positions_list:
        return {"message": "No Open Positions Found"}, 200

    for position in positions_list:
        qty = int(position.get("Quantity", 0) or 0)
        if qty == 0:
            continue
        action = "SELL" if qty > 0 else "BUY"
        payload = {
            "exchangeSegment": position["ExchangeSegment"],
            "exchangeInstrumentID": position["ExchangeInstrumentId"],
            "productType": position["ProductType"],
            "orderType": "MARKET",
            "orderSide": action,
            "timeInForce": "DAY",
            "disclosedQuantity": "0",
            "orderQuantity": str(abs(qty)),
            "limitPrice": "0",
            "stopPrice": "0",
            "orderUniqueIdentifier": "openbull",
        }
        place_order_api(payload, auth)
    return {"status": "success", "message": "All Open Positions SquaredOff"}, 200


def cancel_order(orderid: str, auth: str) -> tuple:
    client = get_httpx_client()
    response = client.delete(
        f"{get_interactive_url()}{_with_client(f'/orders?appOrderID={orderid}', _client_id(auth))}",
        headers={"authorization": _interactive(auth), "Content-Type": "application/json"},
    )
    response.status = response.status_code
    try:
        data = response.json()
    except Exception:
        data = {}
    if data.get("type") == "success" or data.get("status"):
        return {"status": "success", "orderid": orderid}, 200
    return {"status": "error", "message": data.get("description") or data.get("message") or "Failed to cancel order"}, response.status_code


def modify_order(data: dict, auth: str) -> tuple:
    token = get_token_from_cache(data["symbol"], data["exchange"]) or ""
    transformed = transform_modify_order_data(data, token)
    client_id = _client_id(auth)
    if client_id:
        transformed = {**transformed, "clientID": client_id}
    client = get_httpx_client()
    response = client.put(
        f"{get_interactive_url()}{_with_client('/orders', _client_id(auth))}",
        headers={"authorization": _interactive(auth), "Content-Type": "application/json"},
        json=transformed,
    )
    response.status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = {}
    if body.get("type") == "success" or body.get("status") in (True, "true", "success"):
        orderid = str(data.get("orderid", ""))
        result = body.get("result") or body.get("data") or {}
        if isinstance(result, dict) and result.get("AppOrderID"):
            orderid = str(result["AppOrderID"])
        return {"status": "success", "orderid": orderid}, 200
    return {"status": "error", "message": body.get("description") or body.get("message") or "Failed to modify order"}, response.status_code


def cancel_all_orders_api(data, auth: str) -> tuple[list, list]:
    book = get_order_book(auth)
    if book.get("type") != "success":
        return [], []
    orders = book.get("result") or []
    to_cancel = [o for o in orders if o.get("OrderStatus") in ("New", "Trigger Pending")]
    canceled, failed = [], []
    for order in to_cancel:
        orderid = order.get("AppOrderID")
        _, status_code = cancel_order(orderid, auth)
        if status_code == 200:
            canceled.append(orderid)
        else:
            failed.append(orderid)
    return canceled, failed
