"""Pytest configuration and shared fixtures for EMS Parser tests."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add the layer's python directory to sys.path so tests can import ems_parser
_layer_python_dir = str(Path(__file__).parent.parent / "python")
if _layer_python_dir not in sys.path:
    sys.path.insert(0, _layer_python_dir)


@pytest.fixture
def sample_arw_volume_state_payload() -> dict[str, Any]:
    """Sample ARP volume state change event payload."""
    return {
        "time": "2024-01-15T10:30:00+09:00",
        "messageName": "arw.volume.state",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "message": "Anti-ransomware: Volume vol1 state changed to enabled",
        "parameters": {
            "volume_name": "vol1",
            "state": "enabled",
        },
    }


@pytest.fixture
def sample_arw_vserver_state_payload() -> dict[str, Any]:
    """Sample ARP vserver state change event payload."""
    return {
        "time": "2024-01-15T11:00:00+09:00",
        "messageName": "arw.vserver.state",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "message": "Anti-ransomware: Vserver svm-prod-01 state changed to enabled",
        "parameters": {
            "vserver_name": "svm-prod-01",
            "state": "enabled",
        },
    }


@pytest.fixture
def sample_quota_softlimit_payload() -> dict[str, Any]:
    """Sample quota soft limit exceeded event payload."""
    return {
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


@pytest.fixture
def sample_quota_hardlimit_payload() -> dict[str, Any]:
    """Sample quota hard limit exceeded event payload."""
    return {
        "time": "2024-01-15T14:30:00+09:00",
        "messageName": "wafl.quota.hardlimit.exceeded",
        "severity": "error",
        "node": "fsxn-node-02",
        "svmName": "svm-prod-01",
        "message": "Quota hard limit exceeded on volume vol_data",
        "parameters": {
            "volume_name": "vol_data",
            "qtree": "qtree2",
            "quota_target": "user2",
            "used_bytes": 104857600,
            "limit_bytes": 104857600,
        },
    }


@pytest.fixture
def sample_sms_vol_full_payload() -> dict[str, Any]:
    """Sample volume full event payload."""
    return {
        "time": "2024-01-15T16:00:00+09:00",
        "messageName": "sms.vol.full",
        "severity": "error",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "message": "Volume vol_backup is full (98% used)",
        "parameters": {
            "volume_name": "vol_backup",
            "used_percent": 98,
        },
    }


@pytest.fixture
def sample_cf_fsm_takeover_payload() -> dict[str, Any]:
    """Sample HA takeover started event payload."""
    return {
        "time": "2024-01-15T18:00:00+09:00",
        "messageName": "cf.fsm.takeoverStarted",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "message": "Takeover of partner node fsxn-node-02 started: hardware failure",
        "parameters": {
            "partner_node": "fsxn-node-02",
            "reason": "hardware failure",
        },
    }


@pytest.fixture
def sample_net_linkdown_payload() -> dict[str, Any]:
    """Sample network link down event payload."""
    return {
        "time": "2024-01-15T20:00:00+09:00",
        "messageName": "net.linkDown",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "message": "Network link e0a is down: cable unplugged",
        "parameters": {
            "node": "fsxn-node-01",
            "port": "e0a",
            "reason": "cable unplugged",
        },
    }


@pytest.fixture
def all_sample_payloads(
    sample_arw_volume_state_payload: dict[str, Any],
    sample_arw_vserver_state_payload: dict[str, Any],
    sample_quota_softlimit_payload: dict[str, Any],
    sample_quota_hardlimit_payload: dict[str, Any],
    sample_sms_vol_full_payload: dict[str, Any],
    sample_cf_fsm_takeover_payload: dict[str, Any],
    sample_net_linkdown_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """All sample payloads keyed by event name."""
    return {
        "arw.volume.state": sample_arw_volume_state_payload,
        "arw.vserver.state": sample_arw_vserver_state_payload,
        "wafl.quota.softlimit.exceeded": sample_quota_softlimit_payload,
        "wafl.quota.hardlimit.exceeded": sample_quota_hardlimit_payload,
        "sms.vol.full": sample_sms_vol_full_payload,
        "cf.fsm.takeoverStarted": sample_cf_fsm_takeover_payload,
        "net.linkDown": sample_net_linkdown_payload,
    }


@pytest.fixture
def test_data_dir() -> Path:
    """Path to the test_data directory."""
    return Path(__file__).parent / "test_data"


def load_test_data(filename: str) -> dict[str, Any]:
    """Load a JSON test data file.

    Args:
        filename: Name of the JSON file in the test_data directory.

    Returns:
        Parsed JSON as a dictionary.
    """
    test_data_path = Path(__file__).parent / "test_data" / filename
    with open(test_data_path) as f:
        return json.load(f)
