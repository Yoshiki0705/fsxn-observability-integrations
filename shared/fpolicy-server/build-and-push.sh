#!/bin/bash
set -euo pipefail

# FPolicy Server — Build and Push to ECR
#
# IMPORTANT: Fargate runs on linux/amd64. If building on Apple Silicon (arm64),
# you MUST use --platform linux/amd64 or buildx to cross-compile.
# Without this, the Fargate task will fail with:
#   "CannotPullContainerError: image Manifest does not contain descriptor
#    matching platform 'linux/amd64'"
#
# Usage:
#   ./build-and-push.sh [tag]
#
# Examples:
#   ./build-and-push.sh                    # Uses 'latest' tag
#   ./build-and-push.sh v2-timeout-fix     # Uses specified tag

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${1:-latest}"

# Configuration — update these for your environment
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPO="fsxn-fpolicy-server"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "=== FPolicy Server Build & Push ==="
echo "  Region:  ${AWS_REGION}"
echo "  Account: ${AWS_ACCOUNT_ID}"
echo "  Image:   ${ECR_URI}:${TAG}"
echo "  Platform: linux/amd64"
echo ""

# Step 1: ECR Login
echo "🔐 Authenticating to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Step 2: Build for linux/amd64 (critical for Fargate)
echo "🔨 Building image for linux/amd64..."
docker buildx build \
  --platform linux/amd64 \
  -t "${ECR_URI}:${TAG}" \
  --push \
  "${SCRIPT_DIR}"

echo ""
echo "✅ Successfully built and pushed: ${ECR_URI}:${TAG}"
echo ""
echo "To force ECS to pull the new image:"
echo "  aws ecs update-service \\"
echo "    --cluster fsxn-fpolicy-server-cluster \\"
echo "    --service fsxn-fpolicy-server-service \\"
echo "    --force-new-deployment \\"
echo "    --region ${AWS_REGION}"
