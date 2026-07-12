# CloudFormation Parameter Files

Sample parameter files for deploying stacks in this project.

## Format

Files use the [AWS CloudFormation parameter file format](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html):

```json
[
  {"ParameterKey": "Name", "ParameterValue": "value"},
  ...
]
```

## Usage

```bash
# 1. Copy and customize
cp cfn-params/automated-response.example.json cfn-params/automated-response.json
# Edit values in the file

# 2. Deploy with create-stack (supports file:// parameters)
aws cloudformation create-stack \
  --stack-name fsxn-automated-response \
  --template-body file://shared/templates/automated-response.yaml \
  --parameters file://cfn-params/automated-response.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

# 3. Or deploy with deploy (Key=Value format, no file support)
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=198.51.100.10 \
    OntapCredentialsSecretArn=arn:aws:secretsmanager:... \
    VpcId=vpc-xxx \
    SubnetIds=subnet-aaa,subnet-bbb \
    SecurityGroupId=sg-xxx \
    DefaultSvmName=svm-prod \
    CreateVpcEndpoints=true \
  --capabilities CAPABILITY_NAMED_IAM
```

## Important Notes

- `aws cloudformation deploy --parameter-overrides` does **not** support `file://` — use inline `Key=Value` pairs
- `aws cloudformation create-stack --parameters` **does** support `file://` with the JSON array format shown above
- For updates: use `aws cloudformation update-stack --parameters file://...` (same format)
- Never commit filled-in parameter files with real credentials or account IDs to version control
- The `.gitignore` excludes `cfn-params/*.json` (only `.example.json` files are tracked)

## Files

| File | Stack | Notes |
|------|-------|-------|
| `automated-response.example.json` | `automated-response.yaml` | VPC required. Set CreateVpcEndpoints=false if EPs exist. |
| `automated-response-ttl.example.json` | `automated-response-ttl.yaml` | Deploy after automated-response. Same VPC params. |
| `restore-verification.example.json` | `restore-verification.yaml` | Requires: UNIX vol, no ONTAP S3 server, Route Table IDs. |
| `content-classification.example.json` | `content-classification-scanner.yaml` | VpcId empty = simplest (no VPC). |
| `vendor-datadog.example.json` | `integrations/datadog/template.yaml` | Representative vendor example. No VPC by default. |
| `demo-ad-environment.example.json` | `demo-ad-environment.yaml` | Creates AD + Windows/Linux EC2 for demo screenshots. Delete after use. |

## Demo AD Environment: Which Pattern to Choose?

```
Do you have an Active Directory?
│
├── NO → Pattern A: create-new
│   └── Template creates AWS Managed AD (~$0.30/hr, ~15 min to provision)
│       AdMode=create-new, fill AdDomainName + AdPassword
│
├── YES, AWS Managed AD (via AWS Directory Service)
│   └── Pattern B: use-existing-managed
│       AdMode=use-existing-managed, fill ExistingDirectoryId
│       Windows EC2 will auto-join. SVM join uses script with --domain/--dns-ips.
│
└── YES, Self-managed AD (EC2 instance or on-premises via VPN/Direct Connect)
    └── Pattern C: use-self-managed
        AdMode=use-self-managed
        Fill: SelfManagedAdDomainName, SelfManagedAdDnsIps, SelfManagedAdUsername,
              SelfManagedAdPassword, SelfManagedAdOu
        Windows EC2 domain join: manual via PowerShell (no SSM auto-join for self-managed)
        SVM join: script with explicit --domain/--dns-ips/--ou
```

### Required AD Ports (Security Group)

For the Windows EC2 and FSx SVM to communicate with AD controllers:

| Port | Protocol | Purpose |
|------|----------|---------|
| 53 | TCP/UDP | DNS |
| 88 | TCP/UDP | Kerberos |
| 389 | TCP/UDP | LDAP |
| 445 | TCP | SMB/CIFS |
| 636 | TCP | LDAPS |
| 3268 | TCP | Global Catalog |
| 9389 | TCP | AD Web Services |

For demo, a "allow all within VPC" security group is simplest. For production, restrict to these ports only.

## AD Join: Common Pitfalls (Verified)

These failures were encountered and resolved during E2E verification on ONTAP 9.17.1P7D1:

### 1. AWS Managed AD OU Path

AWS Managed AD creates an intermediate OU with the domain's short name. If you specify the OU path manually, include it:

```
✅ Correct: OU=Computers,OU=demo,DC=demo,DC=fsx,DC=local
❌ Wrong:   OU=Computers,DC=demo,DC=fsx,DC=local  (missing OU=demo)
```

The `demo-ad-join-svm.sh` script handles this automatically when `--ad-stack-name` is used.

### 2. FileSystemAdministratorsGroup

| Group | Result |
|-------|--------|
| `Domain Admins` | ✅ Works |
| `AWS Delegated FSx Administrators` | ❌ MISCONFIGURED (insufficient SVM join permissions) |

Always use `Domain Admins` for SVM AD join.

### 3. SSM Domain Join (Windows EC2)

```
❌ SsmAssociations + custom SSM Document with schemaVersion 2.2
   → "Document schema version, 2.2, is not supported by association"

✅ AWS::SSM::Association (separate resource) + AWS-JoinDirectoryServiceDomain (AWS-managed doc)
```

### 4. NetBIOS Name Conflict

The SVM's NetBIOS name must be DIFFERENT from the AD domain's ShortName:
- Domain `demo.fsx.local` → ShortName is `demo`
- SVM NetBIOS must NOT be `DEMO` — use something like `FSXNSVM` or `DEMOSVM`

### 5. MISCONFIGURED Recovery

If the SVM enters `MISCONFIGURED` state, you can retry with corrected parameters — no need to delete the SVM:
```bash
aws fsx update-storage-virtual-machine --storage-virtual-machine-id svm-xxx \
  --active-directory-configuration '{...corrected config...}'
```

## Pre-flight Check

Before deploying, run the pre-flight validation:

```bash
bash shared/scripts/preflight-check.sh --vpc-id vpc-xxx --profile automated-response
```
