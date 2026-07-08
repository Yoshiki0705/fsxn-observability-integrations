#!/bin/bash
# =============================================================================
# build-layer.sh — Package shared Python modules as a Lambda Layer
#
# Creates a zip file suitable for deployment as an AWS Lambda Layer.
# The layer provides ontap_response, auth_cache, object_ledger, sqs_buffer,
# and other shared modules to any Lambda function in this project.
#
# Usage:
#   bash shared/python/build-layer.sh
#   # Output: shared/python/dist/fsxn-shared-python-layer.zip
#
# Deploy:
#   aws lambda publish-layer-version \
#     --layer-name fsxn-shared-python \
#     --zip-file fileb://shared/python/dist/fsxn-shared-python-layer.zip \
#     --compatible-runtimes python3.12 \
#     --description "FSx for ONTAP shared modules (ontap_response, auth_cache, etc.)"
#
# Layer structure (Lambda expects modules under python/):
#   python/
#     ontap_response.py
#     auth_cache.py
#     object_ledger.py
#     sqs_buffer.py
#     observability.py
#     idempotency.py
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${DIST_DIR}/build"
LAYER_ZIP="${DIST_DIR}/fsxn-shared-python-layer.zip"

echo "=== Building Lambda Layer: fsxn-shared-python ==="

# Clean previous build
rm -rf "${BUILD_DIR}" "${LAYER_ZIP}"
mkdir -p "${BUILD_DIR}/python"

# Copy shared modules (Lambda Layer expects python/ prefix)
MODULES=(
  ontap_response.py
  auth_cache.py
  object_ledger.py
  sqs_buffer.py
  observability.py
  idempotency.py
  __init__.py
)

for mod in "${MODULES[@]}"; do
  if [[ -f "${SCRIPT_DIR}/${mod}" ]]; then
    cp "${SCRIPT_DIR}/${mod}" "${BUILD_DIR}/python/${mod}"
    echo "  Added: python/${mod}"
  fi
done

# Create zip
cd "${BUILD_DIR}"
zip -r "${LAYER_ZIP}" python/ -x "python/__pycache__/*"
cd "${SCRIPT_DIR}"

# Clean build dir
rm -rf "${BUILD_DIR}"

# Output info
ZIP_SIZE=$(ls -lh "${LAYER_ZIP}" | awk '{print $5}')
echo ""
echo "=== Layer built successfully ==="
echo "  Output: ${LAYER_ZIP}"
echo "  Size:   ${ZIP_SIZE}"
echo ""
echo "Deploy with:"
echo "  aws lambda publish-layer-version \\"
echo "    --layer-name fsxn-shared-python \\"
echo "    --zip-file fileb://${LAYER_ZIP} \\"
echo "    --compatible-runtimes python3.12 \\"
echo '    --description "FSx for ONTAP shared modules (ontap_response, auth_cache, etc.)"'
