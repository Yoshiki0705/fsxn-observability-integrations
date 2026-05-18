"""HEC token validator for the Splunk E2E verification pipeline.

Retrieves a Splunk HEC token from AWS Secrets Manager and validates
that it conforms to the expected UUID format (8-4-4-4-12 hex characters).
Can be used as a library or run as a CLI tool.

Usage:
    python splunk_token_validator.py --secret-arn <arn>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError

# HEC token format: UUID pattern (8-4-4-4-12 hexadecimal characters)
_HEC_TOKEN_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class ValidationResult:
    """Result of HEC token validation.

    Attributes:
        status: Validation outcome, either "pass" or "fail".
        secret_arn: The ARN of the Secrets Manager secret that was checked.
        token_format_valid: Whether the token matches the UUID pattern.
        error: Human-readable error message if validation failed, None otherwise.
    """

    status: str  # "pass" | "fail"
    secret_arn: str
    token_format_valid: bool
    error: str | None = None


def validate_hec_token(secret_arn: str) -> ValidationResult:
    """Retrieve and validate HEC token format from Secrets Manager.

    Fetches the secret value from AWS Secrets Manager and checks that it
    matches the Splunk HEC token UUID pattern (8-4-4-4-12 hex characters).
    Supports both plain string secrets and JSON-formatted secrets with
    ``hec_token`` or ``SPLUNK_HEC_TOKEN`` keys.

    Args:
        secret_arn: ARN of the Secrets Manager secret containing the HEC token.

    Returns:
        ValidationResult with status and token metadata.
    """
    # Retrieve secret from Secrets Manager
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        return ValidationResult(
            status="fail",
            secret_arn=secret_arn,
            token_format_valid=False,
            error=f"Secrets Manager error: {error_code}",
        )

    secret_string = response.get("SecretString", "")

    # Support both plain string and JSON format secrets
    token = _extract_token(secret_string)

    # Validate token is not empty
    if not token or not token.strip():
        return ValidationResult(
            status="fail",
            secret_arn=secret_arn,
            token_format_valid=False,
            error="HEC token is empty",
        )

    # Validate UUID pattern
    if not _HEC_TOKEN_PATTERN.match(token.strip()):
        return ValidationResult(
            status="fail",
            secret_arn=secret_arn,
            token_format_valid=False,
            error=(
                "HEC token does not match UUID format "
                "(expected: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
            ),
        )

    return ValidationResult(
        status="pass",
        secret_arn=secret_arn,
        token_format_valid=True,
        error=None,
    )


def _extract_token(secret_string: str) -> str:
    """Extract the HEC token from a secret string.

    Handles both plain string tokens and JSON-formatted secrets
    containing ``hec_token`` or ``SPLUNK_HEC_TOKEN`` keys.

    Args:
        secret_string: Raw secret value from Secrets Manager.

    Returns:
        Extracted token string.
    """
    try:
        parsed: dict[str, Any] = json.loads(secret_string)
        return str(
            parsed.get("hec_token", parsed.get("SPLUNK_HEC_TOKEN", secret_string))
        )
    except (json.JSONDecodeError, AttributeError):
        return secret_string


def main() -> None:
    """CLI entry point for HEC token validation."""
    parser = argparse.ArgumentParser(
        description="Validate Splunk HEC token stored in AWS Secrets Manager."
    )
    parser.add_argument(
        "--secret-arn",
        required=True,
        help="ARN of the Secrets Manager secret containing the HEC token.",
    )
    args = parser.parse_args()

    result = validate_hec_token(args.secret_arn)
    print(json.dumps(asdict(result), indent=2))

    sys.exit(0 if result.status == "pass" else 1)


if __name__ == "__main__":
    main()
