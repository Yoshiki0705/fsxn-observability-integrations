#!/bin/bash
# Clean up Elastic integration resources for FSx for ONTAP.
#
# This is a thin wrapper around the shared cleanup script.
# See shared/scripts/cleanup-vendor.sh for full documentation.
#
# Usage:
#   bash integrations/elastic/scripts/cleanup.sh
#   bash integrations/elastic/scripts/cleanup.sh --delete-secret --delete-layer
#   bash integrations/elastic/scripts/cleanup.sh --all

set -euo pipefail

# Elastic-specific configuration
export STACK_PREFIX="${STACK_PREFIX:-fsxn-elastic}"
export SECRET_NAME="${SECRET_NAME:-elastic/fsxn-api-key}"
export VENDOR_NAME="Elastic"

# Resolve shared script path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
  echo "ERROR: Shared cleanup script not found: ${SHARED_SCRIPT}"
  echo "Run from the project root directory."
  exit 1
fi

exec bash "$SHARED_SCRIPT" "$@"
