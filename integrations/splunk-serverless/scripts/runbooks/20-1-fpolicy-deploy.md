# 20.1 FPolicy 共有テンプレートのデプロイ

## 概要

`shared/templates/fpolicy-apigw.yaml` を使用して FPolicy パス（ECS Fargate + SQS + EventBridge パターン）をデプロイする手順書。ONTAP が Fargate タスク IP の TCP:9898 に直接接続し、ファイル操作イベントを EventBridge カスタムバスに発行する。

## 前提条件

- AWS CLI v2 が設定済み（`ap-northeast-1` リージョン）
- VPC、サブネット、セキュリティグループが存在すること
- ECR に FPolicy サーバーイメージ（`v2-timeout-fix` タグ）がプッシュ済み
- FSx for ONTAP SVM のセキュリティグループが TCP:9898 のアウトバウンドを許可していること
- `CAPABILITY_NAMED_IAM` を使用可能であること

## アーキテクチャ概要

```
ONTAP FPolicy → TCP:9898 → ECS Fargate Task → SQS Queue → EventBridge Custom Bus
                                                              ↓
                                                    Lambda (Splunk HEC 送信)
```

**重要な設計ポイント:**
- ONTAP は Fargate タスク IP に直接接続（NLB 経由ではない）
- Fargate タスク IP はタスク再起動時に変更される
- FPolicy プロトコルは独自バイナリプロトコル（HTTP/HTTPS ではない）
- EventBridge カスタムバスの source: `fpolicy.fsxn`

## 手順

### Step 1: ECR イメージの確認

```bash
# ECR リポジトリのイメージ一覧を確認
aws ecr describe-images \
  --repository-name fpolicy-server \
  --region ap-northeast-1 \
  --query 'imageDetails[?contains(imageTags, `v2-timeout-fix`)].[imageTags, imagePushedAt]' \
  --output table
```

**確認ポイント:**
- `v2-timeout-fix` タグのイメージが存在すること
- イメージアーキテクチャが `linux/arm64` であること（ARM64 Fargate 用）

### Step 2: テンプレートの確認

```bash
# テンプレートの存在確認
ls -la shared/templates/fpolicy-apigw.yaml

# cfn-lint でテンプレートを検証
cfn-lint shared/templates/fpolicy-apigw.yaml
```

### Step 3: CloudFormation スタックのデプロイ

```bash
# FPolicy スタックのデプロイ
aws cloudformation deploy \
  --template-file shared/templates/fpolicy-apigw.yaml \
  --stack-name fsxn-fp-srv \
  --region ap-northeast-1 \
  --parameter-overrides \
    ComputeType=fargate \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    FsxnSvmSecurityGroupId=<sg-id> \
    ContainerImage=123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/fpolicy-server:v2-timeout-fix \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

### Step 4: スタックステータスの確認

```bash
# スタックステータスを確認
aws cloudformation describe-stacks \
  --stack-name fsxn-fp-srv \
  --region ap-northeast-1 \
  --query 'Stacks[0].StackStatus' \
  --output text
```

**期待される出力:** `CREATE_COMPLETE` または `UPDATE_COMPLETE`

### Step 5: ECS Fargate タスク設定の確認

```bash
# ECS サービスの確認
aws ecs describe-services \
  --cluster fsxn-fpolicy-cluster \
  --services fsxn-fpolicy-service \
  --region ap-northeast-1 \
  --query 'services[0].{Status: status, RunningCount: runningCount, DesiredCount: desiredCount}'

# タスク定義の確認
aws ecs describe-task-definition \
  --task-definition fsxn-fpolicy-task \
  --region ap-northeast-1 \
  --query 'taskDefinition.{Cpu: cpu, Memory: memory, RuntimePlatform: runtimePlatform}'
```

**期待される設定:**
| 項目 | 期待値 |
|------|--------|
| CPU | 256 (.25 vCPU) |
| Memory | 512 MB |
| Architecture | ARM64 |
| OS Family | LINUX |

### Step 6: Fargate タスク IP の取得

```bash
# 実行中のタスク ARN を取得
TASK_ARN=$(aws ecs list-tasks \
  --cluster fsxn-fpolicy-cluster \
  --service-name fsxn-fpolicy-service \
  --region ap-northeast-1 \
  --query 'taskArns[0]' \
  --output text)

# タスクの ENI 情報からプライベート IP を取得
aws ecs describe-tasks \
  --cluster fsxn-fpolicy-cluster \
  --tasks "$TASK_ARN" \
  --region ap-northeast-1 \
  --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' \
  --output text
```

**注意:** この IP アドレスは ONTAP FPolicy 外部エンジンの `primary-servers` に設定する値。タスク再起動時に変更される。

### Step 7: EventBridge カスタムバスの確認

```bash
# カスタムイベントバスの確認
aws events describe-event-bus \
  --name fpolicy-fsxn-bus \
  --region ap-northeast-1

# イベントルールの確認
aws events list-rules \
  --event-bus-name fpolicy-fsxn-bus \
  --region ap-northeast-1
```

**確認ポイント:**
- カスタムバスが存在すること
- source: `fpolicy.fsxn` のルールが設定されていること

### Step 8: SQS キューの確認

```bash
# SQS キューの確認
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-northeast-1.amazonaws.com/123456789012/fsxn-fpolicy-events \
  --attribute-names All \
  --region ap-northeast-1
```

### Step 9: セキュリティグループの確認

```bash
# Fargate タスクのセキュリティグループで TCP:9898 インバウンドが許可されていることを確認
aws ec2 describe-security-groups \
  --group-ids <fargate-sg-id> \
  --region ap-northeast-1 \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`9898`]'
```

**確認ポイント:**
- TCP:9898 のインバウンドが FSx for ONTAP SVM のセキュリティグループから許可されていること

## 検証チェックリスト

- [ ] ECR に `v2-timeout-fix` タグのイメージが存在する
- [ ] `shared/templates/fpolicy-apigw.yaml` が cfn-lint を通過
- [ ] CloudFormation スタックステータスが `CREATE_COMPLETE`
- [ ] ECS Fargate タスクが ARM64, 256 CPU, 512 MB で設定されている
- [ ] Fargate タスクが Running 状態
- [ ] Fargate タスクのプライベート IP が取得できた
- [ ] EventBridge カスタムバス（source: `fpolicy.fsxn`）が存在する
- [ ] SQS キューが作成されている
- [ ] セキュリティグループで TCP:9898 が許可されている

## トラブルシューティング

### ECS タスクが起動しない

- **原因**: ECR イメージの取得失敗、リソース不足
- **解決**: ECS イベントログを確認: `aws ecs describe-services --cluster ... --query 'services[0].events[:5]'`

### Fargate タスクが STOPPED になる

- **原因**: コンテナのヘルスチェック失敗、OOM
- **解決**: CloudWatch Logs でコンテナログを確認

### セキュリティグループで接続が拒否される

- **原因**: TCP:9898 のインバウンドルールが不足
- **解決**: Fargate タスクの SG に FSx for ONTAP SVM SG からの TCP:9898 を許可

### EventBridge カスタムバスが作成されない

- **原因**: テンプレートの EventBridge リソース定義に問題
- **解決**: CloudFormation イベントでエラー詳細を確認

## 関連タスク

- Task 20.2: Splunk 向け FPolicy 受信 Lambda の作成
- Task 20.3: ONTAP FPolicy 外部エンジン設定
- Task 20.4: FPolicy ファイル操作テスト
