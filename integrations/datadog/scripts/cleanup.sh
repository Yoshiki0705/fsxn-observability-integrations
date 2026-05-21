#!/bin/bash
# Clean up Datadog integration resources for FSx for ONTAP.
#
# This is a thin wrapper around the shared cleanup script.
# See shared/scripts/cleanup-vendor.sh for full documentation.
#
# Usage:
#   bash integrations/datadog/scripts/cleanup.sh
#   bash integrations/datadog/scripts/cleanup.sh --delete-secret --delete-layer
#   bash integrations/datadog/scripts/cleanup.sh --all
#   bash integrations/datadog/scripts/cleanup.sh --all --s3-bucket my-bucket --s3-prefix audit/svm-prod-01/

set -euo pipefail

# Datadog-specific configuration
export STACK_PREFIX="${STACK_PREFIX:-fsxn-datadog}"
export SECRET_NAME="${SECRET_NAME:-datadog/fsxn-api-key}"
export VENDOR_NAME="Datadog"

# Resolve shared script path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
  echo "ERROR: Shared cleanup script not found: ${SHARED_SCRIPT}"
  echo "Run from the project root directory."
  exit 1
fi

exec bash "$SHARED_SCRIPT" "$@"
