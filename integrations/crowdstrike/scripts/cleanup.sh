#!/bin/bash
# Clean up CrowdStrike Falcon LogScale integration resources.
set -euo pipefail

export STACK_PREFIX="${STACK_PREFIX:-fsxn-crowdstrike}"
export SECRET_NAME="${SECRET_NAME:-crowdstrike/fsxn-logscale-token}"
export VENDOR_NAME="CrowdStrike Falcon LogScale"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/../../../shared/scripts/cleanup-vendor.sh" "$@"
