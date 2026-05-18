"""EMS Webhook receiver Lambda function.

Receives ONTAP EMS events via API Gateway and processes them
using the shared EMS Parser Layer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ems_parser import EmsParseError, parse_ems_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle EMS Webhook event from API Gateway.

    Extracts the request body from the API Gateway proxy event,
    parses it using the EMS Parser Layer, and returns an appropriate
    HTTP response.

    Args:
        event: API Gateway proxy event with body containing EMS payload.
        context: Lambda context object.

    Returns:
        API Gateway proxy response dict with statusCode and body.
        Returns 200 on successful parse, 400 on EmsParseError.
    """
    body = event.get("body", "")

    try:
        normalized = parse_ems_event(body)
        logger.info(
            "EMS event received: event_name=%s severity=%s source_node=%s svm=%s",
            normalized["event_name"],
            normalized["severity"],
            normalized["source_node"],
            normalized["svm"],
        )
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"status": "ok", "event_name": normalized["event_name"]}
            ),
        }
    except EmsParseError as e:
        logger.error("EMS parse failed: %s", str(e))
        return {
            "statusCode": 400,
            "body": json.dumps({"status": "error", "message": str(e)}),
        }
