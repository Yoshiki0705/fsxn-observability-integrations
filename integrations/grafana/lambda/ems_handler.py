"""FSx for ONTAP EMS event shipper for Grafana Cloud Loki.

Receives EMS (Event Management System) webhook events from API Gateway,
parses them using the shared EMS parser layer, and ships to Grafana Cloud
via Loki Push API or OTLP Gateway.

Authentication: Basic Auth = base64(instanceId:apiToken)
Labels: {job="fsxn-ems", source="ontap", severity="<severity>"}
"""

from __future__ import annotations

import json
import logging
import os
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any

import boto3
import urllib3

# ─── EMS Parser Layer Import ───────────────────────────────────────────────
try:
    from ems_parser import EmsParseError, parse_ems_event, format_ems_event
except ImportError:
    # Fallback for local development without Lambda Layer
    class EmsParseError(Exception):  # type: ignore[no-redef]
        pass

    def parse_ems_event(payload: str | dict) -> dict:  # type: ignore[misc]
        """Stub: parse raw event when layer is unavailable."""
        if payload is None:
            raise EmsParseError("payload is None")
        if isinstance(payload, str) and payload == "":
            raise EmsParseError("payload is empty")
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                raise EmsParseError(f"invalid JSON: {e}") from e
        else:
            data = payload
        if "messageName" not in data:
            raise EmsParseError("missing required field: messageName")
        return {
            "timestamp": data.get("time", ""),
            "event_name": data.get("messageName", ""),
            "severity": data.get("severity", ""),
            "source_node": data.get("node", ""),
            "svm": data.get("svmName", ""),
            "message": data.get("message", ""),
            "parameters": data.get("parameters", {}),
            "raw": data,
        }

    def format_ems_event(normalized: dict) -> str:  # type: ignore[misc]
        """Stub: serialize event when layer is unavailable."""
        return json.dumps(normalized, ensure_ascii=False, default=str)


# ─── Configuration ─────────────────────────────────────────────────────────

LOKI_ENDPOINT = os.environ.get("LOKI_ENDPOINT", "")
API_KEY_SECRET_ARN = os.environ.get("API_KEY_SECRET_ARN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Auto-detect endpoint mode from URL pattern
USE_OTLP = "otlp-gateway" in LOKI_ENDPOINT or LOKI_ENDPOINT.rstrip("/").endswith("/otlp")

# ─── Constants ──────────────────────────────────────────────────────────────

MAX_RETRIES = 3
MAX_BATCH_BYTES = 3 * 1024 * 1024  # 3MB (Loki recommended ~4MB)

# EMS severity to OTLP severity mapping
EMS_SEVERITY_MAP = {
    "emergency": (21, "FATAL"),
    "alert": (17, "ERROR"),
    "critical": (17, "ERROR"),
    "error": (17, "ERROR"),
    "warning": (13, "WARN"),
    "notice": (9, "INFO"),
    "informational": (9, "INFO"),
    "debug": (5, "DEBUG"),
}

# ─── Logger ────────────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# ─── AWS clients ───────────────────────────────────────────────────────────

secrets_client = boto3.client("secretsmanager")
http = urllib3.PoolManager(num_pools=4, maxsize=10)

# Cache for auth header (Lambda execution context reuse)
_auth_header_cache: str | None = None


def _get_auth_header() -> str:
    """Retrieve Grafana Cloud credentials and build Basic Auth header.

    Supports JSON format: {"instance_id":"<id>","api_key":"<key>"}
    Auth: Basic base64(instanceId:apiToken)

    Returns:
        Basic Auth header value.
    """
    global _auth_header_cache
    if _auth_header_cache is None:
        response = secrets_client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        secret = response["SecretString"]
        try:
            parsed = json.loads(secret)
            instance_id = parsed.get("instance_id", parsed.get("user", ""))
            api_key = parsed.get("api_key", parsed.get("password", ""))
            credentials = f"{instance_id}:{api_key}"
        except (json.JSONDecodeError, AttributeError):
            credentials = secret  # Assume pre-formatted "user:pass"
        _auth_header_cache = f"Basic {b64encode(credentials.encode()).decode()}"
    return _auth_header_cache


def _iso_to_ns(timestamp: str) -> str:
    """Convert ISO 8601 timestamp to nanosecond string for Loki.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Unix nanoseconds as string.
    """
    if not timestamp:
        return str(int(time.time() * 1e9))
    try:
        ts = timestamp.strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1e9))
    except (ValueError, AttributeError):
        return str(int(time.time() * 1e9))


# ─── Loki Push API format ──────────────────────────────────────────────────


def _format_for_loki(normalized: dict[str, Any]) -> dict[str, Any]:
    """Format a normalized EMS event for Loki Push API.

    Labels: {job="fsxn-ems", source="ontap", severity="<severity>"}
    Values: [[timestamp_ns, json_log_line]]

    Args:
        normalized: Normalized EMS event dict from parse_ems_event().

    Returns:
        Loki Push API payload dict.
    """
    severity = normalized.get("severity", "informational").lower()
    ts_ns = _iso_to_ns(normalized.get("timestamp", ""))
    log_line = format_ems_event(normalized)

    payload: dict[str, Any] = {
        "streams": [
            {
                "stream": {
                    "job": "fsxn-ems",
                    "source": "ontap",
                    "severity": severity,
                },
                "values": [[ts_ns, log_line]],
            }
        ]
    }
    return payload


# ─── OTLP format ───────────────────────────────────────────────────────────


def _format_for_otlp(normalized: dict[str, Any]) -> dict[str, Any]:
    """Format a normalized EMS event for OTLP Log Data Model.

    Args:
        normalized: Normalized EMS event dict from parse_ems_event().

    Returns:
        OTLP payload dict with resourceLogs structure.
    """
    severity = normalized.get("severity", "informational")
    severity_num, severity_text = EMS_SEVERITY_MAP.get(
        severity.lower(), (9, "INFO")
    )
    ts_ns = _iso_to_ns(normalized.get("timestamp", ""))

    # Build attributes from EMS event fields
    attributes: list[dict[str, Any]] = [
        {"key": "event_name", "value": {"stringValue": normalized.get("event_name", "")}},
        {"key": "severity", "value": {"stringValue": severity}},
    ]
    if normalized.get("source_node"):
        attributes.append(
            {"key": "source_node", "value": {"stringValue": normalized["source_node"]}}
        )
    if normalized.get("svm"):
        attributes.append(
            {"key": "svm", "value": {"stringValue": normalized["svm"]}}
        )

    # Add parameters as attributes
    for key, value in normalized.get("parameters", {}).items():
        if value is not None and str(value) != "":
            attributes.append({"key": key, "value": {"stringValue": str(value)}})

    log_record: dict[str, Any] = {
        "timeUnixNano": ts_ns,
        "severityNumber": severity_num,
        "severityText": severity_text,
        "body": {"stringValue": format_ems_event(normalized)},
        "attributes": attributes,
    }

    payload: dict[str, Any] = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "fsxn-ems"}},
                        {"key": "source", "value": {"stringValue": "ontap"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "fsxn-ems-grafana", "version": "1.0.0"},
                        "logRecords": [log_record],
                    }
                ],
            }
        ]
    }
    return payload


# ─── Delivery ──────────────────────────────────────────────────────────────


def _normalize_otlp_url(endpoint: str) -> str:
    """Normalize OTLP endpoint URL to ensure it ends with /v1/logs."""
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/v1/logs"):
        return endpoint
    if endpoint.endswith("/otlp"):
        return f"{endpoint}/v1/logs"
    return f"{endpoint}/v1/logs"


def _ship_to_grafana(payload: dict[str, Any], auth_header: str) -> bool:
    """Ship EMS event to Grafana Cloud (Loki Push API or OTLP Gateway).

    Args:
        payload: Formatted payload (Loki or OTLP format).
        auth_header: Basic Auth header value.

    Returns:
        True if successfully sent, False otherwise.
    """
    if USE_OTLP:
        url = _normalize_otlp_url(LOKI_ENDPOINT)
        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }
    else:
        url = f"{LOKI_ENDPOINT.rstrip('/')}/loki/api/v1/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST", url, body=body, headers=headers, timeout=30.0
            )

            if response.status in (200, 204):
                logger.info("Grafana push success: HTTP %d", response.status)
                return True

            if response.status == 429 or response.status >= 500:
                wait_time = 2 ** (attempt + 1)
                logger.warning(
                    "Grafana retry %d/%d: HTTP %d",
                    attempt + 1, MAX_RETRIES, response.status,
                )
                time.sleep(wait_time)
                continue

            logger.error(
                "Grafana error %d: %s",
                response.status,
                response.data.decode("utf-8", errors="replace")[:500],
            )
            return False

        except urllib3.exceptions.HTTPError as e:
            wait_time = 2 ** (attempt + 1)
            logger.warning(
                "HTTP error (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES, str(e),
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)

    return False


# ─── Lambda handler ────────────────────────────────────────────────────────


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle EMS Webhook event from API Gateway.

    Receives an API Gateway proxy event containing an EMS event in the body,
    parses it using the shared EMS parser layer, formats for Grafana Cloud
    (Loki Push API or OTLP), and ships with retry logic.

    Args:
        event: API Gateway proxy event with body containing EMS JSON payload.
        context: Lambda context object.

    Returns:
        API Gateway proxy response dict.
    """
    body = event.get("body", "")
    logger.info("EMS event received, body length: %d", len(body) if body else 0)

    # Get auth header
    try:
        auth_header = _get_auth_header()
    except Exception as e:
        logger.error("Failed to retrieve credentials: %s", str(e))
        return _api_response(500, {"error": "Failed to retrieve credentials"})

    # Parse EMS event using shared layer
    try:
        normalized = parse_ems_event(body)
        logger.info(
            "EMS event parsed: event_name=%s severity=%s svm=%s",
            normalized.get("event_name", ""),
            normalized.get("severity", ""),
            normalized.get("svm", ""),
        )
    except EmsParseError as e:
        logger.error("EMS parse failed: %s", str(e))
        return _api_response(400, {"error": f"Invalid EMS payload: {e}"})

    # Format payload based on endpoint mode
    if USE_OTLP:
        payload = _format_for_otlp(normalized)
    else:
        payload = _format_for_loki(normalized)

    # Ship to Grafana Cloud
    success = _ship_to_grafana(payload, auth_header)

    if success:
        return _api_response(200, {
            "status": "ok",
            "event_name": normalized.get("event_name", ""),
            "delivered": True,
        })
    else:
        return _api_response(502, {
            "status": "error",
            "message": "Delivery to Grafana Cloud failed after retries",
            "event_name": normalized.get("event_name", ""),
        })


def _api_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Create an API Gateway proxy response.

    Args:
        status_code: HTTP status code.
        body: Response body dictionary.

    Returns:
        API Gateway proxy response dict.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }
