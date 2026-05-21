#!/bin/bash
# Clean up OTel Collector integration resources for FSx for ONTAP.
#
# This is a thin wrapper around the shared cleanup script.
# See shared/scripts/cleanup-vendor.sh for full documentation.
#
# Usage:
#   bash integrations/otel-collector/scripts/cleanup.sh
#   bash integrations/otel-collector/scripts/cleanup.sh --delete-secret --delete-layer
#   bash integrations/otel-collector/scripts/cleanup.sh --all

set -euo pipefail

# OTel Collector-specific configuration
export STACK_PREFIX="${STACK_PREFIX:-fsxn-otel}"
export SECRET_NAME="${SECRET_NAME:-otel/fsxn-collector-credentials}"
export VENDOR_NAME="OTel Collector"

# Resolve shared script path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
  echo "ERROR: Shared cleanup script not found: ${SHARED_SCRIPT}"
  echo "Run from the project root directory."
  exit 1
fi

exec bash "$SHARED_SCRIPT" "$@"
