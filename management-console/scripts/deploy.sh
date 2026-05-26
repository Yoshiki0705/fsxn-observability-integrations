#!/bin/bash
set -euo pipefail

# FSxN Management Console - Deployment Script
# Orchestrates 5 CloudFormation stacks in dependency order:
#   1. network → 2. auth → 3. observability → 4. console → 5. monitoring
#
# All parameters are passed via environment variables.
# Stack outputs from earlier stacks are automatically passed to later stacks.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/../templates"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STACK_PREFIX="${STACK_PREFIX:-fsxn-mgmt}"
AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo "ap-northeast-1")}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_DASHBOARD_IMPORT="${SKIP_DASHBOARD_IMPORT:-false}"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy the FSxN Management Console (5 CloudFormation stacks).

Required environment variables:
  VPC_ID                        Target VPC ID (e.g., vpc-0123456789abcdef0)
  PRIVATE_SUBNET_IDS            Comma-separated private subnet IDs (min 2 AZs)
  PUBLIC_SUBNET_IDS             Comma-separated public subnet IDs (min 2 AZs)
  ONTAP_MGMT_ENDPOINTS          Comma-separated FSx ONTAP management endpoints (1-10)
  ONTAP_CREDENTIALS_SECRET_ARNS Comma-separated Secrets Manager ARNs (positional match to endpoints)

Backward-compatible aliases (auto-converted to plural form):
  ONTAP_MGMT_ENDPOINT           Single FSx ONTAP management endpoint (legacy)
  ONTAP_CREDENTIALS_SECRET_ARN  Single Secrets Manager ARN (legacy)

Optional environment variables:
  COGNITO_DOMAIN_PREFIX       Cognito hosted UI domain prefix (default: fsxn-mgmt)
  MFA_CONFIGURATION           OFF | OPTIONAL | REQUIRED (default: OPTIONAL)
  SESSION_DURATION_HOURS      1-12 (default: 8)
  HARVEST_IMAGE_TAG           Harvest container image tag (default: latest)
  TOOLJET_IMAGE_TAG           ToolJet container image tag (default: latest)
  S3_ACCESS_POINT_ARN         FSx ONTAP S3 Access Point ARN
  CERTIFICATE_ARN             ACM certificate ARN for ALB HTTPS
  CUSTOM_DOMAIN_NAME          Custom domain for the console (e.g., console.example.com)
  HOSTED_ZONE_ID              Route 53 Hosted Zone ID for the custom domain
  ALERT_SNS_TOPIC_ARN         Existing SNS topic ARN for alarms (optional)
  FSXN_SECURITY_GROUP_ID      FSx ONTAP file system security group ID (for auto-adding access rules)
  AWS_REGION                  AWS region (default: from aws configure or ap-northeast-1)
  STACK_PREFIX                Stack name prefix (default: fsxn-mgmt)

Options:
  --help, -h                Show this help message
  --dry-run                 Validate templates without deploying
  --skip-dashboard-import   Skip Grafana dashboard import in Stack 3

Examples:
  # Single file system deployment (backward compatible)
  export VPC_ID=vpc-0123456789abcdef0
  export PRIVATE_SUBNET_IDS=subnet-aaaa1111,subnet-bbbb2222
  export PUBLIC_SUBNET_IDS=subnet-cccc3333,subnet-dddd4444
  export ONTAP_MGMT_ENDPOINTS=10.0.x.x
  export ONTAP_CREDENTIALS_SECRET_ARNS=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX
  export CERTIFICATE_ARN=arn:aws:acm:ap-northeast-1:123456789012:certificate/abc-123
  ./deploy.sh

  # Multi file system deployment (up to 10)
  export ONTAP_MGMT_ENDPOINTS=10.0.1.x,10.0.2.x,10.0.3.x
  export ONTAP_CREDENTIALS_SECRET_ARNS=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs1-XXXXXX,arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs2-XXXXXX,arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-fs3-XXXXXX
  ./deploy.sh

  # Legacy single-endpoint variables (auto-converted to plural form)
  export ONTAP_MGMT_ENDPOINT=10.0.x.x
  export ONTAP_CREDENTIALS_SECRET_ARN=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX
  ./deploy.sh

  # Production deployment with MFA required
  export MFA_CONFIGURATION=REQUIRED
  export HARVEST_IMAGE_TAG=24.05.2
  export TOOLJET_IMAGE_TAG=v2.50.0-lts
  ./deploy.sh
EOF
  exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case $1 in
    --help|-h)
      usage
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-dashboard-import)
      SKIP_DASHBOARD_IMPORT=true
      shift
      ;;
    *)
      echo "Error: Unknown option: $1"
      echo "Run '$(basename "$0") --help' for usage."
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate required environment variables
# ---------------------------------------------------------------------------

validate_env() {
  # -------------------------------------------------------------------------
  # Backward compatibility: auto-convert singular vars to plural form
  # -------------------------------------------------------------------------
  if [[ -z "${ONTAP_MGMT_ENDPOINTS:-}" && -n "${ONTAP_MGMT_ENDPOINT:-}" ]]; then
    ONTAP_MGMT_ENDPOINTS="${ONTAP_MGMT_ENDPOINT}"
  fi
  if [[ -z "${ONTAP_CREDENTIALS_SECRET_ARNS:-}" && -n "${ONTAP_CREDENTIALS_SECRET_ARN:-}" ]]; then
    ONTAP_CREDENTIALS_SECRET_ARNS="${ONTAP_CREDENTIALS_SECRET_ARN}"
  fi

  # -------------------------------------------------------------------------
  # Check required variables are set
  # -------------------------------------------------------------------------
  local missing=()

  [[ -z "${VPC_ID:-}" ]] && missing+=("VPC_ID")
  [[ -z "${PRIVATE_SUBNET_IDS:-}" ]] && missing+=("PRIVATE_SUBNET_IDS")
  [[ -z "${PUBLIC_SUBNET_IDS:-}" ]] && missing+=("PUBLIC_SUBNET_IDS")
  [[ -z "${ONTAP_MGMT_ENDPOINTS:-}" ]] && missing+=("ONTAP_MGMT_ENDPOINTS (or ONTAP_MGMT_ENDPOINT)")
  [[ -z "${ONTAP_CREDENTIALS_SECRET_ARNS:-}" ]] && missing+=("ONTAP_CREDENTIALS_SECRET_ARNS (or ONTAP_CREDENTIALS_SECRET_ARN)")

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Error: Missing required environment variables:"
    for var in "${missing[@]}"; do
      echo "  - ${var}"
    done
    echo ""
    echo "Run '$(basename "$0") --help' for usage."
    exit 1
  fi

  # -------------------------------------------------------------------------
  # Multi-endpoint validation: count match and range check
  # -------------------------------------------------------------------------
  IFS=',' read -ra EP_ARRAY <<< "${ONTAP_MGMT_ENDPOINTS}"
  IFS=',' read -ra ARN_ARRAY <<< "${ONTAP_CREDENTIALS_SECRET_ARNS}"

  if [[ ${#EP_ARRAY[@]} -ne ${#ARN_ARRAY[@]} ]]; then
    log_error "Endpoint count (${#EP_ARRAY[@]}) does not match secret ARN count (${#ARN_ARRAY[@]})"
    log_error "Each management endpoint must have a corresponding Secrets Manager ARN (positional match)."
    exit 1
  fi

  if [[ ${#EP_ARRAY[@]} -lt 1 || ${#EP_ARRAY[@]} -gt 10 ]]; then
    log_error "Endpoint count must be between 1 and 10 (got ${#EP_ARRAY[@]})"
    exit 1
  fi

  log_info "Validated ${#EP_ARRAY[@]} FSx ONTAP endpoint(s) with matching credentials"

  # -------------------------------------------------------------------------
  # Custom domain validation: if CUSTOM_DOMAIN_NAME is set, require related vars
  # -------------------------------------------------------------------------
  if [[ -n "${CUSTOM_DOMAIN_NAME:-}" ]]; then
    if [[ -z "${CERTIFICATE_ARN:-}" ]]; then
      log_error "CUSTOM_DOMAIN_NAME is set but CERTIFICATE_ARN is not provided"
      log_error "An ACM certificate is required for custom domain HTTPS."
      exit 1
    fi
    if [[ -z "${HOSTED_ZONE_ID:-}" ]]; then
      log_error "CUSTOM_DOMAIN_NAME is set but HOSTED_ZONE_ID is not provided"
      log_error "A Route 53 Hosted Zone ID is required to create the DNS record."
      exit 1
    fi
    log_info "Custom domain configured: ${CUSTOM_DOMAIN_NAME}"
  fi
}

# ---------------------------------------------------------------------------
# Defaults for optional parameters
# ---------------------------------------------------------------------------

COGNITO_DOMAIN_PREFIX="${COGNITO_DOMAIN_PREFIX:-fsxn-mgmt}"
MFA_CONFIGURATION="${MFA_CONFIGURATION:-OPTIONAL}"
SESSION_DURATION_HOURS="${SESSION_DURATION_HOURS:-8}"
HARVEST_IMAGE_TAG="${HARVEST_IMAGE_TAG:-latest}"
TOOLJET_IMAGE_TAG="${TOOLJET_IMAGE_TAG:-latest}"
S3_ACCESS_POINT_ARN="${S3_ACCESS_POINT_ARN:-}"
CERTIFICATE_ARN="${CERTIFICATE_ARN:-}"
CUSTOM_DOMAIN_NAME="${CUSTOM_DOMAIN_NAME:-}"
HOSTED_ZONE_ID="${HOSTED_ZONE_ID:-}"
ALERT_SNS_TOPIC_ARN="${ALERT_SNS_TOPIC_ARN:-}"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

log_info() {
  echo "ℹ️  $1"
}

log_success() {
  echo "✅ $1"
}

log_error() {
  echo "❌ $1" >&2
}

log_step() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📦 $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Get a CloudFormation stack output value by key
get_stack_output() {
  local stack_name="$1"
  local output_key="$2"

  aws cloudformation describe-stacks \
    --stack-name "${stack_name}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue" \
    --output text
}

# Deploy a single CloudFormation stack
deploy_stack() {
  local stack_name="$1"
  local template_file="$2"
  shift 2
  local params=("$@")

  log_info "Deploying stack: ${stack_name}"
  log_info "Template: ${template_file}"
  log_info "Region: ${AWS_REGION}"

  if [[ ! -f "${template_file}" ]]; then
    log_error "Template not found: ${template_file}"
    return 1
  fi

  # Dry-run mode: validate template only, do not deploy
  if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY-RUN] Would deploy: ${stack_name}"
    log_info "[DRY-RUN] Template: ${template_file}"
    log_info "[DRY-RUN] Parameters: ${params[*]:-none}"
    aws cloudformation validate-template \
      --template-body "file://${template_file}" \
      --region "${AWS_REGION}" > /dev/null
    log_success "[DRY-RUN] Template validated: ${stack_name}"
    return 0
  fi

  # Build parameter overrides
  local param_overrides=""
  if [[ ${#params[@]} -gt 0 ]]; then
    param_overrides="--parameter-overrides ${params[*]}"
  fi

  # Deploy with aws cloudformation deploy
  # shellcheck disable=SC2086
  if ! aws cloudformation deploy \
    --template-file "${template_file}" \
    --stack-name "${stack_name}" \
    --region "${AWS_REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    ${param_overrides}; then

    log_error "Stack deployment failed: ${stack_name}"
    log_error "Check stack events for details:"
    log_error "  aws cloudformation describe-stack-events --stack-name ${stack_name} --region ${AWS_REGION}"
    return 1
  fi

  log_success "Stack deployed successfully: ${stack_name}"
}

# ---------------------------------------------------------------------------
# Main deployment sequence
# ---------------------------------------------------------------------------

main() {
  validate_env

  echo ""
  echo "🚀 FSxN Management Console Deployment"
  echo "   Region: ${AWS_REGION}"
  echo "   Stack prefix: ${STACK_PREFIX}"
  echo "   VPC: ${VPC_ID}"
  echo "   ONTAP endpoints: ${ONTAP_MGMT_ENDPOINTS}"
  echo ""

  # =========================================================================
  # Stack 1: Network
  # =========================================================================
  log_step "Stack 1/5: ${STACK_PREFIX}-network"

  deploy_stack "${STACK_PREFIX}-network" "${TEMPLATE_DIR}/network.yaml" \
    "VpcId=${VPC_ID}" \
    "PrivateSubnetIds=${PRIVATE_SUBNET_IDS}" \
    "PublicSubnetIds=${PUBLIC_SUBNET_IDS}" \
    "OntapManagementEndpoints=${ONTAP_MGMT_ENDPOINTS}"

  # Retrieve network stack outputs for downstream stacks
  HARVEST_TASK_SG=$(get_stack_output "${STACK_PREFIX}-network" "HarvestTaskSgId")
  TOOLJET_TASK_SG=$(get_stack_output "${STACK_PREFIX}-network" "ToolJetTaskSgId")
  ALB_SG=$(get_stack_output "${STACK_PREFIX}-network" "AlbSgId")
  LAMBDA_SG=$(get_stack_output "${STACK_PREFIX}-network" "LambdaSgId")
  NAT_GW_ID=$(get_stack_output "${STACK_PREFIX}-network" "NatGatewayId")

  log_info "Network outputs retrieved:"
  log_info "  HarvestTaskSG: ${HARVEST_TASK_SG}"
  log_info "  ToolJetTaskSG: ${TOOLJET_TASK_SG}"
  log_info "  AlbSG: ${ALB_SG}"
  log_info "  LambdaSG: ${LAMBDA_SG}"

  # Add Harvest task SG to FSx ONTAP security group (if specified)
  if [[ -n "${FSXN_SECURITY_GROUP_ID:-}" ]]; then
    log_info "Adding Harvest task SG to FSx ONTAP security group..."
    aws ec2 authorize-security-group-ingress \
      --group-id "${FSXN_SECURITY_GROUP_ID}" \
      --protocol tcp --port 443 \
      --source-group "${HARVEST_TASK_SG}" \
      --region "${AWS_REGION}" 2>/dev/null || log_info "Rule already exists (idempotent)"
    log_success "FSx ONTAP SG rule added: ${FSXN_SECURITY_GROUP_ID} ← ${HARVEST_TASK_SG}:443"
  fi

  # =========================================================================
  # Stack 2: Auth
  # =========================================================================
  log_step "Stack 2/5: ${STACK_PREFIX}-auth"

  deploy_stack "${STACK_PREFIX}-auth" "${TEMPLATE_DIR}/auth.yaml" \
    "CognitoDomainPrefix=${COGNITO_DOMAIN_PREFIX}" \
    "MfaConfiguration=${MFA_CONFIGURATION}" \
    "SessionDurationHours=${SESSION_DURATION_HOURS}"

  # Retrieve auth stack outputs
  COGNITO_USER_POOL_ID=$(get_stack_output "${STACK_PREFIX}-auth" "UserPoolId")
  COGNITO_APP_CLIENT_ID=$(get_stack_output "${STACK_PREFIX}-auth" "AppClientId")
  COGNITO_DOMAIN=$(get_stack_output "${STACK_PREFIX}-auth" "UserPoolDomainName")
  COGNITO_USER_POOL_ARN=$(get_stack_output "${STACK_PREFIX}-auth" "UserPoolArn")

  log_info "Auth outputs retrieved:"
  log_info "  UserPoolId: ${COGNITO_USER_POOL_ID}"
  log_info "  AppClientId: ${COGNITO_APP_CLIENT_ID}"
  log_info "  CognitoDomain: ${COGNITO_DOMAIN}"

  # =========================================================================
  # Pre-Stack 3: Upload dashboards to S3 and ensure AMG API key secret
  # =========================================================================
  log_step "Pre-Stack 3: Dashboard upload & AMG API key secret"

  # Resolve AWS Account ID dynamically
  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  DASHBOARD_BUCKET_NAME="fsxn-mgmt-dashboards-${AWS_ACCOUNT_ID}-${AWS_REGION}"
  DASHBOARD_SOURCE_DIR="${SCRIPT_DIR}/../harvest/dashboards"

  # Upload dashboard JSONs to S3 (bucket created by observability stack on first deploy)
  if [[ -d "${DASHBOARD_SOURCE_DIR}" ]]; then
    local json_count
    json_count=$(find "${DASHBOARD_SOURCE_DIR}" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "${json_count}" -gt 0 ]]; then
      log_info "Uploading ${json_count} dashboard JSON(s) to s3://${DASHBOARD_BUCKET_NAME}/dashboards/"
      if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Would sync ${DASHBOARD_SOURCE_DIR}/*.json to s3://${DASHBOARD_BUCKET_NAME}/dashboards/"
      else
        aws s3 sync "${DASHBOARD_SOURCE_DIR}" "s3://${DASHBOARD_BUCKET_NAME}/dashboards/" \
          --exclude "*" --include "*.json" \
          --region "${AWS_REGION}" 2>/dev/null || \
          log_info "Dashboard bucket may not exist yet (will be created by Stack 3). Upload will retry after stack deploy."
        log_success "Dashboard JSONs uploaded to S3"
      fi
    else
      log_info "No dashboard JSON files found in ${DASHBOARD_SOURCE_DIR} — skipping upload"
    fi
  else
    log_info "Dashboard source directory not found: ${DASHBOARD_SOURCE_DIR} — skipping upload"
  fi

  # Ensure AMG API key secret exists in Secrets Manager
  AMG_API_KEY_SECRET_NAME="fsxn-mgmt-amg-api-key"
  AMG_API_KEY_SECRET_ARN=""

  if aws secretsmanager describe-secret \
    --secret-id "${AMG_API_KEY_SECRET_NAME}" \
    --region "${AWS_REGION}" > /dev/null 2>&1; then
    AMG_API_KEY_SECRET_ARN=$(aws secretsmanager describe-secret \
      --secret-id "${AMG_API_KEY_SECRET_NAME}" \
      --region "${AWS_REGION}" \
      --query "ARN" --output text)
    log_info "AMG API key secret already exists: ${AMG_API_KEY_SECRET_NAME}"
  else
    if [[ "${DRY_RUN}" == "true" ]]; then
      log_info "[DRY-RUN] Would create Secrets Manager secret: ${AMG_API_KEY_SECRET_NAME}"
      AMG_API_KEY_SECRET_ARN="arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:${AMG_API_KEY_SECRET_NAME}-XXXXXX"
    else
      AMG_API_KEY_SECRET_ARN=$(aws secretsmanager create-secret \
        --name "${AMG_API_KEY_SECRET_NAME}" \
        --description "AMG API key for FSxN Management Console dashboard import" \
        --secret-string "PLACEHOLDER_UPDATE_WITH_REAL_AMG_API_KEY" \
        --region "${AWS_REGION}" \
        --query "ARN" --output text)
      log_success "Created AMG API key secret: ${AMG_API_KEY_SECRET_NAME}"
      log_info "⚠️  ACTION REQUIRED: Update the secret with a real AMG API key:"
      log_info "  aws secretsmanager put-secret-value --secret-id ${AMG_API_KEY_SECRET_NAME} --secret-string '<your-amg-api-key>' --region ${AWS_REGION}"
    fi
  fi

  log_info "AMG API key secret ARN: ${AMG_API_KEY_SECRET_ARN}"
  log_info "Skip dashboard import: ${SKIP_DASHBOARD_IMPORT}"

  # =========================================================================
  # Stack 3: Observability
  # =========================================================================
  log_step "Stack 3/5: ${STACK_PREFIX}-observability"

  local observability_params=(
    "PrivateSubnetIds=${PRIVATE_SUBNET_IDS}"
    "HarvestTaskSgId=${HARVEST_TASK_SG}"
    "OntapManagementEndpoints=${ONTAP_MGMT_ENDPOINTS}"
    "OntapCredentialsSecretArns=${ONTAP_CREDENTIALS_SECRET_ARNS}"
    "CognitoUserPoolArn=${COGNITO_USER_POOL_ARN}"
    "HarvestImageTag=${HARVEST_IMAGE_TAG}"
    "SkipDashboardImport=${SKIP_DASHBOARD_IMPORT}"
    "AmgApiKeySecretArn=${AMG_API_KEY_SECRET_ARN}"
  )

  deploy_stack "${STACK_PREFIX}-observability" "${TEMPLATE_DIR}/observability.yaml" "${observability_params[@]}"

  # Retrieve observability stack outputs
  AMP_WORKSPACE_ID=$(get_stack_output "${STACK_PREFIX}-observability" "AmpWorkspaceId")
  AMG_WORKSPACE_URL=$(get_stack_output "${STACK_PREFIX}-observability" "AmgWorkspaceUrl")
  ECS_CLUSTER_ARN=$(get_stack_output "${STACK_PREFIX}-observability" "EcsClusterArn")
  ECS_CLUSTER_NAME=$(get_stack_output "${STACK_PREFIX}-observability" "EcsClusterName")
  HARVEST_SERVICE_ARN=$(get_stack_output "${STACK_PREFIX}-observability" "HarvestServiceArn")
  HARVEST_SERVICE_NAME=$(get_stack_output "${STACK_PREFIX}-observability" "HarvestServiceName")

  log_info "Observability outputs retrieved:"
  log_info "  AMP Workspace: ${AMP_WORKSPACE_ID}"
  log_info "  AMG URL: ${AMG_WORKSPACE_URL}"
  log_info "  ECS Cluster: ${ECS_CLUSTER_ARN}"

  # =========================================================================
  # Stack 4: Console
  # =========================================================================
  log_step "Stack 4/5: ${STACK_PREFIX}-console"

  local console_params=(
    "VpcId=${VPC_ID}"
    "PrivateSubnetIds=${PRIVATE_SUBNET_IDS}"
    "PublicSubnetIds=${PUBLIC_SUBNET_IDS}"
    "AlbSgId=${ALB_SG}"
    "ToolJetTaskSgId=${TOOLJET_TASK_SG}"
    "LambdaSgId=${LAMBDA_SG}"
    "EcsClusterArn=${ECS_CLUSTER_ARN}"
    "CognitoUserPoolArn=${COGNITO_USER_POOL_ARN}"
    "CognitoAppClientId=${COGNITO_APP_CLIENT_ID}"
    "CognitoDomain=${COGNITO_DOMAIN}"
    "OntapCredentialsSecretArns=${ONTAP_CREDENTIALS_SECRET_ARNS}"
    "OntapManagementEndpoints=${ONTAP_MGMT_ENDPOINTS}"
    "ToolJetImageTag=${TOOLJET_IMAGE_TAG}"
    "SessionDurationHours=${SESSION_DURATION_HOURS}"
  )

  # Optional parameters — only pass if set
  [[ -n "${S3_ACCESS_POINT_ARN}" ]] && console_params+=("S3AccessPointArn=${S3_ACCESS_POINT_ARN}")
  [[ -n "${CERTIFICATE_ARN}" ]] && console_params+=("CertificateArn=${CERTIFICATE_ARN}")
  [[ -n "${CUSTOM_DOMAIN_NAME}" ]] && console_params+=("CustomDomainName=${CUSTOM_DOMAIN_NAME}")
  [[ -n "${HOSTED_ZONE_ID}" ]] && console_params+=("HostedZoneId=${HOSTED_ZONE_ID}")

  deploy_stack "${STACK_PREFIX}-console" "${TEMPLATE_DIR}/console.yaml" "${console_params[@]}"

  # Retrieve console stack outputs
  ALB_DNS_NAME=$(get_stack_output "${STACK_PREFIX}-console" "AlbDnsName")
  TOOLJET_SERVICE_ARN=$(get_stack_output "${STACK_PREFIX}-console" "ToolJetServiceArn")
  TOOLJET_SERVICE_NAME=$(get_stack_output "${STACK_PREFIX}-console" "ToolJetServiceName")
  TEMP_BUCKET_NAME=$(get_stack_output "${STACK_PREFIX}-console" "TempBucketName")

  # Retrieve console URL (custom domain if configured, otherwise ALB DNS)
  CONSOLE_URL=$(get_stack_output "${STACK_PREFIX}-console" "ConsoleUrl")
  if [[ -z "${CONSOLE_URL}" ]]; then
    CONSOLE_URL="https://${ALB_DNS_NAME}"
  fi

  log_info "Console outputs retrieved:"
  log_info "  ALB DNS: ${ALB_DNS_NAME}"
  log_info "  Console URL: ${CONSOLE_URL}"
  log_info "  ToolJet Service: ${TOOLJET_SERVICE_ARN}"

  # =========================================================================
  # Stack 5: Monitoring
  # =========================================================================
  log_step "Stack 5/5: ${STACK_PREFIX}-monitoring"

  local monitoring_params=(
    "EcsClusterName=${ECS_CLUSTER_NAME}"
    "HarvestServiceName=${HARVEST_SERVICE_NAME}"
    "ToolJetServiceName=${TOOLJET_SERVICE_NAME}"
    "AlbArn=$(get_stack_output "${STACK_PREFIX}-console" "AlbArn")"
    "ToolJetTargetGroupArn=$(get_stack_output "${STACK_PREFIX}-console" "ToolJetTargetGroupArn")"
  )

  [[ -n "${ALERT_SNS_TOPIC_ARN}" ]] && monitoring_params+=("AlertSnsTopicArn=${ALERT_SNS_TOPIC_ARN}")

  deploy_stack "${STACK_PREFIX}-monitoring" "${TEMPLATE_DIR}/monitoring.yaml" "${monitoring_params[@]}"

  # =========================================================================
  # Deployment complete
  # =========================================================================
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🎉 FSxN Management Console deployed successfully!"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Access the console:"
  echo "  Console URL: ${CONSOLE_URL}"
  if [[ -n "${CUSTOM_DOMAIN_NAME}" ]]; then
    echo "  ALB endpoint: https://${ALB_DNS_NAME}"
  fi
  echo "  Grafana:      ${AMG_WORKSPACE_URL}"
  echo ""
  echo "Stacks deployed:"
  echo "  1. ${STACK_PREFIX}-network"
  echo "  2. ${STACK_PREFIX}-auth"
  echo "  3. ${STACK_PREFIX}-observability"
  echo "  4. ${STACK_PREFIX}-console"
  echo "  5. ${STACK_PREFIX}-monitoring"
  echo ""
  echo "To clean up all resources:"
  echo "  bash ${SCRIPT_DIR}/cleanup.sh"
  echo ""
}

main "$@"
