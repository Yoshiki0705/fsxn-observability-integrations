import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("handler", None)
import handler

class TestSendBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        lines = ['{"msg":"test1"}', '{"msg":"test2"}']
        assert handler._send_batch(lines, "https://endpoint.sumologic.com/receiver/v1/http/TOKEN") is True
        headers = mock_http.request.call_args[1]["headers"]
        assert headers["X-Sumo-Category"] == "aws/fsxn/audit"

    @patch("handler.http")
    def test_ndjson_body(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        lines = ['{"a":1}', '{"b":2}']
        handler._send_batch(lines, "https://endpoint.sumologic.com/x")
        body = mock_http.request.call_args[1]["body"].decode()
        assert body == '{"a":1}\n{"b":2}'
