"""
Custom exception handler for DRF.
Returns consistent JSON error responses across the entire API.
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("apps.core")


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to produce a unified error envelope:
    {
        "error": "Human-readable message",
        "details": { ... }   # optional extra context
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Normalise to our envelope
        original_data = response.data
        error_message = _extract_message(original_data)

        response.data = {
            "error": error_message,
            "details": original_data if isinstance(original_data, dict) else {},
        }
        logger.warning(
            "API error [%s]: %s — view: %s",
            response.status_code,
            error_message,
            context.get("view", "unknown"),
        )

    return response


def _extract_message(data):
    """Pull a human-readable message from DRF error data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list) and data:
        return str(data[0])
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        # Pick the first field error
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            if isinstance(value, str):
                return f"{key}: {value}"
    return "An error occurred."
