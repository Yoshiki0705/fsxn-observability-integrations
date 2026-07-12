"""Unit tests for network_block.py — NACL-based IP blocking."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add shared/python to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from network_block import NetworkBlockClient, NetworkBlockError


@pytest.fixture
def mock_ec2():
    """Create a mock EC2 client."""
    return MagicMock()


@pytest.fixture
def client(mock_ec2):
    """Create a NetworkBlockClient with mock EC2 client."""
    return NetworkBlockClient(ec2_client=mock_ec2)


class TestValidateIp:
    """Test IP validation."""

    def test_valid_ipv4(self, client):
        assert client._validate_ip("10.0.5.99") == "10.0.5.99/32"

    def test_valid_ipv4_with_cidr(self, client):
        assert client._validate_ip("10.0.5.99/32") == "10.0.5.99/32"

    def test_invalid_ip(self, client):
        with pytest.raises(NetworkBlockError, match="Invalid IP"):
            client._validate_ip("999.999.999.999")

    def test_empty_ip(self, client):
        with pytest.raises(NetworkBlockError, match="Invalid IP"):
            client._validate_ip("")

    def test_ipv6_rejected(self, client):
        with pytest.raises(NetworkBlockError, match="Invalid IP"):
            client._validate_ip("::1")


class TestFindNaclForSubnet:
    """Test NACL discovery."""

    def test_finds_nacl(self, client, mock_ec2):
        mock_ec2.describe_network_acls.return_value = {
            "NetworkAcls": [{"NetworkAclId": "acl-12345"}]
        }
        result = client.find_nacl_for_subnet("subnet-abc")
        assert result == "acl-12345"
        mock_ec2.describe_network_acls.assert_called_once_with(
            Filters=[{"Name": "association.subnet-id", "Values": ["subnet-abc"]}]
        )

    def test_no_nacl_found(self, client, mock_ec2):
        mock_ec2.describe_network_acls.return_value = {"NetworkAcls": []}
        with pytest.raises(NetworkBlockError, match="No NACL found"):
            client.find_nacl_for_subnet("subnet-nonexistent")


class TestBlockIp:
    """Test IP blocking."""

    def test_block_all_ports(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},  # find_nacl
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": []}]},  # find_rule
        ]
        mock_ec2.create_network_acl_entry.return_value = {}

        result = client.block_ip(
            subnet_id="subnet-abc",
            client_ip="10.0.5.99",
            reason="ransomware detected",
        )

        assert result["status"] == "blocked"
        assert result["cidr"] == "10.0.5.99/32"
        assert result["nacl_id"] == "acl-123"
        assert result["rule_number"] == 50  # First in range
        assert result["block_all_ports"] is True

        mock_ec2.create_network_acl_entry.assert_called_once_with(
            NetworkAclId="acl-123",
            RuleNumber=50,
            Protocol="-1",
            RuleAction="deny",
            Egress=False,
            CidrBlock="10.0.5.99/32",
        )

    def test_block_nfs_only(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": []}]},
        ]
        mock_ec2.create_network_acl_entry.return_value = {}

        result = client.block_ip(
            subnet_id="subnet-abc",
            client_ip="10.0.5.99",
            block_all_ports=False,
        )

        assert result["status"] == "blocked"
        assert result["block_all_ports"] is False
        mock_ec2.create_network_acl_entry.assert_called_once_with(
            NetworkAclId="acl-123",
            RuleNumber=50,
            Protocol="6",
            PortRange={"From": 2049, "To": 2049},
            RuleAction="deny",
            Egress=False,
            CidrBlock="10.0.5.99/32",
        )

    def test_skips_used_rule_numbers(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": [
                {"RuleNumber": 50, "Egress": False, "RuleAction": "deny"},
                {"RuleNumber": 51, "Egress": False, "RuleAction": "deny"},
            ]}]},
        ]
        mock_ec2.create_network_acl_entry.return_value = {}

        result = client.block_ip(subnet_id="subnet-abc", client_ip="10.0.5.99")
        assert result["rule_number"] == 52  # First available after 50, 51

    def test_range_exhausted(self, client, mock_ec2):
        # Fill the entire range (50-99)
        entries = [
            {"RuleNumber": n, "Egress": False, "RuleAction": "deny"}
            for n in range(50, 100)
        ]
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": entries}]},
        ]

        with pytest.raises(NetworkBlockError, match="No available rule numbers"):
            client.block_ip(subnet_id="subnet-abc", client_ip="10.0.5.99")


class TestUnblockIp:
    """Test IP unblocking."""

    def test_unblock_existing(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},  # find_nacl
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": [
                {"RuleNumber": 50, "Egress": False, "RuleAction": "deny",
                 "CidrBlock": "10.0.5.99/32"},
            ]}]},  # describe for removal
        ]
        mock_ec2.delete_network_acl_entry.return_value = {}

        result = client.unblock_ip(subnet_id="subnet-abc", client_ip="10.0.5.99")

        assert result["status"] == "unblocked"
        assert result["rules_removed"] == 1
        mock_ec2.delete_network_acl_entry.assert_called_once_with(
            NetworkAclId="acl-123",
            RuleNumber=50,
            Egress=False,
        )

    def test_unblock_not_found(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": []}]},
        ]

        result = client.unblock_ip(subnet_id="subnet-abc", client_ip="10.0.5.99")
        assert result["status"] == "not_found"

    def test_unblock_ignores_rules_outside_range(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": [
                # Rule 10 is outside our range (50-99)
                {"RuleNumber": 10, "Egress": False, "RuleAction": "deny",
                 "CidrBlock": "10.0.5.99/32"},
            ]}]},
        ]

        result = client.unblock_ip(subnet_id="subnet-abc", client_ip="10.0.5.99")
        assert result["status"] == "not_found"
        mock_ec2.delete_network_acl_entry.assert_not_called()


class TestListActiveBlocks:
    """Test listing active blocks."""

    def test_list_with_blocks(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": [
                {"RuleNumber": 50, "Egress": False, "RuleAction": "deny",
                 "CidrBlock": "10.0.5.99/32", "Protocol": "-1", "PortRange": None},
                {"RuleNumber": 51, "Egress": False, "RuleAction": "deny",
                 "CidrBlock": "10.0.6.100/32", "Protocol": "6",
                 "PortRange": {"From": 2049, "To": 2049}},
                # This one is outside our range — should not appear
                {"RuleNumber": 100, "Egress": False, "RuleAction": "allow",
                 "CidrBlock": "0.0.0.0/0", "Protocol": "-1"},
            ]}]},
        ]

        result = client.list_active_blocks(subnet_id="subnet-abc")
        assert result["count"] == 2
        assert result["active_blocks"][0]["cidr"] == "10.0.5.99/32"
        assert result["active_blocks"][1]["cidr"] == "10.0.6.100/32"

    def test_list_empty(self, client, mock_ec2):
        mock_ec2.describe_network_acls.side_effect = [
            {"NetworkAcls": [{"NetworkAclId": "acl-123"}]},
            {"NetworkAcls": [{"NetworkAclId": "acl-123", "Entries": []}]},
        ]

        result = client.list_active_blocks(subnet_id="subnet-abc")
        assert result["count"] == 0
        assert result["active_blocks"] == []
