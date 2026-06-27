"""Unit tests for Dashboard Importer Lambda handler.

Tests cover:
- Successful import of multiple dashboards (happy path)
- AMG API rate limit (429) retry with exponential backoff
- S3 read failure handling with CFn FAILED response
- AMG API error (500) handling
- Idempotent re-import (overwrite=true, no duplicate)
- Delete request type (no-op SUCCESS)
- Empty bucket (no dashboard files)
- Partial failure (some succeed, some fail)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Add lambda directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def dashboard_env_vars(monkeypatch):
    """Set required environment variables for dashboard importer tests."""
    monkeypatch.setenv(
        "AMG_API_KEY_SECRET_ARN",
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:amg-api-key-XXXXXX",
    )
    monkeypatch.setenv(
        "AMG_WORKSPACE_URL",
        "https://g-abcdef1234.grafana-workspace.ap-northeast-1.amazonaws.com",
    )
    monkeypatch.setenv("DASHBOARD_BUCKET_NAME", "test-dashboard-bucket")
    monkeypatch.setenv("DASHBOARD_S3_PREFIX", "dashboards/")
    monkeypatch.setenv("AMP_WORKSPACE_ID", "ws-test-amp-12345")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-1")


@pytest.fixture
def reload_dashboard_importer(dashboard_env_vars):
    """Reload the dashboard_importer module to pick up mocked env vars."""
    if "dashboard_importer" in sys.modules:
        del sys.modules["dashboard_importer"]
    import dashboard_importer

    return dashboard_importer


@pytest.fixture
def cfn_event():
    """Create a sample CloudFormation Custom Resource event."""
    return {
        "RequestType": "Create",
        "ResponseURL": "https://cfn-response.example.com",
        "StackId": "arn:aws:cloudformation:ap-northeast-1:123456789012:stack/test/guid",
        "RequestId": "unique-id",
        "LogicalResourceId": "DashboardImporter",
        "PhysicalResourceId": "physical-id",
    }


@pytest.fixture
def cfn_delete_event(cfn_event):
    """Create a Delete-type CloudFormation Custom Resource event."""
    cfn_event["RequestType"] = "Delete"
    return cfn_event


@pytest.fixture
def mock_lambda_context():
    """Create a mock Lambda context object for dashboard importer."""
    context = MagicMock()
    context.aws_request_id = "test-request-id-dashboard"
    context.function_name = "fsxn-mgmt-dashboard-importer"
    context.log_stream_name = "2026/01/15/[$LATEST]abcdef1234567890"
    context.memory_limit_in_mb = 256
    context.invoked_function_arn = (
        "arn:aws:lambda:ap-northeast-1:123456789012:function:fsxn-mgmt-dashboard-importer"
    )
    return context


@pytest.fixture
def sample_dashboard_json():
    """Create a sample Grafana dashboard JSON."""
    return {
        "uid": "fsxn-overview",
        "title": "FSx for ONTAP Overview",
        "panels": [
            {"id": 1, "title": "IOPS", "type": "graph"},
            {"id": 2, "title": "Throughput", "type": "graph"},
        ],
        "schemaVersion": 38,
    }


# ─── Test Classes ──────────────────────────────────────────────────────────


class TestSuccessfulImport:
    """Test happy path: 3 dashboards imported successfully."""

    def test_successful_import(
        self, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """Happy path: 3 dashboards imported, CFn SUCCESS response sent."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — list 3 dashboard files
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "dashboards/fsxn-overview.json"},
                    {"Key": "dashboards/fsxn-volumes.json"},
                    {"Key": "dashboards/fsxn-performance.json"},
                ]
            }
        ]

        # Mock S3 get_object for each dashboard
        dashboard_jsons = [
            {"uid": "fsxn-overview", "title": "FSx for ONTAP Overview", "panels": []},
            {"uid": "fsxn-volumes", "title": "FSx for ONTAP Volumes", "panels": []},
            {"uid": "fsxn-performance", "title": "FSx for ONTAP Performance", "panels": []},
        ]
        handler._s3_client.get_object.side_effect = [
            {"Body": MagicMock(read=MagicMock(return_value=json.dumps(d).encode()))}
            for d in dashboard_jsons
        ]

        # Mock AMG HTTP API
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = b'{"id": 1, "uid": "test", "url": "/d/test/dashboard"}'

        handler._http = MagicMock()
        handler._http.request.return_value = mock_response

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify CFn response was sent with SUCCESS
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert cfn_body["Data"]["ImportedCount"] == "3"
        assert cfn_body["Data"]["FailedCount"] == "0"
        assert cfn_body["Data"]["TotalCount"] == "3"


class TestRateLimitRetry:
    """Test AMG API 429 rate limit with retry and backoff."""

    @patch("time.sleep")
    def test_rate_limit_retry(
        self, mock_sleep, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """AMG returns 429, verify retry with backoff, then success."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — 1 dashboard file
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {"Contents": [{"Key": "dashboards/fsxn-overview.json"}]}
        ]
        handler._s3_client.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(
                    return_value=json.dumps(
                        {"uid": "fsxn-overview", "title": "FSx for ONTAP Overview", "panels": []}
                    ).encode()
                )
            )
        }

        # Mock AMG HTTP API — first call for datasource succeeds,
        # then 429 on first dashboard import attempt, then success
        rate_limit_response = MagicMock()
        rate_limit_response.status = 429
        rate_limit_response.data = b'{"message": "rate limit exceeded"}'

        success_response = MagicMock()
        success_response.status = 200
        success_response.data = b'{"id": 1, "uid": "fsxn-overview", "url": "/d/fsxn-overview/dashboard"}'

        # Datasource POST succeeds, then dashboard POST gets 429 then succeeds
        handler._http = MagicMock()
        handler._http.request.side_effect = [
            success_response,  # POST /api/datasources
            rate_limit_response,  # POST /api/dashboards/db — 429
            success_response,  # POST /api/dashboards/db — retry succeeds
            success_response,  # PUT CFn response
        ]

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify time.sleep was called for backoff
        mock_sleep.assert_called()
        # First retry should wait BACKOFF_BASE_SECONDS * (2^0) = 2 seconds
        assert mock_sleep.call_args_list[0] == call(2)

        # Verify CFn SUCCESS response
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert cfn_body["Data"]["ImportedCount"] == "1"


class TestS3ReadFailure:
    """Test S3 GetObject failure handling."""

    def test_s3_read_failure(
        self, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """S3 GetObject fails, verify CFn FAILED response with error message."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — list returns 1 file
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {"Contents": [{"Key": "dashboards/fsxn-overview.json"}]}
        ]

        # S3 get_object raises an exception
        from botocore.exceptions import ClientError

        handler._s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
            "GetObject",
        )

        # Mock AMG HTTP API — datasource creation succeeds
        success_response = MagicMock()
        success_response.status = 200
        success_response.data = b'{"id": 1, "name": "Amazon Managed Prometheus"}'

        handler._http = MagicMock()
        handler._http.request.return_value = success_response

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify CFn FAILED response (all imports failed)
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "FAILED"
        assert "fsxn-overview" in cfn_body["Reason"]
        assert cfn_body["Data"]["FailedCount"] == "1"
        assert cfn_body["Data"]["ImportedCount"] == "0"


class TestAmgApiError:
    """Test AMG API 500 error handling."""

    @patch("time.sleep")
    def test_amg_api_error(
        self, mock_sleep, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """AMG returns 500, verify error handling and CFn FAILED response."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — 1 dashboard file
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {"Contents": [{"Key": "dashboards/fsxn-overview.json"}]}
        ]
        handler._s3_client.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(
                    return_value=json.dumps(
                        {"uid": "fsxn-overview", "title": "FSx for ONTAP Overview", "panels": []}
                    ).encode()
                )
            )
        }

        # Mock AMG HTTP API — datasource succeeds, dashboard import returns 500
        datasource_response = MagicMock()
        datasource_response.status = 200
        datasource_response.data = b'{"id": 1, "name": "Amazon Managed Prometheus"}'

        error_response = MagicMock()
        error_response.status = 500
        error_response.data = b'{"message": "Internal Server Error"}'

        # CFn response mock
        cfn_response = MagicMock()
        cfn_response.status = 200
        cfn_response.data = b""

        handler._http = MagicMock()
        handler._http.request.side_effect = [
            datasource_response,  # POST /api/datasources — success
            error_response,  # POST /api/dashboards/db — 500
            cfn_response,  # PUT CFn response
        ]

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify CFn FAILED response
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "FAILED"
        assert "500" in cfn_body["Reason"] or "Internal Server Error" in cfn_body["Reason"]


class TestIdempotentReimport:
    """Test idempotent re-import (overwrite=true, no duplicate)."""

    def test_idempotent_reimport(
        self, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """Dashboard already exists (overwrite=true), verify no duplicate."""
        handler = reload_dashboard_importer

        # Set RequestType to Update (re-deploy scenario)
        cfn_event["RequestType"] = "Update"

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — 1 dashboard file
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {"Contents": [{"Key": "dashboards/fsxn-overview.json"}]}
        ]
        handler._s3_client.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(
                    return_value=json.dumps(
                        {"uid": "fsxn-overview", "id": 42, "title": "FSx for ONTAP Overview", "panels": []}
                    ).encode()
                )
            )
        }

        # Mock AMG HTTP API — all succeed (overwrite existing dashboard)
        success_response = MagicMock()
        success_response.status = 200
        success_response.data = b'{"id": 42, "uid": "fsxn-overview", "url": "/d/fsxn-overview/dashboard", "status": "success", "version": 2}'

        handler._http = MagicMock()
        handler._http.request.return_value = success_response

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify the dashboard import call used overwrite=true and removed 'id'
        import_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "POST" and "/api/dashboards/db" in str(c[0][1])
        ]
        assert len(import_calls) == 1

        # Parse the request body to verify overwrite=true and id removed
        request_body = json.loads(import_calls[0][1]["body"])
        assert request_body["overwrite"] is True
        assert "id" not in request_body["dashboard"]
        assert request_body["dashboard"]["uid"] == "fsxn-overview"

        # Verify CFn SUCCESS response
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert cfn_body["Data"]["ImportedCount"] == "1"


class TestDeleteRequest:
    """Test Delete RequestType handling."""

    def test_delete_request(
        self, reload_dashboard_importer, cfn_delete_event, mock_lambda_context
    ):
        """Delete RequestType, verify no-op SUCCESS response."""
        handler = reload_dashboard_importer

        # Mock HTTP for CFn response only
        cfn_response = MagicMock()
        cfn_response.status = 200
        cfn_response.data = b""

        handler._http = MagicMock()
        handler._http.request.return_value = cfn_response

        # Execute
        handler.lambda_handler(cfn_delete_event, mock_lambda_context)

        # Verify only one HTTP call was made (the CFn response)
        assert handler._http.request.call_count == 1

        # Verify it was a PUT to the CFn response URL
        put_call = handler._http.request.call_args_list[0]
        assert put_call[0][0] == "PUT"
        assert "cfn-response.example.com" in put_call[0][1]

        # Verify SUCCESS status
        cfn_body = json.loads(put_call[1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert "no-op" in cfn_body["Data"].get("Message", "").lower() or \
               "Delete" in cfn_body["Data"].get("Message", "")


class TestEmptyBucket:
    """Test empty bucket (no dashboard files in S3)."""

    def test_empty_bucket(
        self, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """No dashboard files in S3, verify SUCCESS with ImportedCount=0."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — empty bucket (no Contents key)
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [{}]  # No 'Contents' key

        # Mock AMG HTTP API — datasource creation succeeds
        success_response = MagicMock()
        success_response.status = 200
        success_response.data = b'{"id": 1, "name": "Amazon Managed Prometheus"}'

        handler._http = MagicMock()
        handler._http.request.return_value = success_response

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify CFn SUCCESS response with ImportedCount=0
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert cfn_body["Data"]["ImportedCount"] == "0"


class TestPartialFailure:
    """Test partial failure (some dashboards succeed, some fail)."""

    def test_partial_failure(
        self, reload_dashboard_importer, cfn_event, mock_lambda_context
    ):
        """Some dashboards succeed, some fail, verify SUCCESS with counts."""
        handler = reload_dashboard_importer

        # Mock Secrets Manager
        handler._secrets_client = MagicMock()
        handler._secrets_client.get_secret_value.return_value = {
            "SecretString": "test-api-key-12345"
        }

        # Mock S3 — 3 dashboard files
        handler._s3_client = MagicMock()
        paginator_mock = MagicMock()
        handler._s3_client.get_paginator.return_value = paginator_mock
        paginator_mock.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "dashboards/fsxn-overview.json"},
                    {"Key": "dashboards/fsxn-volumes.json"},
                    {"Key": "dashboards/fsxn-performance.json"},
                ]
            }
        ]

        # First and third dashboards read OK, second fails (invalid JSON)
        handler._s3_client.get_object.side_effect = [
            {
                "Body": MagicMock(
                    read=MagicMock(
                        return_value=json.dumps(
                            {"uid": "fsxn-overview", "title": "FSx for ONTAP Overview", "panels": []}
                        ).encode()
                    )
                )
            },
            {
                "Body": MagicMock(
                    read=MagicMock(
                        return_value=b"invalid json {{{{"
                    )
                )
            },
            {
                "Body": MagicMock(
                    read=MagicMock(
                        return_value=json.dumps(
                            {"uid": "fsxn-performance", "title": "FSx for ONTAP Performance", "panels": []}
                        ).encode()
                    )
                )
            },
        ]

        # Mock AMG HTTP API — datasource and dashboard imports succeed
        success_response = MagicMock()
        success_response.status = 200
        success_response.data = b'{"id": 1, "uid": "test", "url": "/d/test/dashboard"}'

        handler._http = MagicMock()
        handler._http.request.return_value = success_response

        # Execute
        handler.lambda_handler(cfn_event, mock_lambda_context)

        # Verify CFn SUCCESS response (partial failure is still SUCCESS)
        cfn_calls = [
            c for c in handler._http.request.call_args_list
            if c[0][0] == "PUT" and "cfn-response" in str(c[0][1])
        ]
        assert len(cfn_calls) == 1
        cfn_body = json.loads(cfn_calls[0][1]["body"])
        assert cfn_body["Status"] == "SUCCESS"
        assert cfn_body["Data"]["ImportedCount"] == "2"
        assert cfn_body["Data"]["FailedCount"] == "1"
        assert cfn_body["Data"]["TotalCount"] == "3"
