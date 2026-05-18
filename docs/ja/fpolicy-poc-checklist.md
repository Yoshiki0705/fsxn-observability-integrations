# FPolicy PoC チェックリスト

## 目的

FPolicy ファイルアクティビティパイプラインの E2E 検証: ONTAP ファイル操作 → ECS Fargate → SQS → Lambda → Datadog

## 前提条件

- [ ] FSx for ONTAP ファイルシステムがデプロイ済み
- [ ] CIFS 対応 SVM に SMB 共有が1つ以上存在
- [ ] FSx ONTAP と同じ VPC のプライベートサブネット
- [ ] Fargate 用のエグレスパス: NAT Gateway または VPC エンドポイント（ECR, CloudWatch Logs, SQS）
- [ ] ECR リポジトリに FPolicy サーバーイメージ（`linux/amd64` でビルド）
- [ ] Datadog API キーが Secrets Manager に保存済み
- [ ] ONTAP fsxadmin 認証情報にアクセス可能

## PoC スコープ

### スコープ内

- SMB create イベントの Datadog 到着
- Fargate TCP リスナー接続性
- SQS → Lambda → Datadog シッピング
- Fargate タスク再起動と IP 更新復旧
- Datadog Log Explorer クエリ検証

### スコープ外

- 全操作の配信保証（async モードでの rename/delete）
- NFS 本番対応
- Multi-AZ HA 設計
- 高ボリュームパフォーマンスベンチマーク
- 監査ログの代替

## 成功基準

| 基準 | 目標 |
|------|------|
| Create イベントが Datadog に到着 | 30秒以内 |
| 再起動復旧 | 3分以内 |
| Lambda 処理時間 | イベントあたり 500ms 未満 |
| Lambda エラー | PoC 中 0 件 |

## 既知の制約（Go/No-Go 前に確認）

- [ ] rename/delete イベントは async モードで配信されない場合がある
- [ ] NFS は明示的なバージョン指定と慎重なテストが必要
- [ ] user フィールドが空になる操作がある
- [ ] Fargate タスク再起動中（~2分）のイベントロスの可能性
- [ ] FPolicy はイベント駆動 signal であり、完全な監査ログの代替ではない

## ロールバック手順

```bash
# 1. ONTAP で FPolicy を無効化
# vserver fpolicy disable -vserver <svm> -policy-name fpolicy_aws

# 2. AWS スタック削除
aws cloudformation delete-stack --stack-name fsxn-datadog-ems-fpolicy
aws cloudformation delete-stack --stack-name fsxn-fpolicy-server
```

## Go / No-Go 判断

| 質問 | 回答 |
|------|------|
| Create イベントが Datadog に到着したか？ | Yes/No |
| レイテンシはユースケースに許容可能か？ | Yes/No |
| 既知の制約は許容可能か？ | Yes/No |
| コストモデルを理解したか？ | Yes/No |
| 本番 HA 設計が特定されたか？ | Yes/No |
