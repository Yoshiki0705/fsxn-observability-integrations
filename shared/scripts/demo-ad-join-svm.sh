#!/bin/bash
set -euo pipefail
# =============================================================================
# FSx for ONTAP SVM AD Join Helper
#
# Joins an existing FSx for ONTAP SVM to an AWS Managed Microsoft AD.
# Run AFTER deploying demo-ad-environment.yaml (AD must be Active first).
#
# Usage:
#   bash shared/scripts/demo-ad-join-svm.sh \
#     --svm-id svm-0123456789abcdef0 \
#     --ad-stack-name fsxn-demo-ad-env \
#     --ad-password 'YourP@ssw0rd'
#
# Or with explicit parameters:
#   bash shared/scripts/demo-ad-join-svm.sh \
#     --svm-id svm-xxx \
#     --domain demo.fsx.local \
#     --dns-ips '["198.51.100.10","198.51.100.11"]' \
#     --ad-password 'YourP@ssw0rd' \
#     --netbios FSXNSVM
# =============================================================================

REGION="${AWS_REGION:-ap-northeast-1}"
SVM_ID=""
AD_STACK=""
AD_DOMAIN=""
AD_DNS_IPS=""
AD_PASSWORD=""
AD_USERNAME="Admin"
NETBIOS="FSXNSVM"
OU_DN=""
DRY_RUN=false

usage() {
  echo "Usage: $0 --svm-id <svm-id> --ad-stack-name <stack> --ad-password <pass>"
  echo "  or:  $0 --svm-id <svm-id> --domain <domain> --dns-ips <json-array> --ad-password <pass>"
  echo ""
  echo "Options:"
  echo "  --svm-id        FSx SVM ID (required)"
  echo "  --ad-stack-name CFn stack name (resolves domain/DNS automatically)"
  echo "  --domain        AD domain FQDN (if not using --ad-stack-name)"
  echo "  --dns-ips       AD DNS IPs as JSON array (if not using --ad-stack-name)"
  echo "  --ad-password   AD join password (required)"
  echo "  --ad-username   AD join username (default: Admin)"
  echo "  --netbios       NetBIOS name for SVM (default: FSXNSVM, max 15 chars)"
  echo "  --ou            Custom OU DN (default: auto-generated from domain)"
  echo "  --region        AWS region (default: \$AWS_REGION or ap-northeast-1)"
  echo "  --dry-run       Show what would be done without executing"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --svm-id) SVM_ID="$2"; shift 2 ;;
    --ad-stack-name) AD_STACK="$2"; shift 2 ;;
    --domain) AD_DOMAIN="$2"; shift 2 ;;
    --dns-ips) AD_DNS_IPS="$2"; shift 2 ;;
    --ad-password) AD_PASSWORD="$2"; shift 2 ;;
    --ad-username) AD_USERNAME="$2"; shift 2 ;;
    --netbios) NETBIOS="$2"; shift 2 ;;
    --ou) OU_DN="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown: $1"; usage ;;
  esac
done

[[ -z "$SVM_ID" ]] && echo "Error: --svm-id required" && usage
[[ -z "$AD_PASSWORD" ]] && echo "Error: --ad-password required" && usage

# Resolve from CloudFormation stack if --ad-stack-name provided
if [[ -n "$AD_STACK" ]]; then
  echo "Resolving AD info from stack: $AD_STACK"
  AD_DOMAIN=$(aws cloudformation describe-stacks --stack-name "$AD_STACK" --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`DomainName`].OutputValue' --output text)
  AD_ID=$(aws cloudformation describe-stacks --stack-name "$AD_STACK" --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ManagedAdId`].OutputValue' --output text)
  AD_DNS_IPS=$(aws ds describe-directories --directory-ids "$AD_ID" --region "$REGION" \
    --query 'DirectoryDescriptions[0].DnsIpAddrs' --output json)
  echo "  Domain: $AD_DOMAIN"
  echo "  AD ID: $AD_ID"
  echo "  DNS IPs: $AD_DNS_IPS"
fi

[[ -z "$AD_DOMAIN" ]] && echo "Error: Could not resolve domain name" && exit 1
[[ -z "$AD_DNS_IPS" ]] && echo "Error: Could not resolve DNS IPs" && exit 1

# Check current SVM state
echo ""
echo "Checking SVM: $SVM_ID"
SVM_LIFECYCLE=$(aws fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$SVM_ID" --region "$REGION" \
  --query 'StorageVirtualMachines[0].Lifecycle' --output text)
SVM_AD_CURRENT=$(aws fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$SVM_ID" --region "$REGION" \
  --query 'StorageVirtualMachines[0].ActiveDirectoryConfiguration.SelfManagedActiveDirectoryConfiguration.DomainName' --output text 2>/dev/null || echo "")

if [[ -n "$SVM_AD_CURRENT" && "$SVM_AD_CURRENT" != "None" ]]; then
  echo "  SVM already joined to AD: $SVM_AD_CURRENT"
  echo "  No action needed."
  exit 0
fi

echo "  Lifecycle: $SVM_LIFECYCLE"
echo "  AD: Not joined"
echo ""

# Build OU DN from domain name (if not provided via --ou)
if [[ -z "$OU_DN" ]]; then
  # For AWS Managed AD: OU=Computers,OU=<short-name>,DC=x,DC=y,DC=z
  # For self-managed AD: OU=Computers,DC=x,DC=y,DC=z (or custom)
  # AWS Managed AD creates an intermediate OU with the domain short name.
  # Detect: if --ad-stack-name was used (Pattern A), include the intermediate OU.
  IFS='.' read -ra PARTS <<< "$AD_DOMAIN"
  DC_PARTS=""
  for part in "${PARTS[@]}"; do
    DC_PARTS="${DC_PARTS},DC=${part}"
  done

  if [[ -n "$AD_STACK" ]]; then
    # AWS Managed AD: include intermediate OU with short name
    SHORT_NAME="${PARTS[0]}"
    OU_DN="OU=Computers,OU=${SHORT_NAME}${DC_PARTS}"
  else
    # Self-managed AD: simple default (user should override with --ou if needed)
    OU_DN="OU=Computers${DC_PARTS}"
  fi
fi

echo "Joining SVM to AD..."
echo "  Domain: $AD_DOMAIN"
echo "  NetBIOS: $NETBIOS"
echo "  Username: $AD_USERNAME"
echo "  OU: $OU_DN"
echo "  DNS: $AD_DNS_IPS"
echo ""

if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY RUN] Would execute:"
  echo "  aws fsx update-storage-virtual-machine --storage-virtual-machine-id $SVM_ID ..."
  echo ""
  echo "JSON payload:"
  echo "  {\"NetBiosName\": \"$NETBIOS\","
  echo "   \"SelfManagedActiveDirectoryConfiguration\": {"
  echo "     \"DomainName\": \"$AD_DOMAIN\","
  echo "     \"OrganizationalUnitDistinguishedName\": \"$OU_DN\","
  echo "     \"UserName\": \"$AD_USERNAME\","
  echo "     \"DnsIps\": $AD_DNS_IPS}}"
  exit 0
fi

aws fsx update-storage-virtual-machine \
  --storage-virtual-machine-id "$SVM_ID" \
  --active-directory-configuration "{
    \"NetBiosName\": \"${NETBIOS}\",
    \"SelfManagedActiveDirectoryConfiguration\": {
      \"DomainName\": \"${AD_DOMAIN}\",
      \"OrganizationalUnitDistinguishedName\": \"${OU_DN}\",
      \"UserName\": \"${AD_USERNAME}\",
      \"Password\": \"${AD_PASSWORD}\",
      \"DnsIps\": ${AD_DNS_IPS},
      \"FileSystemAdministratorsGroup\": \"Domain Admins\"
    }
  }" --region "$REGION" > /dev/null

echo "AD join initiated. Waiting for completion..."

for i in $(seq 1 30); do
  sleep 20
  SVM_STATUS=$(aws fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$SVM_ID" --region "$REGION" \
    --query 'StorageVirtualMachines[0].Lifecycle' --output text)
  SVM_AD_NOW=$(aws fsx describe-storage-virtual-machines --storage-virtual-machine-ids "$SVM_ID" --region "$REGION" \
    --query 'StorageVirtualMachines[0].ActiveDirectoryConfiguration.SelfManagedActiveDirectoryConfiguration.DomainName' --output text 2>/dev/null || echo "")

  if [[ -n "$SVM_AD_NOW" && "$SVM_AD_NOW" != "None" && "$SVM_STATUS" == "CREATED" ]]; then
    echo ""
    echo "✅ SVM AD join complete!"
    echo "  Domain: $SVM_AD_NOW"
    echo "  Lifecycle: $SVM_STATUS"
    echo ""
    echo "Next steps:"
    echo "  1. Create a CIFS share on the SVM:"
    echo "     vserver cifs share create -vserver <svm-name> -share-name data -path /data"
    echo "  2. Connect from Windows: \\\\<svm-dns>\\data (user: ${AD_DOMAIN}\\Admin)"
    exit 0
  fi
  echo "  [$i/30] Lifecycle=$SVM_STATUS, AD=$SVM_AD_NOW"
done

echo ""
echo "⚠️  Timeout waiting for AD join. Check SVM status manually:"
echo "  aws fsx describe-storage-virtual-machines --storage-virtual-machine-ids $SVM_ID"
exit 1
