"""Shared fixtures for ontap_response tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add shared/python to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_http():
    """Mock urllib3 PoolManager for ONTAP REST API calls."""
    with patch("ontap_response.urllib3.PoolManager") as mock_pm:
        mock_instance = MagicMock()
        mock_pm.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def ontap_client(mock_http):
    """Create OntapResponseClient with mocked HTTP."""
    from ontap_response import OntapResponseClient

    client = OntapResponseClient(
        mgmt_ip="10.0.1.100",
        username="fsxadmin",
        password="test-password",
    )
    # Replace the internal http with our mock
    client._http = mock_http
    return client


def make_response(status: int = 200, data: dict | None = None) -> MagicMock:
    """Create a mock urllib3 response."""
    resp = MagicMock()
    resp.status = status
    if data is None:
        data = {}
    resp.data = bytes(
        __import__("json").dumps(data), "utf-8"
    )
    return resp
