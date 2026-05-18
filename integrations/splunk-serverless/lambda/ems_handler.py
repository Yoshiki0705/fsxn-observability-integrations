"""EMS Webhook handler for ONTAP EMS events forwarding to Splunk HEC.

Receives ONTAP EMS events via API Gateway HTTP API, validates the API key
and payload, formats the event for Splunk HEC, and forwards it. Designed
for ransomware detection (ARP) and other EMS alerting scenarios.

Key patterns:
- API key validation against Secrets Manager stored value
- Required field validation (message-name, message-severity, message-timestamp)
- Exponential backoff retry for HEC delivery (max 3 retries, base 2s)
- HTTP 502 on HEC failure after retries (DLQ handled by Lambda infrastructure)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3
from botocore.exceptions import ClientError

from models import EmsEventPayload, SplunkHecEvent

# Configuration from environment variables
HEC_ENDPOINT = os.environ.get("SPLUNK_HEC_ENDPOINT", "")
EMS_API_KEY_SECRET_ARN = os.environ.get("EMS_API_KEY_SECRET_ARN", "")
HEC_TOKEN_SECRET_ARN = os.environ.get("HEC_TOKEN_SECRET_ARN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# EMS-specific Splunk configuration
EMS_SOURCETYPE = "fsxn:ontap:ems"
EMS_INDEX = "fsxn_ems"
EMS_SOURCE = "fsxn-ems"

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 2

# Required EMS payload fields
REQUIRED_EMS_FIELDS = ("message-name", "message-severity", "message-timestamp")

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# AWS clients (initialized once per execution context)
secrets_client = boto3.client("secretsmanager")
http = urllib3.PoolManager(num_pools=2, maxsize=4)

# Cached secrets (per execution context, not per invocation)
_api_key_cache: str | None = None
_hec_token_cache: str | None = None


def _get_api_key() -> str:
    """Retrieve EMS API key from Secrets Manager (cached per execution context).

    Returns:
        The API key string stored in Secrets Manager.

    Raises:
        ClientError: If secret retrieval fails.
    """
    global _api_key_cache
    if _api_key_cache is not None:
        return _api_key_cache

    response = secrets_client.get_secret_value(SecretId=EMS_API_KEY_SECRET_ARN)
    _api_key_cache = response["SecretString"]
    return _api_key_cache


def _get_hec_token() -> str:
    """Retrieve Splunk HEC token from Secrets Manager (cached per execution context).

    Returns:
        The HEC token string stored in Secrets Manager.

    Raises:
        ClientError: If secret retrieval fails.
    """
    global _hec_token_cache
    if _hec_token_cache is not None:
        return _hec_token_cache

    response = secrets_client.get_secret_value(SecretId=HEC_TOKEN_SECRET_ARN)
    _hec_token_cache = response["SecretString"]
    return _hec_token_cache


def _validate_api_key(headers: dict[str, str]) -> bool:
    """Validate x-api-key header against stored secret.

    Checks that the incoming request contains an x-api-key header whose
    value matches the API key stored in AWS Secrets Manager.

    Args:
        headers: Request headers from API Gateway HTTP API event.
            Header names are lowercased by API Gateway HTTP API (v2.0).

    Returns:
        True if the API key is valid, False otherwise.
    """
    # API Gateway HTTP API (v2.0) lowercases all header names
    api_key = headers.get("x-api-key", "")
    if not api_key:
        logger.warning("Missing x-api-key header in request")
        return False

    try:
        expected_key = _get_api_key()
    except ClientError as e:
        logger.error(
            "Failed to retrieve API key from Secrets Manager (%s): %s",
            EMS_API_KEY_SECRET_ARN,
            e.response["Error"]["Code"],
        )
        return False

    if api_key != expected_key:
        logger.warning("Invalid x-api-key provided")
        return False

    return True


def _validate_ems_payload(payload: dict[str, Any]) -> list[str]:
    """Validate required EMS fields in the payload.

    Checks that the payload contains all required fields:
    message-name, message-severity, and message-timestamp.

    Args:
        payload: Parsed JSON body from the webhook request.

    Returns:
        List of missing required field names. Empty list if all present.
    """
    missing: list[str] = []
    for field in REQUIRED_EMS_FIELDS:
        if field not in payload or payload[field] is None or payload[field] == "":
            missing.append(field)
    return missing


def _format_ems_for_splunk(payload: dict[str, Any]) -> dict[str, Any]:
    """Format EMS event as Splunk HEC JSON.

    Creates a Splunk HEC event with sourcetype fsxn:ontap:ems, index fsxn_ems,
    and includes all original EMS fields in the event object.

    Args:
        payload: Validated EMS event payload containing message-name,
            message-severity, message-timestamp, and optionally parameters.

    Returns:
        Dictionary suitable for Splunk HEC /services/collector/event endpoint.
    """
    ems_event = EmsEventPayload.from_webhook_payload(payload)

    # Build event data including all original EMS fields
    event_data: dict[str, Any] = {
        "message-name": ems_event.message_name,
        "message-severity": ems_event.message_severity,
        "message-timestamp": ems_event.message_timestamp,
        "parameters": ems_event.parameters,
    }

    # Determine host from parameters if available
    host = ems_event.parameters.get(
        "vserver-name",
        ems_event.parameters.get("node-name", "fsxn-ontap"),
    )

    hec_event = SplunkHecEvent(
        time=None,  # Use Splunk indexing time
        host=host,
        source=EMS_SOURCE,
        sourcetype=EMS_SOURCETYPE,
        index=EMS_INDEX,
        event=event_data,
    )

    return hec_event.to_hec_json()


def _send_to_hec(hec_payload: dict[str, Any], hec_token: str) -> bool:
    """Send formatted event to Splunk HEC with exponential backoff retry.

    Retries on HTTP 429 (rate limited) and 5xx (server errors) with
    exponential backoff: base delay 2 seconds, doubling per attempt,
    up to 3 total attempts.

    Args:
        hec_payload: Formatted HEC event dictionary.
        hec_token: Splunk HEC authentication token.

    Returns:
        True if the event was successfully delivered, False otherwise.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Splunk {hec_token}",
    }
    body = json.dumps(hec_payload).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST",
                f"{HEC_ENDPOINT}/services/collector/event",
                body=body,
                headers=headers,
                timeout=30.0,
            )

            if response.status == 200:
                logger.info("Successfully forwarded EMS event to Splunk HEC")
                return True

            # Retry on 429 or 5xx
            if response.status == 429 or response.status >= 500:
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(
                        "Splunk HEC returned %d, attempt %d/%d, "
                        "retrying in %ds",
                        response.status,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                logger.error(
                    "Splunk HEC returned %d, all %d attempts exhausted",
                    response.status,
                    MAX_RETRIES,
                )
                return False

            # 4xx (except 429): do not retry
            logger.error(
                "Splunk HEC client error %d: %s",
                response.status,
                response.data.decode("utf-8", errors="replace")[:300],
            )
            return False

        except urllib3.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    "HTTP error on attempt %d/%d: %s, retrying in %ds",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "HTTP error on final attempt %d/%d: %s",
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )
                return False

    return False


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle EMS webhook events from API Gateway HTTP API.

    Processes incoming ONTAP EMS events: validates the API key, validates
    the payload structure, formats the event for Splunk HEC, and forwards
    it. Returns appropriate HTTP status codes for each failure mode.

    Args:
        event: API Gateway HTTP API (v2.0) event containing headers and body.
        context: Lambda execution context.

    Returns:
        API Gateway response dict with statusCode and JSON body.
    """
    logger.info("Processing EMS webhook event")

    # Extract headers (API Gateway HTTP API v2.0 lowercases header names)
    headers = event.get("headers", {})

    # Step 1: Validate API key
    if not _validate_api_key(headers):
        return _response(401, {"error": "Unauthorized: invalid or missing API key"})

    # Step 2: Parse request body
    body = event.get("body", "")
    if not body:
        return _response(400, {"error": "Request body is empty"})

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Malformed JSON body: %s", str(e))
        return _response(400, {"error": f"Malformed JSON body: {str(e)}"})

    # Step 3: Validate required EMS fields
    missing_fields = _validate_ems_payload(payload)
    if missing_fields:
        error_msg = (
            f"Missing required fields: {', '.join(sorted(missing_fields))}"
        )
        logger.warning(error_msg)
        return _response(400, {"error": error_msg, "missing_fields": sorted(missing_fields)})

    # Step 4: Format for Splunk HEC
    hec_payload = _format_ems_for_splunk(payload)

    # Step 5: Retrieve HEC token and forward to Splunk
    try:
        hec_token = _get_hec_token()
    except ClientError as e:
        logger.error(
            "Failed to retrieve HEC token from Secrets Manager (%s): %s",
            HEC_TOKEN_SECRET_ARN,
            e.response["Error"]["Code"],
        )
        return _response(502, {"error": "Internal error retrieving HEC credentials"})

    # Step 6: Send to HEC with retry
    success = _send_to_hec(hec_payload, hec_token)
    if not success:
        return _response(502, {"error": "Failed to forward event to Splunk HEC"})

    return _response(200, {
        "status": "success",
        "message": "EMS event forwarded to Splunk HEC",
        "message_name": payload.get("message-name", ""),
    })


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build API Gateway HTTP API response.

    Args:
        status_code: HTTP status code.
        body: Response body dictionary to be JSON-serialized.

    Returns:
        API Gateway response dict with statusCode, headers, and body.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
