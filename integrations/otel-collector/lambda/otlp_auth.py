"""Shared OTLP authentication and header management for direct-send Lambda handlers.

This module centralizes the auth header construction and EXTRA_HEADERS_JSON
validation logic that all three handlers (handler.py, ems_handler.py,
fpolicy_handler.py) share. Extracting it here prevents drift when one handler
is updated but the others are not.

Usage:
    from otlp_auth import build_auth_headers, validate_extra_headers_json

    # At module level (startup validation):
    EXTRA_HEADERS_JSON = validate_extra_headers_json(
        os.environ.get("EXTRA_HEADERS_JSON", ""), logger
    )

    # At request time:
    headers = build_auth_headers(auth_mode, auth_header_name, token, extra_headers_json, logger)
"""

from __future__ import annotations

import json
import logging
from typing import Optional


# Headers that EXTRA_HEADERS_JSON must never override.
# Compared case-insensitively against keys in the parsed JSON.
_RESERVED_HEADERS = frozenset([
    "authorization",
    "content-type",
    "content-length",
    "host",
])


def validate_extra_headers_json(raw: str, logger: logging.Logger) -> str:
    """Validate EXTRA_HEADERS_JSON at startup. Returns cleaned value or empty string.

    - Rejects non-dict JSON (arrays, strings, numbers)
    - Rejects reserved header names (case-insensitive)
    - Rejects non-string values
    - Returns empty string on any validation failure (headers will be skipped)
    """
    if not raw:
        return ""

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("EXTRA_HEADERS_JSON is not valid JSON: %s. Extra headers will be ignored.", e)
        return ""

    if not isinstance(parsed, dict):
        logger.error(
            "EXTRA_HEADERS_JSON must be a JSON object (dict), got %s. "
            "Extra headers will be ignored.", type(parsed).__name__
        )
        return ""

    # Check for reserved headers and non-string values
    cleaned = {}
    for key, value in parsed.items():
        if key.lower() in _RESERVED_HEADERS:
            logger.warning(
                "EXTRA_HEADERS_JSON contains reserved header '%s' which will be ignored. "
                "Use AUTH_MODE/OTLP_CONTENT_TYPE settings instead.", key
            )
            continue
        if not isinstance(value, str):
            logger.warning(
                "EXTRA_HEADERS_JSON value for '%s' is not a string (got %s), skipping.",
                key, type(value).__name__
            )
            continue
        cleaned[key] = value

    if not cleaned:
        return ""

    return json.dumps(cleaned)


def validate_auth_mode_header(
    auth_mode: str, auth_header_name: str, logger: logging.Logger
) -> None:
    """Warn if AUTH_MODE=header but AUTH_HEADER_NAME is not properly configured."""
    if auth_mode == "header" and (not auth_header_name or auth_header_name == "Authorization"):
        logger.warning(
            "AUTH_MODE=header but AUTH_HEADER_NAME is empty or still 'Authorization'. "
            "Set AUTH_HEADER_NAME to the vendor's custom header name "
            "(e.g. 'Mackerel-Api-Key'). Requests may fail with 401/403."
        )


def build_auth_headers(
    auth_mode: str,
    auth_header_name: str,
    token: Optional[str],
    extra_headers_json: str,
    logger: logging.Logger,
) -> dict[str, str]:
    """Build the complete set of auth + extra headers for an OTLP request.

    Args:
        auth_mode: "bearer", "basic", "header", or "none"
        auth_header_name: Header name for AUTH_MODE=header (e.g. "Mackerel-Api-Key")
        token: The secret/token value (may be None if no API key configured)
        extra_headers_json: Validated JSON string of extra headers (or empty)
        logger: Logger instance for warnings

    Returns:
        Dict of header name → value to include in the OTLP request.
    """
    import base64

    auth_headers: dict[str, str] = {}

    if token:
        if auth_mode == "basic":
            encoded = base64.b64encode(token.encode("utf-8")).decode("utf-8")
            auth_headers = {"Authorization": f"Basic {encoded}"}
        elif auth_mode == "header":
            auth_headers = {auth_header_name: token}
        elif auth_mode == "bearer":
            auth_headers = {"Authorization": f"Bearer {token}"}
        # auth_mode == "none": no auth headers

    if extra_headers_json:
        try:
            extra = json.loads(extra_headers_json)
            # Extra headers do NOT override auth headers — auth takes precedence
            for key, value in extra.items():
                if key.lower() not in {k.lower() for k in auth_headers}:
                    auth_headers[key] = value
                else:
                    logger.debug(
                        "EXTRA_HEADERS_JSON key '%s' conflicts with auth header, skipping.", key
                    )
        except (json.JSONDecodeError, AttributeError):
            pass  # Already validated at startup; defensive fallback only

    return auth_headers
