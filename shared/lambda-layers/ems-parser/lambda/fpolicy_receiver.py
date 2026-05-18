"""FPolicy External Engine receiver Lambda function.

Receives FPolicy file operation notifications via NLB + Private API Gateway.
This is a reference implementation for E2E testing of the FPolicy event
delivery path.
"""

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle FPolicy event from API Gateway.

    Extracts the request body from the API Gateway proxy event, parses
    the JSON payload, and logs the file operation details. Each request
    is assigned a unique event ID for traceability.

    Args:
        event: API Gateway proxy event with FPolicy notification body.
        context: Lambda context object.

    Returns:
        API Gateway proxy response dict with statusCode and JSON body.
        Returns 200 on success with {"status": "ok", "event_id": ...}.
        Returns 400 on parse error with {"status": "error", "message": ..., "event_id": ...}.
    """
    body = event.get("body", "")
    event_id = str(uuid.uuid4())

    try:
        payload: dict[str, Any] = json.loads(body) if isinstance(body, str) else body
        logger.info(
            "FPolicy event received: operation=%s path=%s user=%s client_ip=%s",
            payload.get("operation", "unknown"),
            payload.get("file_path", "unknown"),
            payload.get("user", "unknown"),
            payload.get("client_ip", "unknown"),
        )
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "event_id": event_id}),
        }
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("FPolicy payload parse failed: %s", str(e))
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"status": "error", "message": str(e), "event_id": event_id}
            ),
        }
