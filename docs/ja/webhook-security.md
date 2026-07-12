# EMS Webhook セキュリティガイド

🌐 **日本語**（このページ） | [English](../en/webhook-security.md)

## 概要

ONTAP EMS Webhook はイベント通知を HTTPS エンドポイントに配信します。本ガイドでは、これらのイベントを受信する API Gateway エンドポイントのセキュリティ対策について説明します。

## 認証モード

共有 EMS Webhook テンプレート（`shared/templates/ems-webhook-apigw.yaml`）は 4 つの認証モードをサポートしています:

| モード | `WebhookAuthMode` | ユースケース | ONTAP 互換性 |
|------|-------------------|----------|---------------------|
| None | `NONE` | クイックスタート / PoC 専用 | ✅ 設定不要 |
| API Key | `API_KEY` | 使用量プランによる基本的な保護 | ✅ カスタムヘッダーサポート |
| IAM SigV4 | `IAM` | AWS ネイティブ認証 | ⚠️ SigV4 署名機能が必要 |
| Shared Secret | `SHARED_SECRET` | 本番推奨 | ✅ Authorization ヘッダーの Bearer トークン |

## 推奨: Shared Secret（Lambda Authorizer）

本番 EMS Webhook には `SHARED_SECRET` モードを使用してください。Secrets Manager に保存されたシークレットに対して Bearer トークンを検証する Lambda Authorizer がデプロイされます。

### 動作の仕組み

```
ONTAP EMS → HTTPS POST with Authorization: Bearer <token>
    → API Gateway
    → Lambda Authorizer (validates token against Secrets Manager)
    → If valid: invoke EMS handler Lambda
    → If invalid: return 401/403
```

### セットアップ

1. **Secrets Manager に Webhook シークレットを作成**:

```bash
aws secretsmanager create-secret \
  --name "fsxn/ems-webhook-secret" \
  --secret-string '{"webhook_secret": "<generate-a-strong-random-token>"}' \
  --region ap-northeast-1
```

2. **SHARED_SECRET モードでデプロイ**:

```bash
aws cloudformation deploy \
  --template-file shared/templates/ems-webhook-apigw.yaml \
  --stack-name fsxn-ems-webhook \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    LambdaFunctionArn=<ems-handler-arn> \
    WebhookAuthMode=SHARED_SECRET \
    WebhookSecretArn=<secret-arn>
```

3. **ONTAP EMS Webhook 送信先を Authorization ヘッダー付きで設定**:

```
vserver ems destination create -name grafana-webhook \
  -rest-api-url https://<api-id>.execute-api.<region>.amazonaws.com/prod/ems \
  -certificate-authority <ca-name>
```

> **注意**
>
> ONTAP EMS Webhook のカスタムヘッダー設定は ONTAP バージョンによって異なります。`Authorization: Bearer <token>` ヘッダーを Webhook リクエストに追加する正しい構文については、ONTAP ドキュメントを参照してください。

### シークレットローテーション

Lambda Authorizer はシークレットを 5 分間キャッシュします（Authorizer コードの `_SECRET_TTL` で設定可能）。Secrets Manager でシークレットをローテーションした後:

1. キャッシュ TTL 期間中は旧トークンと新トークンの両方が有効
2. 5 分後、新トークンのみが受け入れられる
3. Lambda の再デプロイは不要

ゼロダウンタイムローテーション:
1. 新しいトークンでシークレットを更新
2. Authorizer キャッシュの有効期限切れを待つ（5 分）
3. ONTAP EMS Webhook 設定を新しいトークンで更新

## 追加のハードニング

認証モードに関わらず、以下の追加制御を検討してください:

### API Gateway リソースポリシー

ソース IP または VPC でアクセスを制限:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*",
      "Condition": {
        "IpAddress": {
          "aws:SourceIp": ["<ontap-management-ip>/32"]
        }
      }
    }
  ]
}
```

### WAF 統合

インターネット公開エンドポイントの場合、以下を含む AWS WAF をアタッチ:
- レート制限（悪用防止）
- IP レピュテーションリスト
- リクエストサイズ制限
- 地理的制限

### スロットリング

テンプレートには設定可能なスロットリングが含まれています:
- `ThrottlingRateLimit`: 1 秒あたりのリクエスト数（デフォルト: 100）
- `ThrottlingBurstLimit`: バースト容量（デフォルト: 50）

EMS イベントボリュームに基づいて調整してください。

## セキュリティ判断マトリクス

| デプロイ環境 | 推奨認証 | 追加制御 |
|-----------|-----------------|---------------------|
| Dev/PoC | `NONE` | 不要 |
| Staging | `API_KEY` | スロットリング |
| 本番（プライベートネットワーク） | `SHARED_SECRET` | リソースポリシー（ソース IP） |
| 本番（インターネット公開） | `SHARED_SECRET` | リソースポリシー + WAF + スロットリング |

## 推奨する本番ベースライン

ほとんどのデプロイでは、以下の組み合わせが過度な複雑さなしに強固なセキュリティを提供します:

1. **API Gateway Lambda Authorizer** と Shared Secret（Bearer トークン）
2. **AWS Secrets Manager にシークレットを保存**（ローテーションスケジュール付き）
3. **ソース IP 制限**（API Gateway リソースポリシー経由、ONTAP 管理アドレスが安定している場合）
4. **AWS WAF**（インターネット公開エンドポイント向け、レート制限、IP レピュテーション）
5. **API Gateway アクセスログ**を有効化（監査証跡用）
6. **CloudWatch アラーム**（認証失敗 `4XX` カウント）
7. **シークレットローテーション手順書**を文書化・テスト済み

> 初期本番デプロイでは項目 1〜3 から開始してください。エンドポイントがインターネット公開の場合、またはコンプライアンスで要求される場合に WAF（項目 4）を追加してください。

## ファイル一覧

| ファイル | 用途 |
|------|---------|
| `shared/templates/ems-webhook-apigw.yaml` | API Gateway CloudFormation テンプレート |
| `shared/lambda/authorizers/shared_secret_authorizer.py` | Lambda Authorizer コード |
| `shared/python/auth_cache.py` | 再利用可能な認証情報キャッシュ（ハンドラー側認証用） |
