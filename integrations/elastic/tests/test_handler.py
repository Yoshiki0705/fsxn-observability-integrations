import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("handler", None)
import handler

class TestFormatDocument:
    def test_ecs_fields(self):
        log = {"EventID": "4663", "UserName": "admin", "ClientIP": "10.0.1.1",
               "Operation": "ReadData", "ObjectName": "/vol/data/f.txt",
               "Result": "Success", "SVMName": "svm-01", "timestamp": "2026-01-15T12:00:00Z"}
        doc = handler._format_document(log, "audit/test.json")
        assert doc["@timestamp"] == "2026-01-15T12:00:00Z"
        assert doc["event"]["code"] == "4663"
        assert doc["event"]["type"] == ["access"]
        assert doc["event"]["category"] == ["file"]
        assert doc["user"]["name"] == "admin"
        assert doc["fsxn"]["operation"] == "ReadData"

class TestSendBulk:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_http.request.return_value = MagicMock(
            status=200, data=b'{"errors":false,"items":[]}')
        lines = ['{"index":{"_index":"test"}}', '{"msg":"hi"}']
        assert handler._send_bulk(lines, "api-key-123") is True
        headers = mock_http.request.call_args[1]["headers"]
        assert "ApiKey api-key-123" in headers["Authorization"]

    @patch("handler.http")
    def test_ndjson_format(self, mock_http):
        mock_http.request.return_value = MagicMock(
            status=200, data=b'{"errors":false}')
        lines = ['{"index":{}}', '{"a":1}', '{"index":{}}', '{"b":2}']
        handler._send_bulk(lines, "key")
        body = mock_http.request.call_args[1]["body"].decode()
        assert body.endswith("\n")
        assert body.count("\n") == 4
