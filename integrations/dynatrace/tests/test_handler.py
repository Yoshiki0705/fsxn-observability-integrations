import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("handler", None)
import handler

class TestFormatEntry:
    def test_basic(self):
        log = {"EventID": "4663", "SVMName": "svm-01", "UserName": "admin",
               "Operation": "ReadData", "Result": "Success", "timestamp": "2026-01-15T12:00:00Z"}
        entry = handler._format_entry(log, "audit/test.json")
        assert entry["log.source"] == "fsxn-ontap"
        assert entry["severity"] == "info"
        assert entry["fsxn.svm"] == "svm-01"

    def test_failure_severity(self):
        log = {"Result": "Failure"}
        entry = handler._format_entry(log, "test.json")
        assert entry["severity"] == "warn"

class TestSendBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_http.request.return_value = MagicMock(status=204)
        assert handler._send_batch([{"content": "test"}], "dt-token") is True
        headers = mock_http.request.call_args[1]["headers"]
        assert headers["Authorization"] == "Api-Token dt-token"
