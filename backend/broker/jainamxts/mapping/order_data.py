"""Map Jainam XTS order/trade/position/holdings responses to OpenBull shape."""

from __future__ import annotations

import logging

from backend.broker.upstox.mapping.order_data import get_symbol_exchange_from_token

logger = logging.getLogger(__name__)

EXCHANGE_MAP = {
    "NSECM": "NSE",
    "BSECM": "BSE",
    "NSEFO": "NFO",
    "BSEFO": "BFO",
    "MCXFO": "MCX",
    "NSECD": "CDS",
}

ORDER_TYPE_MAP = {
    "Limit": "LIMIT",
    "Market": "MARKET",
    "StopLimit": "SL",
    "StopMarket": "SL-M",
}

ORDER_STATUS_MAP = {
    "Filled": "complete",
    "Rejected": "rejected",
    "Cancelled": "cancelled",
    "New": "open",
    "Trigger Pending": "trigger pending",
}


def _oa_symbol_from_token(token, exchange: str) -> str | None:
    info = get_symbol_exchange_from_token(str(token))
    if info:
        return info[0]
    return None


def map_order_data(order_data: dict | list) -> list[dict]:
    if not isinstance(order_data, dict) or "result" not in order_data or not order_data["result"]:
        return []

    rows = order_data["result"]
    if not isinstance(rows, list):
        return []

    for order in rows:
        token = order.get("ExchangeInstrumentID")
        exch = EXCHANGE_MAP.get(order.get("ExchangeSegment", ""), order.get("ExchangeSegment", ""))
        symbol = _oa_symbol_from_token(token, exch)
        if symbol:
            order["TradingSymbol"] = symbol
    return rows


def calculate_order_statistics(order_data: list[dict]) -> dict:
    total_buy = total_sell = total_completed = total_open = total_rejected = 0
    for order in order_data or []:
        if order.get("OrderSide") == "BUY":
            total_buy += 1
        elif order.get("OrderSide") == "SELL":
            total_sell += 1
        status = order.get("OrderStatus")
        if status == "Filled":
            total_completed += 1
        elif status in ("New", "Trigger Pending"):
            total_open += 1
        elif status == "Rejected":
            total_rejected += 1
    return {
        "total_buy_orders": total_buy,
        "total_sell_orders": total_sell,
        "total_completed_orders": total_completed,
        "total_open_orders": total_open,
        "total_rejected_orders": total_rejected,
    }


def transform_order_data(orders) -> list[dict]:
    if isinstance(orders, dict):
        orders = [orders]
    out = []
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        exchange = EXCHANGE_MAP.get(order.get("ExchangeSegment", ""), order.get("ExchangeSegment", ""))
        out.append({
            "symbol": order.get("TradingSymbol", ""),
            "exchange": exchange,
            "action": order.get("OrderSide", ""),
            "quantity": int(order.get("OrderQuantity", 0) or 0),
            "price": float(order.get("OrderPrice", 0) or 0),
            "trigger_price": float(order.get("OrderStopPrice", 0) or 0),
            "pricetype": ORDER_TYPE_MAP.get(order.get("OrderType", ""), order.get("OrderType", "")),
            "product": order.get("ProductType", ""),
            "orderid": str(int(float(order.get("AppOrderID", 0) or 0))),
            "order_status": ORDER_STATUS_MAP.get(order.get("OrderStatus", ""), order.get("OrderStatus", "")),
            "timestamp": order.get("LastUpdateDateTime", ""),
        })
    return out


def map_trade_data(trade_data: dict) -> list[dict]:
    if not isinstance(trade_data, dict) or "result" not in trade_data or not trade_data["result"]:
        return []
    rows = trade_data["result"]
    if not isinstance(rows, list):
        return []
    for trade in rows:
        token = trade.get("ExchangeInstrumentID")
        exch = EXCHANGE_MAP.get(trade.get("ExchangeSegment", ""), trade.get("ExchangeSegment", ""))
        symbol = _oa_symbol_from_token(token, exch)
        if symbol:
            trade["TradingSymbol"] = symbol
    return rows


def transform_tradebook_data(tradebook_data: list[dict]) -> list[dict]:
    out = []
    for trade in tradebook_data or []:
        exchange = EXCHANGE_MAP.get(trade.get("ExchangeSegment", ""), trade.get("ExchangeSegment", ""))
        qty = int(trade.get("OrderQuantity", 0) or 0)
        avg = float(trade.get("OrderAverageTradedPrice", 0) or 0)
        out.append({
            "symbol": trade.get("TradingSymbol", ""),
            "exchange": exchange,
            "product": trade.get("ProductType", ""),
            "action": trade.get("OrderSide", ""),
            "quantity": qty,
            "average_price": avg,
            "trade_value": qty * avg,
            "orderid": str(int(float(trade.get("AppOrderID", 0) or 0))),
            "timestamp": trade.get("OrderGeneratedDateTime", ""),
        })
    return out


def map_position_data(position_data: dict) -> dict | list:
    if not isinstance(position_data, dict) or "result" not in position_data or not position_data["result"]:
        return []
    return position_data["result"]


def transform_positions_data(positions_data) -> list[dict]:
    if isinstance(positions_data, dict):
        rows = positions_data.get("positionList", [])
    else:
        rows = positions_data or []
    if not isinstance(rows, list):
        return []

    out = []
    for position in rows:
        if not isinstance(position, dict):
            continue
        token = position.get("ExchangeInstrumentId")
        exchange = EXCHANGE_MAP.get(position.get("ExchangeSegment", ""), position.get("ExchangeSegment", ""))
        symbol = _oa_symbol_from_token(token, exchange) or position.get("TradingSymbol", "")
        qty = float(position.get("Quantity", 0) or 0)
        if qty > 0:
            avg = float(position.get("BuyAveragePrice", 0) or 0)
        elif qty < 0:
            avg = float(position.get("SellAveragePrice", 0) or 0)
        else:
            avg = 0.0
        out.append({
            "symbol": symbol,
            "exchange": exchange,
            "product": position.get("ProductType", ""),
            "quantity": int(qty),
            "average_price": f"{avg:.2f}",
            "ltp": float(position.get("ltp", 0) or 0),
            "pnl": float(position.get("pnl", 0) or 0),
        })
    return out


def map_portfolio_data(portfolio_data: dict) -> dict:
    if not portfolio_data or portfolio_data.get("type") != "success" or "result" not in portfolio_data:
        return {"holdings": [], "totalholding": None}

    holdings_data = (
        (portfolio_data.get("result") or {}).get("RMSHoldings") or {}
    ).get("Holdings") or {}

    holdings_list = []
    total_inv = 0.0
    for isin, holding in holdings_data.items():
        nse_id = holding.get("ExchangeNSEInstrumentId")
        symbol = _oa_symbol_from_token(nse_id, "NSE") or isin
        qty = holding.get("HoldingQuantity", 0) or 0
        buy_avg = holding.get("BuyAvgPrice", 0) or 0
        inv = float(qty) * float(buy_avg)
        holdings_list.append({
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "quantity": qty,
            "product": "CNC",
            "buy_price": buy_avg,
            "investment_value": inv,
            "current_value": inv,
            "profitandloss": 0,
            "pnlpercentage": 0,
        })
        total_inv += inv

    return {
        "holdings": holdings_list,
        "totalholding": {
            "totalholdingvalue": total_inv,
            "totalinvvalue": total_inv,
            "totalprofitandloss": 0,
            "totalpnlpercentage": 0,
        },
    }


def transform_holdings_data(holdings_data: dict) -> list[dict]:
    if not holdings_data or "holdings" not in holdings_data:
        return []
    return [
        {
            "symbol": h.get("tradingsymbol", ""),
            "exchange": h.get("exchange", ""),
            "quantity": h.get("quantity", 0),
            "product": h.get("product", ""),
            "pnl": h.get("profitandloss", 0.0),
            "pnlpercent": h.get("pnlpercentage", 0.0),
        }
        for h in holdings_data["holdings"]
    ]


def calculate_portfolio_statistics(holdings_data: dict) -> dict:
    total = holdings_data.get("totalholding") or {}
    return {
        "totalholdingvalue": total.get("totalholdingvalue", 0),
        "totalinvvalue": total.get("totalinvvalue", 0),
        "totalprofitandloss": total.get("totalprofitandloss", 0),
        "totalpnlpercentage": total.get("totalpnlpercentage", 0),
    }
