"""Integration tests for EMS Parser + Lambda handler pipeline.

Tests the full flow from API Gateway event through Lambda handler
to EMS Parser Layer, verifying correct HTTP responses for both
EMS Receiver and FPolicy Receiver Lambda functions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add the lambda directory to sys.path so we can import handlers
_lambda_dir = str(Path(__file__).parent.parent / "lambda")
if _lambda_dir not in sys.path:
    sys.path.insert(0, _lambda_dir)

from ems_receiver import lambda_handler as ems_handler  # noqa: E402
from fpolicy_receiver import lambda_handler as fpolicy_handler  # noqa: E402


class TestEmsReceiverWithValidArpPayload:
    """Test EMS Receiver Lambda handler with valid ARP payload → 200 response."""

    def test_valid_arp_payload_returns_200(self) -> None:
        """EMS Receiver returns 200 for a valid ARP volume state event."""
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "messageName": "arw.volume.state",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Anti-ransomware: Volume vol_data state changed to enabled",
            "parameters": {
                "volume_name": "vol_data",
                "state": "enabled",
            },
        }
        event: dict[str, Any] = {
            "body": json.dumps(payload),
            "httpMethod": "POST",
            "path": "/ems",
        }

        response = ems_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "ok"
        assert body["event_name"] == "arw.volume.state"


class TestEmsReceiverWithValidQuotaPayload:
    """Test EMS Receiver Lambda handler with valid quota payload → 200 response."""

    def test_valid_quota_payload_returns_200(self) -> None:
        """EMS Receiver returns 200 for a valid quota soft limit event."""
        payload = {
            "time": "2024-01-15T14:00:00+09:00",
            "messageName": "wafl.quota.softlimit.exceeded",
            "severity": "warning",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Quota soft limit exceeded on volume vol_data",
            "parameters": {
                "volume_name": "vol_data",
                "qtree": "qtree1",
                "quota_target": "user1",
                "used_bytes": 62914560,
                "limit_bytes": 52428800,
            },
        }
        event: dict[str, Any] = {
            "body": json.dumps(payload),
            "httpMethod": "POST",
            "path": "/ems",
        }

        response = ems_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "ok"
        assert body["event_name"] == "wafl.quota.softlimit.exceeded"


class TestEmsReceiverWithInvalidPayload:
    """Test EMS Receiver Lambda handler with invalid payload → 400 response."""

    def test_invalid_json_returns_400(self) -> None:
        """EMS Receiver returns 400 for invalid JSON body."""
        event: dict[str, Any] = {
            "body": "this is not valid json!!!",
            "httpMethod": "POST",
            "path": "/ems",
        }

        response = ems_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
        assert "message" in body
        assert len(body["message"]) > 0

    def test_empty_body_returns_400(self) -> None:
        """EMS Receiver returns 400 for empty body."""
        event: dict[str, Any] = {
            "body": "",
            "httpMethod": "POST",
            "path": "/ems",
        }

        response = ems_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"

    def test_missing_message_name_returns_400(self) -> None:
        """EMS Receiver returns 400 when messageName is missing."""
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Some message",
            "parameters": {"key": "value"},
        }
        event: dict[str, Any] = {
            "body": json.dumps(payload),
            "httpMethod": "POST",
            "path": "/ems",
        }

        response = ems_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
        assert "messageName" in body["message"]


class TestFpolicyReceiverWithValidPayload:
    """Test FPolicy Receiver Lambda handler with valid file operation payload → 200."""

    def test_valid_file_operation_returns_200(self) -> None:
        """FPolicy Receiver returns 200 for a valid file operation event."""
        payload = {
            "operation": "create",
            "file_path": "/vol/data/documents/report.docx",
            "user": "admin",
            "client_ip": "10.0.1.50",
            "protocol": "cifs",
            "timestamp": "2024-01-15T10:30:00+09:00",
        }
        event: dict[str, Any] = {
            "body": json.dumps(payload),
            "httpMethod": "POST",
            "path": "/fpolicy",
        }

        response = fpolicy_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "ok"
        assert "event_id" in body
        # event_id should be a valid UUID format
        assert len(body["event_id"]) == 36


class TestFpolicyReceiverWithInvalidJson:
    """Test FPolicy Receiver Lambda handler with invalid JSON → 400 response."""

    def test_invalid_json_returns_400(self) -> None:
        """FPolicy Receiver returns 400 for invalid JSON body."""
        event: dict[str, Any] = {
            "body": "not valid json {{{",
            "httpMethod": "POST",
            "path": "/fpolicy",
        }

        response = fpolicy_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["status"] == "error"
        assert "message" in body
        assert "event_id" in body
