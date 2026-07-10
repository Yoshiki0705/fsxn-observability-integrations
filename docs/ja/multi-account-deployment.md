# AWS Organizations を使用したマルチアカウントデプロイ

🌐 **日本語**（このページ） | [English](../en/multi-account-deployment.md)

## 概要

CloudFormation StackSets を使用して、複数の AWS アカウントに FSx for ONTAP Observability Pipeline をデプロイします。このパターンにより、監査ログパイプラインの一元管理を実現しつつ、データ処理は各アカウントのローカルで行います。

## アーキテクチャ

```
管理アカウント
  |
  CloudFormation StackSet (service-managed permissions)
  |
  +---> アカウント A (ap-northeast-1)
  |       Lambda + EventBridge + DLQ + Secrets Manager
  |
  +---> アカウント B (ap-northeast-1)
  |       Lambda + EventBridge + DLQ + Secrets Manager
  |
  +---> アカウント C (us-east-1)
          Lambda + EventBridge + DLQ + Secrets Manager

一元管理: StackSet 管理、クロスアカウントダッシュボード
アカウント別: FSx for ONTAP、S3 AP、ベンダー認証情報、監査データ
```

## 主要な設計判断

| 判断事項 | 選択 | 根拠 |
|---------|------|------|
| 権限モデル | SERVICE_MANAGED | ターゲットアカウントで手動 IAM ロール不要 |
| データローカリティ | アカウント別処理 | 監査ログがソースアカウントから出ない |
| 認証情報の分離 | アカウント別 Secrets Manager | クロスアカウント認証情報共有なし |
| 自動デプロイ | デフォルトで有効 | 新規アカウントに自動的にパイプラインをデプロイ |
| 障害許容度 | 10% | 不正なテンプレート更新の影響範囲を制限 |

## 前提条件

### 1. AWS Organizations のセットアップ

```bash
# Organizations が有効であることを確認
aws organizations describe-organization \
  --query 'Organization.{Id:Id, MasterAccountId:MasterAccountId}'

# StackSets の信頼されたアクセスを有効化
aws organizations enable-aws-service-access \
  --service-principal member.org.stacksets.cloudformation.amazonaws.com
```

### 2. アカウント別の準備

各ターゲットアカウントに必要なもの：

1. **監査ログが有効な FSx for ONTAP**
2. **SSM Parameter Store に保存された S3 Access Point ARN**：
   ```bash
   aws ssm put-parameter \
     --name "/fsxn/s3-access-point-arn" \
     --value "arn:aws:s3:<region>:<account-id>:accesspoint/fsxn-audit-ap" \
     --type String
   ```
3. **Secrets Manager のベンダー認証情報**：
   ```bash
   aws secretsmanager create-secret \
     --name "<vendor>/fsxn-credentials" \
     --secret-string '{"api_key":"<key>"}'
   ```

### 3. テンプレートのアップロード

全アカウントからアクセス可能な S3 バケットにベンダーテンプレートをアップロード：

```bash
aws s3 cp integrations/<vendor>/template.yaml \
  s3://<stackset-templates-bucket>/<vendor>/template.yaml
```

## デプロイ

```bash
aws cloudformation deploy \
  --template-file shared/templates/multi-account-stackset.yaml \
  --stack-name fsxn-<vendor>-stackset-admin \
  --parameter-overrides \
    OrganizationalUnitIds=ou-xxxx-yyyyyyyy \
    VendorName=<vendor> \
    VendorTemplateUrl=https://s3.<region>.amazonaws.com/<bucket>/<vendor>/template.yaml \
    VendorCredentialSecretName=<vendor>/fsxn-credentials \
    Regions=ap-northeast-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

## 監視

```bash
# アカウント別のインスタンスステータスを確認
aws cloudformation list-stack-instances \
  --stack-set-name fsxn-<vendor>-observability-pipeline \
  --call-as SELF \
  --query 'Summaries[].{Account:Account, Region:Region, Status:StackInstanceStatus.DetailedStatus}'
```

## クロスアカウント Observability

全アカウントの一元監視には、CloudWatch クロスアカウント Observability を有効化するか、Organization スコープの publish 権限を持つ中央 SNS トピックにアラームを集約します。

## 運用手順

### 新規アカウントの追加
1. アカウントがターゲット OU に参加
2. StackSet が自動デプロイ（AutoDeployment=true の場合）
3. 新規アカウントで SSM パラメータと Secrets Manager シークレットを作成
4. StackSet インスタンスのステータスを確認

### アカウントの削除
1. アカウントが OU から離脱
2. StackSet がスタックを自動削除
3. 必要に応じて Secrets Manager を手動クリーンアップ

### 失敗したインスタンスのトラブルシューティング
```bash
aws cloudformation describe-stack-instance \
  --stack-set-name fsxn-<vendor>-observability-pipeline \
  --stack-instance-account <account-id> \
  --stack-instance-region <region> \
  --call-as SELF \
  --query 'StackInstance.StatusReason'
```

## セキュリティ上の考慮事項

- 各アカウントが独自の Secrets Manager シークレットを保持（クロスアカウント認証情報共有なし）
- 監査ログがソースアカウントから出ない
- FailureTolerancePercentage が影響範囲を制限
- S3 バケットポリシーがテンプレートアクセスを Organization のみに制限

## 関連ドキュメント

- [Pipeline SLO](pipeline-slo.md)
- [コンプライアンスエビデンスパック](compliance-evidence-pack.md)
- [クロスリージョンレプリケーション](cross-region-replication.md)
