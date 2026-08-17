"""OpenBull <-> Jainam XTS order field mapping."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def transform_data(data: dict, token: str) -> dict:
    return {
        "exchangeSegment": map_exchange(data["exchange"]),
        "exchangeInstrumentID": int(token) if str(token).isdigit() else token,
        "productType": map_product_type(data["product"]),
        "orderType": map_order_type(data["pricetype"]),
        "orderSide": data["action"].upper(),
        "timeInForce": "DAY",
        "disclosedQuantity": data.get("disclosed_quantity", "0"),
        "orderQuantity": data["quantity"],
        "limitPrice": data.get("price", "0"),
        "stopPrice": data.get("trigger_price", "0"),
        "orderUniqueIdentifier": "openbull",
    }


def transform_modify_order_data(data: dict, token: str) -> dict:
    return {
        "appOrderID": data["orderid"],
        "modifiedProductType": map_product_type(data["product"]),
        "modifiedOrderType": map_order_type(data["pricetype"]),
        "modifiedOrderQuantity": data["quantity"],
        "modifiedDisclosedQuantity": data.get("disclosed_quantity", "0"),
        "modifiedLimitPrice": data["price"],
        "modifiedStopPrice": data.get("trigger_price", "0"),
        "modifiedTimeInForce": "DAY",
        "orderUniqueIdentifier": "openbull",
    }


def map_exchange(exchange: str) -> str:
    return {
        "NSE": "NSECM",
        "BSE": "BSECM",
        "MCX": "MCXFO",
        "NFO": "NSEFO",
        "BFO": "BSEFO",
        "CDS": "NSECD",
        "NSE_INDEX": "NSECM",
        "BSE_INDEX": "BSECM",
    }.get(exchange, exchange)


def map_order_type(pricetype: str) -> str:
    return {
        "MARKET": "MARKET",
        "LIMIT": "LIMIT",
        "SL": "STOPLIMIT",
        "SL-M": "STOPMARKET",
    }.get(pricetype, "MARKET")


def map_product_type(product: str) -> str:
    return {
        "CNC": "CNC",
        "NRML": "NRML",
        "MIS": "MIS",
    }.get(product, "MIS")


def reverse_map_product_type(exchange: str, product: str) -> str:
    return {"CNC": "CNC", "NRML": "NRML", "MIS": "MIS"}.get(product, product)
