# 最小テストパス

🌐 **日本語**（このページ） | [English](../en/quick-start-minimum.md)

最もシンプルな構成で監査イベントを Datadog に送信します。

## 必要なもの

- FSx for ONTAP ファイルシステム（監査ログ有効化済み）
- FSx for ONTAP S3 Access Point（audit volume にアタッチ済み）
- Datadog アカウント（無料トライアル可）
- Secrets Manager に保存した Datadog API Key

## 最小構成

| 設定 | 値 | 理由 |
|---------|-------|-----|
| Lambda VPC | VPC 外 | NAT Gateway 不要 |
| Scheduler | rate(5 minutes) | デフォルト |
| Audit rotation | 5分間隔（時間ベース） | ローテーションファイルが素早く出現 |
| Datadog site | 使用サイト（例: ap1.datadoghq.com） | — |

## 手順

```bash
# 1. デプロイ（1コマンド）
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=<your-fsx-s3-ap-arn> \
    DatadogApiKeySecretArn=<your-secret-arn> \
    DatadogSite=<your-site> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <your-region>

# 2. 監査対象共有でテストファイル操作を実行
#    （SMB または NFS でファイルを作成/削除）

# 3. 5-10分待機

# 4. Datadog で確認
#    検索: source:fsxn
```

## 成功基準

- [ ] Datadog Log Explorer で `source:fsxn` が1件以上返る
- [ ] `@attributes.operation` が入力されている
- [ ] `@attributes.user` が入力されている

## 最小テストに含まれないもの

- VPC / NAT Gateway 設定
- DLQ リプレイ手順
- カスタムメトリクス
- Datadog Monitor
- マルチ SVM / マルチアカウント

これらは本番強化ステップであり、完全なドキュメントでカバーされています。

## 次のステップ

ログ到着確認後:
1. [フィールドマッピング](../../integrations/datadog/docs/ja/field-mapping.md)を確認
2. [調査クエリ](../../integrations/datadog/docs/ja/field-mapping.md#datadog-検索クエリ)を試す
3. Monitor を設定（ブログシリーズ Part 3）
