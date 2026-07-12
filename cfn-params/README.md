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

## Pre-flight Check

Before deploying, run the pre-flight validation:

```bash
bash shared/scripts/preflight-check.sh --vpc-id vpc-xxx --profile automated-response
```
