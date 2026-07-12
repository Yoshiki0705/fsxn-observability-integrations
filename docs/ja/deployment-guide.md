# デプロイメントガイド — 既存 FSx for ONTAP 環境への統合

🌐 **日本語** (このページ) | [English](../en/deployment-guide.md)

## 概要

このガイドは、Amazon FSx for NetApp ONTAP が稼働中の環境に対して、本プロジェクトのオブザーバビリティ/セキュリティスタックをデプロイする手順を説明します。本プロジェクトの全テンプレートは**オーバーレイ設計**であり、FSx ファイルシステム・SVM・ボリュームを新規作成しません。既存インフラの上に監視、インシデント対応、データ保護の機能を追加します。

## 開始前に必要な情報

既存環境から以下を収集してください。

| # | リソース | 確認場所 | 使用先スタック |
|---|----------|----------|---------------|
| 1 | FSx ファイルシステム ID | FSx コンソール → ファイルシステム → `fs-xxxxxxxxxxxxxxxxx` | `fsxn-audit-config`, `restore-verification` |
| 2 | 管理エンドポイント IP | FSx コンソール → ファイルシステム詳細 → 管理 DNS/IP | `automated-response`, `restore-verification`, `fpolicy-apigw`, `lakehouse-monitoring` |
| 3 | SVM 名 | FSx コンソール → ストレージ仮想マシン | `automated-response`, `automated-response-ttl` |
| 4 | SVM ID | FSx コンソール → SVM 詳細 → `svm-xxxxxxxxxxxxxxxxx` | `fsxn-audit-config` |
| 5 | VPC ID | VPC コンソール | 全 VPC モードスタック |
| 6 | プライベートサブネット ID | VPC コンソール → サブネット（FSx ENI と同じ AZ） | 全 VPC モードスタック |
| 7 | セキュリティグループ ID | FSx 管理 IP への HTTPS (443) を許可する SG | 全 VPC モードスタック |
| 8 | ルートテーブル ID | VPC コンソール → ルートテーブル → サブネット関連付け | `restore-verification`, `content-classification-scanner` |
| 9 | ONTAP 管理者クレデンシャル Secret ARN | Secrets Manager → `arn:aws:secretsmanager:...` | `automated-response`, `restore-verification` |
| 10 | S3 Access Point ARN | S3 コンソールまたは `aws fsx describe-data-repository-associations` | `prerequisites`, ベンダースタック |

## スタック一覧

### Tier 1: 監査ログ転送（ベンダー統合）

FSx for ONTAP の監査ログをオブザーバビリティベンダーに転送するスタック群。Lambda を VPC 外で実行する場合、VPC 設定は不要です。

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Prerequisites | `shared/templates/prerequisites.yaml` | FsxS3AccessPointArn | No |
| S3 Access Point | `shared/templates/s3-access-point.yaml` | BucketName, VpcId (optional) | No |
| Vendor (×10) | `integrations/<vendor>/template.yaml` | FsxS3AccessPointArn, VendorSecretArn | No (default) |

### Tier 2: インシデント対応

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Automated Response | `shared/templates/automated-response.yaml` | OntapMgmtIp, Secret ARN, VPC/Subnet/SG, DefaultSvmName | Yes |
| TTL Auto-Unblock | `shared/templates/automated-response-ttl.yaml` | Same as above + BlockTtlMinutes, CheckIntervalMinutes | Yes |

### Tier 3: データ保護と分類

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Restore Verification | `shared/templates/restore-verification.yaml` | OntapMgmtIp, FileSystemId, Secret ARN, VPC, Subnet, SG, Route Tables | Yes |
| Content Classification | `shared/templates/content-classification-scanner.yaml` | VpcId (optional), LanguageCode | No (default) |

### Tier 4: 高度な監視

| Stack | Template | Key Parameters | VPC Required |
|-------|----------|---------------|--------------|
| Syslog → CloudWatch | `shared/templates/syslog-vpce-cloudwatch.yaml` | VpcId, SubnetIds, VpcCidr | Yes |
| FPolicy Server | `shared/templates/fpolicy-server-fargate.yaml` | VpcId, SubnetIds, FsxnSvmSecurityGroupId, ContainerImage | Yes |
| CloudWatch Log Alarm | `shared/templates/cloudwatch-log-alarm.yaml` | LogGroupName, TargetPattern | No |
| Lakehouse Monitoring | `shared/templates/lakehouse-monitoring.yaml` | OntapMgmtEndpoint, S3AccessPointArn, VPC/Subnet/SG | Yes |

### Tier 5: 運用アドオン

| Stack | Template | Purpose |
|-------|----------|---------|
| Object Ledger | `shared/templates/object-ledger.yaml` | DynamoDB per-file processing state |
| SQS Buffering | `shared/templates/sqs-buffering.yaml` | SQS buffer + DLQ for high-volume |
| Secrets Rotation | `shared/templates/secrets-rotation-sample.yaml` | Auto-rotate vendor API keys |
| PagerDuty Escalation | `shared/templates/pagerduty-escalation.yaml` | Alert routing to PagerDuty |

---

## VPC Endpoint 競合マトリクス

複数のスタックが VPC Endpoint を作成できます。2種類の競合メカニズムを理解することが重要です。

- **Interface Endpoint**（SecretsManager, SNS, STS, Comprehend）: 同一 VPC 内に同一サービスの `PrivateDnsEnabled=true` の Interface Endpoint を2つ作成すると `"private-dns-enabled cannot be set because there is already a conflicting DNS domain"` エラーでデプロイがロールバックされます。最も頻繁に発生するデプロイ失敗です。
- **Gateway Endpoint**（S3, DynamoDB）: DNS 競合は発生しませんが、同一ルートテーブルに同じサービスの Gateway Endpoint を2つ紐づけることはできません。

既にエンドポイントが存在する場合は、対応する `CreateXxxEndpoint=false` を設定してください。

| Service | Type | automated-response | restore-verification | content-classification | syslog-vpce | vpc-endpoints |
|---------|------|:------------------:|:--------------------:|:----------------------:|:-----------:|:-------------:|
| **SecretsManager** | Interface | `CreateVpcEndpoints` | `CreateSecretsManagerEndpoint` | — | — | Always |
| **SNS** | Interface | `CreateVpcEndpoints` | — | `CreateVpcEndpoints` | — | — |
| **STS** | Interface | — | `CreateStsEndpoint` | — | — | — |
| **Comprehend** | Interface | — | — | `CreateVpcEndpoints` | — | — |
| **CW Logs Syslog** | Interface | — | — | — | Always | — |
| **S3** | Gateway | — | `CreateS3GatewayEndpoint` | `CreateVpcEndpoints` | — | Always |
| **DynamoDB** | Gateway | — | — | `CreateVpcEndpoints` | — | — |

### 既存エンドポイントの確認方法

```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
  --query 'VpcEndpoints[].{Service:ServiceName,Type:VpcEndpointType,State:State}' \
  --output table
```

### 判断ルール

デプロイする各スタックについて、以下を実行してください。
1. 上記のコマンドで既存エンドポイントを確認
2. スタックが作成するエンドポイントが既に存在するか照合
3. 存在する場合 → 該当の `Create*Endpoint=false` に設定
4. 存在しない場合 → `true`（デフォルト）のまま

---

## 検証済みデプロイパス

### Path 1: 監査ログ転送（最もシンプル）

**目的**: FSx for ONTAP の監査ログをオブザーバビリティベンダーに転送する。

```
s3-access-point.yaml → prerequisites.yaml → integrations/<vendor>/template.yaml
```

**手順**:
1. SVM で監査ログを有効化（ONTAP CLI: `vserver audit create`）
2. ログ配信先の S3 バケットを作成
3. `s3-access-point.yaml` をデプロイ（Lambda 用の AP を作成）
4. `prerequisites.yaml` をデプロイ（EventBridge スケジューラ、チェックポイントテーブル）
5. ベンダーテンプレートをデプロイ（例: `integrations/datadog/template.yaml`）

**VPC 設定は不要です。** Lambda はデフォルトで VPC 外にデプロイされます。

### Path 2: インシデント対応

**目的**: ユーザー/IP の自動ブロックと TTL ベースの自動解除。

```
automated-response.yaml (CreateVpcEndpoints=true)
  → automated-response-ttl.yaml
```

**手順**:
1. ONTAP 管理者クレデンシャルを Secrets Manager に保存
2. VPC/Subnet/SG を指定して `automated-response.yaml` をデプロイ
3. Lambda Layer（`shared/lambda-layers/`）をデプロイし、関数に適用
4. 同じ VPC パラメータで `automated-response-ttl.yaml` をデプロイ

**セキュリティに関する補足**: Lambda は ONTAP 管理 IP に直接到達するため VPC 内で実行されます。Secrets Manager と SNS の VPC Endpoint は最初のスタックが作成します。

### Path 3: リカバリポイント検証

**目的**: スナップショットの復元前にランサムウェア指標をスキャンして安全性を検証する。

```
automated-response.yaml (first, creates SecretsManager EP)
  → restore-verification.yaml (CreateSecretsManagerEndpoint=false)
```

**このパス固有の前提条件**:
- 対象ボリュームが **UNIX セキュリティスタイル**であること（確認: `volume show -fields security-style`）
- 対象 SVM に **ONTAP ネイティブ S3 サーバーが無効**であること（確認: `vserver object-store-server show`）
- サブネットのルートテーブル ID が必要

**手順**:
1. 前提条件を検証（`preflight-check.sh --profile restore-verification` を実行）
2. `automated-response.yaml` が未デプロイなら先にデプロイ
3. `CreateSecretsManagerEndpoint=false` を指定して `restore-verification.yaml` をデプロイ
4. スナップショット詳細を指定して Step Functions ワークフローを実行

### Path 4: コンテンツ分類（PII スキャナー）

**目的**: Amazon Comprehend を使い、FSx for ONTAP ボリューム上のファイルから PII を検出する。

```
content-classification-scanner.yaml (VPC外 mode)
```

**最もシンプルなデプロイ** — VpcId を空のままにします。対象ボリュームに Internet-origin S3 Access Point がアタッチされている必要があります。

VPC スコープのアクセスポイント（restore-verification が作成するもの）を使う場合は、VpcId を設定し、既存のエンドポイントがあれば作成を無効にしてください。

### Path 5: フルスイート（全機能）

VPC Endpoint の競合を回避するため、以下の順序でデプロイしてください。

| Order | Stack | Endpoint Settings |
|-------|-------|-------------------|
| 1 | `automated-response.yaml` | `CreateVpcEndpoints=true` (creates SecretsManager + SNS) |
| 2 | `automated-response-ttl.yaml` | No endpoints created |
| 3 | `restore-verification.yaml` | `CreateSecretsManagerEndpoint=false`, `CreateStsEndpoint=true`, `CreateS3GatewayEndpoint=false` (if S3 GW EP exists) |
| 4 | `content-classification-scanner.yaml` | Deploy in **VPC-外 mode** (VpcId='') for simplicity |
| 5 | `syslog-vpce-cloudwatch.yaml` | Always creates CW Logs Syslog EP (unique, no conflict) |

---

## デプロイ前検証 (Pre-flight)

VPC モードのスタックをデプロイする前に、事前検証スクリプトを実行してください。

```bash
bash shared/scripts/preflight-check.sh \
  --vpc-id vpc-0123456789abcdef0 \
  --profile automated-response

# Available profiles:
#   audit-shipping        — Path 1
#   automated-response    — Path 2
#   restore-verification  — Path 3
#   content-classification — Path 4
#   full-suite            — Path 5
```

スクリプトの確認項目:
- 既存 VPC Endpoint（重複作成によるデプロイ失敗の防止）
- セキュリティグループのエグレスルール（ONTAP 管理 IP への HTTPS 443）
- サブネットのルートテーブル関連付け
- 対象 SVM の ONTAP S3 サーバー有無（restore-verification のみ）
- S3 Access Point のネットワークオリジン（Internet vs VPC）

---

## パラメータファイルテンプレート

`cfn-params/` に CloudFormation 標準 JSON 形式のサンプルパラメータファイルがあります。

```
cfn-params/
├── README.md                              ← Usage instructions
├── automated-response.example.json
├── automated-response-ttl.example.json
├── restore-verification.example.json
├── content-classification.example.json
└── vendor-datadog.example.json
```

コピーしてリネーム（`.example` を削除）し、値を入力してからデプロイします。

```bash
cp cfn-params/automated-response.example.json cfn-params/automated-response.json
# Edit with your values

# Option A: create-stack (supports file:// parameter files)
aws cloudformation create-stack \
  --stack-name fsxn-automated-response \
  --template-body file://shared/templates/automated-response.yaml \
  --parameters file://cfn-params/automated-response.json \
  --capabilities CAPABILITY_NAMED_IAM

# Option B: deploy (inline Key=Value only — no file:// support)
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=198.51.100.10 \
    OntapCredentialsSecretArn=arn:aws:secretsmanager:... \
    VpcId=vpc-xxx SubnetIds=subnet-aaa,subnet-bbb \
    SecurityGroupId=sg-xxx DefaultSvmName=svm-prod \
    CreateVpcEndpoints=true \
  --capabilities CAPABILITY_NAMED_IAM
```

**運用に関する補足**: `aws cloudformation deploy --parameter-overrides` は `file://` を**サポートしません**。`deploy` コマンドではインラインの `Key=Value` 形式を使用するか、`create-stack --parameters file://` で JSON ファイルベースのデプロイを行ってください。

---

## デプロイ所要時間の目安

| Path | Stacks | Estimated Duration | Notes |
|------|--------|--------------------|-------|
| 1: Audit Log Shipping | 3 | 5–10 minutes | No VPC Endpoints to create |
| 2: Incident Response | 2 | 8–15 minutes | Interface EP creation: ~2 min each |
| 3: Recovery Point Verification | 2 | 10–20 minutes | STS EP creation adds time |
| 4: Content Classification | 1 | 3–5 minutes (VPC外) | VPC mode adds 5–10 min for EPs |
| 5: Full Suite | 5 | 25–40 minutes | Deploy sequentially |

**運用に関する補足**: restore-verification（Path 3）の Step Functions 実行は、FlexClone への S3 Access Point アタッチ時の FSx for ONTAP 内部同期のため、追加で 15〜40 分かかります。

---

## コスト情報

### VPC Endpoint（固定月額）

| Endpoint Type | Cost (per endpoint) | Notes |
|---------------|--------------------:|-------|
| Interface (SecretsManager, SNS, STS, Comprehend) | ~$7.20/month + $0.01/GB | Per-AZ ENI charge |
| Gateway (S3, DynamoDB) | Free | No hourly or data charges |

**フルスイートのベースライン**（Interface EP 4本 × 2 AZ）: データ処理前で約 $57.60/月。

### コンピュートと API コスト（従量課金）

| Service | Pricing | Typical Monthly (light usage) |
|---------|---------|------------------------------:|
| Lambda (audit polling, 5-min schedule) | $0.20/1M requests + compute | $1–5 |
| Lambda (incident response, event-driven) | Same | < $1 |
| Step Functions (restore-verification) | $0.025/1K transitions | < $1 |
| Comprehend DetectPiiEntities | $0.0001/unit (100 chars) | Varies by scan volume |
| DynamoDB (checkpoint/ledger) | Pay-per-request | < $1 |
| EventBridge Scheduler | $1/1M invocations | < $1 |
| SNS notifications | $0.50/1M publishes | < $1 |

**コストに関する補足**: 最大の変動コストは Comprehend PII スキャン（content-classification）です。平均 10 KB のファイル 10,000 件をスキャンすると、1 回のスキャンで約 $10 かかります。

### コスト最適化

- 必要なパスのみデプロイ（監査ログ転送だけならフルスイートは不要）
- 可能な限り Gateway EP（S3, DynamoDB）を使用 — 無料
- content-classification の `DefaultMaxFiles` でスキャンあたりの Comprehend コストを制限
- content-classification を VPC 外モードでデプロイすれば追加の 4 つの VPC Endpoint が不要

### データ処理に関する考慮事項（コンテンツ分類）

content-classification-scanner を使用する場合、FSx for ONTAP ボリューム上のファイル内容が Amazon Comprehend の `DetectPiiEntities` API に送信されて分析されます。Comprehend は同一 AWS リージョン内でデータを処理し、処理後にデータを保存しません。ただし、ファイル内容を AWS AI サービスに送信することを制限するデータレジデンシーや分類ポリシーがある場合は、機密ボリュームで PII スキャンを有効にする前にコンプライアンスチームと確認してください。

---

## ONTAP バージョン要件

| Feature | Minimum ONTAP Version | FSx for ONTAP Support |
|---------|----------------------|----------------------|
| REST API (all stacks) | 9.6+ | All FSx for ONTAP versions |
| S3 Access Point (restore-verification, classification) | 9.11.1+ | Supported since launch (9.11.1+) |
| Audit logging (NAS) | 9.0+ | All FSx for ONTAP versions |
| Name-mapping (automated-response) | 9.0+ | All FSx for ONTAP versions |
| FPolicy (external server) | 9.0+ | All FSx for ONTAP versions |

FSx for ONTAP は ONTAP 9.11.1 以降で動作するため、本プロジェクトの全機能がサポートされます。

---

## 既存インフラとの制約

### ONTAP S3 サーバーの排他制約（restore-verification のみ）

FSx for ONTAP S3 Access Point と ONTAP ネイティブ S3 サーバーは、同一 SVM 上で排他的です。SVM に ONTAP S3 サーバーが有効になっている場合、`restore-verification` スタックの FlexClone + S3 AP アタッチステップは以下のエラーで失敗します。

> Amazon FSx is unable to create an S3 access point because of an existing ONTAP object storage server on SVM {svm}

**対処法**: ONTAP S3 サーバーのない別の SVM を使用するか、既存サーバーを削除する（データ損失リスクあり — チームと確認のこと）。

### ボリュームセキュリティスタイル（restore-verification のみ）

S3 Access Point は対象ボリュームに UNIX セキュリティスタイルを要求します。NTFS や mixed ボリュームは直接の S3 AP アタッチに対応していません。

**確認方法**: `curl -sk -u admin:pass "https://<mgmt-ip>/api/storage/volumes?name=<vol>&fields=nas.security_style"`

### Active Directory 連携

`automated-response` スタックの SMB ユーザーブロック（name-mapping）は ONTAP SVM レベルで動作します。ドメイン ID（例: `CORP\jdoe`）で SMB ユーザーをブロックするには、SVM が Active Directory に参加している必要があります。

#### AD 参加: 検証済みデプロイ手順

1. **AD を作成または特定**（AWS Managed AD またはセルフマネージド）
2. **`demo-ad-environment.yaml` をデプロイ**（または既存 AD インフラを使用）
3. **`demo-ad-join-svm.sh` を実行**して SVM を AD に参加
4. **CIFS 共有を作成**（SMB アクセスに必要）

#### AD 参加: 重要な設定（ONTAP 9.17.1 で検証済み）

| 設定 | AWS Managed AD | セルフマネージド AD |
|------|---------------|-----------------|
| OU パス | `OU=Computers,OU=<ShortName>,DC=...` | `OU=Computers,DC=...` またはカスタム |
| FileSystemAdministratorsGroup | `Domain Admins` | `Domain Admins` または委任されたグループ |
| NetBIOS 名 | ドメイン ShortName と異なる値 | ドメイン内で一意 |
| ユーザー名 | `Admin` | 委任された権限を持つサービスアカウント |

**よくある失敗**: `FileSystemAdministratorsGroup` に `AWS Delegated FSx Administrators` を使用すると SVM が `MISCONFIGURED` 状態になります。`Domain Admins` を使用してください。

**AWS Managed AD の OU パス**: AWS Managed AD はドメインの短縮名で中間 OU を作成します。ドメイン `demo.fsx.local`（ShortName: `demo`）の場合、正しいパスは `OU=Computers,OU=demo,DC=demo,DC=fsx,DC=local` です。`OU=Computers,DC=demo,DC=fsx,DC=local` ではありません。

**MISCONFIGURED からの復旧**: `aws fsx update-storage-virtual-machine` を正しいパラメータで再実行できます。SVM の削除は不要です。

#### Windows EC2 ドメイン参加（CloudFormation）

`AWS::SSM::Association` で AWS 管理ドキュメント `AWS-JoinDirectoryServiceDomain` を使用してください。EC2 インスタンスの `SsmAssociations` プロパティや `aws:domainJoin` のカスタム SSM Document は使用しないでください。

検証済みパターンは `shared/templates/demo-ad-environment.yaml` を参照してください。

#### デモ環境の前提条件

`demo-ad-environment.yaml` をデプロイする前に、以下の VPC Endpoint が存在することを確認してください（プライベートサブネットの EC2 に SSM でアクセスするために必要）:

```bash
# 既存の SSM エンドポイントを確認
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=<vpc-id>" \
  --query 'VpcEndpoints[?contains(ServiceName,`ssm`)].ServiceName'

# 不足している場合は作成（サービスごとに1コマンド）:
for svc in ssm ssmmessages ec2messages; do
  aws ec2 create-vpc-endpoint --vpc-id <vpc-id> --vpc-endpoint-type Interface \
    --service-name com.amazonaws.<region>.$svc \
    --subnet-ids <subnet1>,<subnet2> --security-group-ids <sg-id> --private-dns-enabled
done
```

#### NFS ブロック: Export-Policy vs NACL

| メカニズム | 同一サブネット | 異なるサブネット | root クライアント | 効果タイミング |
|-----------|:-----------:|:------------:|:-----------:|:-------------:|
| Export-policy deny rule | ✅ 有効 | ✅ 有効 | ✅ root もブロック | 即時 |
| NACL deny rule | ❌ 無効 | ✅ 有効 | ✅ 全てブロック | 即時 |

多くの FSx for ONTAP デプロイメント（クライアントと FSx ENI が同一サブネット）では、**export-policy deny rule が確実なメカニズム**です。NACL はクライアントと FSx が異なるサブネットにある場合の多層防御としてのみ有用です。

### DNS / Route 53

Route 53 レコードを作成するスタックはありません。VPC Endpoint のプライベート DNS は AWS が自動処理します（PrivateDnsEnabled=true）。カスタム DNS 設定は不要です。

---

## トラブルシューティング

### スタックロールバック: "private-dns-enabled cannot be set"

**原因**: VPC に既存の同一サービスの VPC Endpoint がある。

**対処法**: 該当の `Create*Endpoint=false` パラメータを設定する。上記の VPC Endpoint 確認コマンドを使用。

### Lambda タイムアウト（ONTAP 管理 IP への接続）

**原因**: セキュリティグループが管理 IP への HTTPS (443) アウトバウンドを許可していない、または Lambda が管理 IP へのルートを持たないサブネットにいる。

**対処法**: SecurityGroupId が OntapMgmtIp:443 へのエグレスを許可していることを確認。SubnetIds が FSx と同じ VPC にあることを確認。

### Secrets Manager の AccessDeniedException

**原因**: (a) Secret ARN が変わっている（Secrets Manager は再作成時に新しいランダムサフィックスを割り当てる）、または (b) Secrets Manager の VPC Endpoint が利用できない。

**対処法**: 正確な ARN を確認: `aws secretsmanager describe-secret --secret-id <name> --query ARN`。正しい ARN でスタックを更新する。

### restore-verification: "existing ONTAP object storage server"

**原因**: 対象 SVM に ONTAP S3 サーバーがある。これは構造的な競合であり、リトライでは解決しない。

**対処法**: 別の SVM を使用するか、ONTAP S3 サーバーを削除する（データ損失がないか事前確認のこと）。

---

## Day 2: デプロイ後の検証と運用

デプロイ後、スタックが正常に動作していることを確認してください。

### 即時検証（1 時間以内）

| Path | Verification Step | Expected Result |
|------|-------------------|-----------------|
| 1 (Audit) | Perform a file operation on the audited share, wait 5–10 min | Logs appear in vendor platform (`source:fsxn` in Datadog) |
| 2 (Response) | Send `health_check` via SNS trigger | Lambda returns `"status": "healthy"` |
| 3 (Recovery) | Execute Step Functions with a test snapshot | Workflow completes with `verdict: clean` or `suspicious` |
| 4 (Classification) | Invoke Lambda with a test S3 AP ARN | DynamoDB table contains scan results |

### 継続的な監視

以下の CloudWatch メトリクスにアラームを設定してください。

| Metric | Alarm Condition | Action |
|--------|----------------|--------|
| Lambda Errors (all stacks) | > 0 for 5 minutes | Investigate via CloudWatch Logs |
| DLQ ApproximateNumberOfMessagesVisible | > 0 | Replay failed messages (see [DLQ Replay Runbook](runbooks/dlq-replay.md)) |
| Lambda Duration (audit poller) | > 80% of timeout | Increase LambdaTimeout or LambdaMemorySize |
| Step Functions ExecutionsFailed | > 0 | Check execution history in console |

### 定期レビュー（月次）

- **ProtectedAccountsExtra**: 自動ブロック除外アカウントの一覧をレビューする。サービスアカウントは時間とともに変化するため、古いエントリが蓄積するとインシデント対応の有効性が低下する
- **Secret ARN の有効性**: Secrets Manager のシークレットがローテーションまたは再作成された場合、ARN サフィックスが変わる。`aws secretsmanager describe-secret --secret-id <name> --query ARN` で確認
- **VPC Endpoint のコスト**: Interface EP のコストを確認し、不要になったものを削除する

---

## ロールバックとクリーンアップ

### 自動ロールバック

CloudFormation はデプロイ失敗時に自動的にロールバックします。スタック自体の手動介入は不要です。ただし:

- 失敗ポイント前に作成された VPC Endpoint はロールバックで**クリーンアップされます**
- `DeletionPolicy: Retain` の DynamoDB テーブルは残る可能性があります（`aws dynamodb list-tables` で確認）
- スタックが `ROLLBACK_COMPLETE` 状態になった場合、同名で再作成する前に削除が必要: `aws cloudformation delete-stack --stack-name <name>`

### 手動クリーンアップ（完全削除）

ベンダー固有のクリーンアップスクリプトまたは共有ユーティリティを使用します。

```bash
# Single vendor stack
bash integrations/<vendor>/scripts/cleanup.sh --all -y

# Shared stacks (delete in reverse deployment order)
aws cloudformation delete-stack --stack-name fsxn-content-classification
aws cloudformation delete-stack --stack-name fsxn-restore-verification
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl
aws cloudformation delete-stack --stack-name fsxn-automated-response
```

**運用に関する補足**: デプロイの逆順でスタックを削除してください。`automated-response` スタックは他のスタックが使用する VPC Endpoint を作成しており、先に削除すると他スタックの削除中に Secrets Manager アクセスが失われます（通常は無害ですがエラーログが生成されます）。

---

## 関連ドキュメント

- [前提条件とリソースデプロイ](prerequisites.md) — S3 バケット、監査ログ、S3 AP 作成
- [クイックスタート（最小テスト）](quick-start-minimum.md) — ログ配信の最速確認パス
- [Verified Recovery Point ガイド](verified-recovery-point-guide.md) — restore-verification の詳細
- [Automated Response ガイド](automated-response-guide.md) — インシデント対応の運用
- [マルチアカウントデプロイ](multi-account-deployment.md) — StackSets による組織展開
