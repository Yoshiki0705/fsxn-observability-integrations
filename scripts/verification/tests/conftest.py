"""Shared pytest fixtures for verification tests.

Provides sample data fixtures for testing the verification package
components including bilingual comparison, results rendering, and
screenshot validation.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def sample_markdown_ja() -> str:
    """Sample Japanese Markdown document for bilingual comparison tests."""
    return """\
# セットアップガイド

## 前提条件

- AWS アカウント
- Datadog アカウント

## デプロイ手順

### ステップ 1: パラメータ設定

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| `StackName` | スタック名 | `fsxn-datadog-integration` |
| `DatadogApiKeyArn` | API キーの ARN | - |

### ステップ 2: デプロイ実行

```bash
aws cloudformation deploy \\
  --template-file template.yaml \\
  --stack-name fsxn-datadog-integration \\
  --capabilities CAPABILITY_IAM
```

## 動作確認

テストイベントを送信して動作を確認します。

```json
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "test-bucket"},
        "object": {"key": "audit/test.json"}
      }
    }
  ]
}
```
"""


@pytest.fixture
def sample_markdown_en() -> str:
    """Sample English Markdown document for bilingual comparison tests."""
    return """\
# Setup Guide

## Prerequisites

- AWS Account
- Datadog Account

## Deployment Steps

### Step 1: Parameter Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `StackName` | Stack name | `fsxn-datadog-integration` |
| `DatadogApiKeyArn` | API key ARN | - |

### Step 2: Execute Deployment

```bash
aws cloudformation deploy \\
  --template-file template.yaml \\
  --stack-name fsxn-datadog-integration \\
  --capabilities CAPABILITY_IAM
```

## Verification

Send a test event to verify the integration works.

```json
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "test-bucket"},
        "object": {"key": "audit/test.json"}
      }
    }
  ]
}
```
"""


@pytest.fixture
def sample_verification_environment() -> dict[str, Any]:
    """Sample verification environment data."""
    return {
        "aws_region": "ap-northeast-1",
        "stack_name": "fsxn-datadog-integration",
        "lambda_function_name": "fsxn-datadog-integration-shipper",
        "datadog_site": "datadoghq.com",
    }


@pytest.fixture
def sample_verification_step() -> dict[str, Any]:
    """Sample verification step data."""
    return {
        "step_number": 1,
        "step_name": "Deploy CloudFormation Stack",
        "result": "success",
        "command": "aws cloudformation deploy --template-file template.yaml --stack-name fsxn-datadog-integration",
        "output": "Stack fsxn-datadog-integration created successfully.",
        "screenshot_path": None,
        "error_detail": None,
        "timestamp": "2026-01-15T14:30:00+09:00",
    }


@pytest.fixture
def sample_verification_step_with_screenshot() -> dict[str, Any]:
    """Sample verification step with screenshot reference."""
    return {
        "step_number": 3,
        "step_name": "Verify Datadog Log Arrival",
        "result": "success",
        "command": None,
        "output": "Found 5 logs matching source:fsxn within 5 minutes.",
        "screenshot_path": "docs/screenshots/datadog-logs-arrival.png",
        "error_detail": None,
        "timestamp": "2026-01-15T14:35:00+09:00",
    }


@pytest.fixture
def required_screenshot_filenames() -> list[str]:
    """List of required screenshot filenames for validation."""
    return [
        "datadog-logs-arrival.png",
        "datadog-pipeline-config.png",
        "datadog-facets-config.png",
        "datadog-dashboard.png",
        "datadog-unauthorized-access.png",
    ]


@pytest.fixture
def png_magic_bytes() -> bytes:
    """PNG file magic bytes for format validation."""
    return b"\x89PNG\r\n\x1a\n"
