#!/bin/bash
# Clean up Sumo Logic integration resources for FSx for ONTAP.
#
# This is a thin wrapper around the shared cleanup script.
# See shared/scripts/cleanup-vendor.sh for full documentation.
#
# Usage:
#   bash integrations/sumo-logic/scripts/cleanup.sh
#   bash integrations/sumo-logic/scripts/cleanup.sh --delete-secret --delete-layer
#   bash integrations/sumo-logic/scripts/cleanup.sh --all

set -euo pipefail

# Sumo Logic-specific configuration
export STACK_PREFIX="${STACK_PREFIX:-fsxn-sumologic}"
export SECRET_NAME="${SECRET_NAME:-sumologic/fsxn-http-source-url}"
export VENDOR_NAME="Sumo Logic"

# Resolve shared script path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_SCRIPT="${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh"

if [ ! -f "$SHARED_SCRIPT" ]; then
  echo "ERROR: Shared cleanup script not found: ${SHARED_SCRIPT}"
  echo "Run from the project root directory."
  exit 1
fi

exec bash "$SHARED_SCRIPT" "$@"
