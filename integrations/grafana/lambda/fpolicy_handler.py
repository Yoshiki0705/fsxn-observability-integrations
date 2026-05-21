"""FSx for ONTAP FPolicy event shipper for Grafana Cloud Loki.

Receives FPolicy file operation events from EventBridge custom bus
(source: fpolicy.fsxn) and ships to Grafana Cloud via OTLP Gateway
or Loki Push API.

Architecture:
  ONTAP -> TCP:9898 -> ECS Fargate -> SQS -> Bridge Lambda ->
  EventBridge (fpolicy.fsxn) -> This Lambda -> Grafana Cloud OTLP Gateway

Authentication: Basic Auth = base64(instanceId:apiToken)
Labels: {job="fsxn-fpolicy", source="ontap", operation="<op>"}
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

# --- Configuration ----------------------------------------------------------

LOKI_ENDPOINT = os.environ.get("LOKI_ENDPOINT", "")
API_KEY_SECRET_ARN = os.environ.get("API_KEY_SECRET_ARN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Auto-detect endpoint mode from URL pattern
USE_OTLP = "otlp-gateway" in LOKI_ENDPOINT or LOKI_ENDPOINT.rstrip("/").endswith("/otlp")

# --- Constants --------------------------------------------------------------

MAX_RETRIES = 3

# --- Logger -----------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# --- AWS clients ------------------------------------------------------------

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


def _format_for_otlp(event: dict[str, Any]) -> dict[str, Any]:
    """Format FPolicy event for OTLP Log Data Model.

    Resource attributes: service.name=fsxn-fpolicy, source=ontap
    Log attributes: operation, file_path, user, client_ip

    Args:
        event: FPolicy event dictionary from EventBridge detail.

    Returns:
        OTLP payload dict with resourceLogs structure.
    """
    operation = event.get("operation_type", event.get("operation", "unknown"))
    file_path = event.get("file_path", "")
    user = event.get("user", "")
    client_ip = event.get("client_ip", "")
    vserver = event.get("vserver", event.get("svm_name", ""))
    protocol = event.get("protocol", "")
    timestamp = event.get("timestamp", "")

    ts_ns = _iso_to_ns(timestamp)

    # Build log attributes
    attributes: list[dict[str, Any]] = [
        {"key": "operation", "value": {"stringValue": operation}},
        {"key": "file_path", "value": {"stringValue": file_path}},
        {"key": "user", "value": {"stringValue": user}},
        {"key": "client_ip", "value": {"stringValue": client_ip}},
    ]
    if vserver:
        attributes.append({"key": "svm", "value": {"stringValue": vserver}})
    if protocol:
        attributes.append({"key": "protocol", "value": {"stringValue": protocol}})

    # Build log body as JSON string
    body_str = json.dumps(event, default=str, ensure_ascii=False)

    log_record: dict[str, Any] = {
        "timeUnixNano": ts_ns,
        "severityNumber": 9,
        "severityText": "INFO",
        "body": {"stringValue": body_str},
        "attributes": attributes,
    }

    payload: dict[str, Any] = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "fsxn-fpolicy"}},
                        {"key": "source", "value": {"stringValue": "ontap"}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "fsxn-fpolicy-grafana", "version": "1.0.0"},
                        "logRecords": [log_record],
                    }
                ],
            }
        ]
    }
    return payload


def _format_for_loki(event: dict[str, Any]) -> dict[str, Any]:
    """Format FPolicy event for Loki Push API.

    Labels: {job="fsxn-fpolicy", source="ontap", operation="<op>"}
    Values: [[timestamp_ns, json_log_line]]

    Args:
        event: FPolicy event dictionary from EventBridge detail.

    Returns:
        Loki Push API payload dict.
    """
    operation = event.get("operation_type", event.get("operation", "unknown"))
    timestamp = event.get("timestamp", "")
    ts_ns = _iso_to_ns(timestamp)
    log_line = json.dumps(event, default=str, ensure_ascii=False)

    payload: dict[str, Any] = {
        "streams": [
            {
                "stream": {
                    "job": "fsxn-fpolicy",
                    "source": "ontap",
                    "operation": operation,
                },
                "values": [[ts_ns, log_line]],
            }
        ]
    }
    return payload


def _normalize_otlp_url(endpoint: str) -> str:
    """Normalize OTLP endpoint URL to ensure it ends with /v1/logs."""
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/v1/logs"):
        return endpoint
    if endpoint.endswith("/otlp"):
        return f"{endpoint}/v1/logs"
    return f"{endpoint}/v1/logs"


def _ship_to_grafana(payload: dict[str, Any], auth_header: str) -> bool:
    """Ship FPolicy event to Grafana Cloud (OTLP Gateway or Loki Push API).

    Args:
        payload: Formatted payload (OTLP or Loki format).
        auth_header: Basic Auth header value.

    Returns:
        True if successfully sent, False otherwise.
    """
    if USE_OTLP:
        url = _normalize_otlp_url(LOKI_ENDPOINT)
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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle FPolicy event from EventBridge.

    Receives an EventBridge event with source 'fpolicy.fsxn' containing
    FPolicy file operation data, formats for Grafana Cloud (OTLP or Loki
    Push API), and ships with retry logic.

    Args:
        event: EventBridge event with source 'fpolicy.fsxn'. The ``detail``
            field contains the FPolicy file operation data.
        context: Lambda context object.

    Returns:
        Dict with statusCode and processing summary.
    """
    logger.info("FPolicy handler invoked: source=%s", event.get("source", "unknown"))

    # Get auth header
    try:
        auth_header = _get_auth_header()
    except Exception as e:
        logger.error("Failed to retrieve credentials: %s", str(e))
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve credentials"},
        }

    # Extract FPolicy event detail from EventBridge event
    detail = event.get("detail")
    if detail is None:
        logger.error("Event detail is missing")
        return {
            "statusCode": 400,
            "body": {"error": "Event detail is missing"},
        }

    if not isinstance(detail, dict):
        logger.error("Unexpected detail type: %s", type(detail).__name__)
        return {
            "statusCode": 400,
            "body": {"error": f"Unexpected detail type: {type(detail).__name__}"},
        }

    logger.info(
        "FPolicy event: operation=%s file_path=%s user=%s",
        detail.get("operation_type", detail.get("operation", "")),
        detail.get("file_path", ""),
        detail.get("user", ""),
    )

    # Format payload based on endpoint mode
    if USE_OTLP:
        payload = _format_for_otlp(detail)
    else:
        payload = _format_for_loki(detail)

    # Ship to Grafana Cloud
    success = _ship_to_grafana(payload, auth_header)

    if success:
        return {
            "statusCode": 200,
            "body": {
                "status": "ok",
                "operation": detail.get("operation_type", detail.get("operation", "")),
                "delivered": True,
            },
        }
    else:
        return {
            "statusCode": 502,
            "body": {
                "status": "error",
                "message": "Delivery to Grafana Cloud failed after retries",
            },
        }
