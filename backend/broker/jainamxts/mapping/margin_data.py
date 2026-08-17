"""Jainam XTS does not provide a margin calculator API."""


def transform_margin_positions(positions: list[dict]) -> list[dict]:
    return []


def parse_margin_response(response_data: dict) -> dict:
    return {
        "status": "error",
        "message": (response_data or {}).get(
            "message", "Jainam XTS does not support a margin calculator API"
        ),
    }
