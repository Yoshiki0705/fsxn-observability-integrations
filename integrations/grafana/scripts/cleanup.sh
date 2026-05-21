#!/bin/bash
# Clean up Grafana Cloud integration resources for FSx for ONTAP.
#
# This is a thin wrapper around the shared cleanup script.
# See shared/scripts/cleanup-vendor.sh for full documentation.
#
# Usage:
#   bash integrations/grafana/scripts/cleanup.sh
#   bash integrations/grafana/scripts/cleanup.sh --delete-secret --delete-layer
#   bash integrations/grafana/scripts/cleanup.sh --all
#   bash integrations/grafana/scripts/cleanup.sh --all --s3-bucket my-bucket --s3-prefix audit/svm-prod-01/

set -euo pipefail

# Grafana-specific configuration
export STACK_PREFIX="${STACK_PREFIX:-fsxn-grafana}"
export SECRET_NAME="${SECRET_NAME:-grafana/fsxn-loki-credentials}"
export VENDOR_NAME="Grafana Cloud"

# Resolve shared script path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
  echo "ERROR: Shared cleanup script not found: ${SHARED_SCRIPT}"
  echo "Run from the project root directory."
  exit 1
fi

exec bash "$SHARED_SCRIPT" "$@"
