# Elastic セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Elasticsearch Bulk API で配信し、Kibana で可視化するセットアップ手順です。

## 前提条件

- Elastic Cloud または自己ホスト Elasticsearch クラスタ
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Elasticsearch API Key の作成

```bash
# Elastic Cloud の場合: Kibana → Stack Management → API Keys → Create
aws secretsmanager create-secret \
  --name "elastic/fsxn-api-key" \
  --secret-string '{"api_key":"YOUR_ENCODED_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/elastic/template.yaml \
  --stack-name fsxn-elastic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    ElasticApiKeySecretArn=arn:aws:secretsmanager:...:secret:elastic/fsxn-api-key-XXXXX \
    ElasticEndpoint=https://my-cluster.es.ap-northeast-1.aws.found.io:9243 \
    S3BucketName=$BUCKET_NAME \
    IndexPrefix=fsxn-audit \
  --capabilities CAPABILITY_IAM
```

## Step 3: Kibana 設定

### Index Pattern 作成
1. Kibana → **Stack Management** → **Index Patterns**
2. Pattern: `fsxn-audit-*`
3. Time field: `@timestamp`

### Discover で確認
- フィルタ: `fsxn.operation: ReadData`
- 時間範囲: Last 1 hour

### ダッシュボード例
- 操作別円グラフ: `fsxn.operation.keyword`
- ユーザー別棒グラフ: `user.name.keyword`
- 失敗アクセスタイムライン: `fsxn.result: Failure`

## インデックス管理

日次インデックス `fsxn-audit-YYYY.MM.DD` が自動作成されます。ILM (Index Lifecycle Management) で自動削除を設定:

```json
PUT _ilm/policy/fsxn-audit-policy
{
  "policy": {
    "phases": {
      "hot": {"actions": {"rollover": {"max_age": "30d"}}},
      "delete": {"min_age": "90d", "actions": {"delete": {}}}
    }
  }
}
```

## フォレンジック調査 (Kibana Discover/Lens)

> 🔍 ユーザー/IP/パス中心の調査ワークフロー（誰が、どこから、何にアクセスし、何をしたか — DII Storage Workload Security の Forensics ダッシュボードに類似）が必要な場合、[正規化イベントスキーマ](../../../docs/en/normalized-event-schema.md) で ONTAP audit / FPolicy フィールドは既に ECS（`user.name`、`source.ip`、`file.path`、`event.action`）へマッピングされているため、カスタムマッピングは不要です。Kibana で以下を構築してください:

### 保存検索 (KQL)

| 調査ビュー | KQL クエリ | DII SWS の対応ビュー |
|-----------|-----------|----------------------|
| User Overview | `user.name: "<value>"` | Forensic User Overview |
| All Activity | `event.dataset: "fsxn"`（フィルタなし、`@timestamp` 降順） | Forensics - All Activity |
| IP 中心ドリルダウン | `source.ip: "<value>"` | Forensic User Activity Data |
| エンティティ/ファイル履歴 | `file.path: "<value>"` | Forensic Entities Page |

それぞれを分かりやすい名前（例: `fsxn-forensics-user-overview`）で Kibana の **Saved Search** として保存すれば、調査担当者はクエリを作り直さずに Discover から適切なビューを選択できます。

### Lens ビジュアライゼーション

現在フィルタ中の保存検索に対して `event.action`（操作種別）を集計する **Lens** バーチャートを追加してください — DII SWS の Forensics ダッシュボードがユーザー/エンティティごとのアクション分布を表示するのと同じ方法で、異常なアクションの偏り（例: 削除操作の急増）を可視化できます。

### エクスポート

Discover の **Share → CSV Reports**（新しい Kibana では **Generate CSV**）で、選択した時間範囲に絞った現在のフィルタビューをエクスポートできます — DII SWS の 31 日フィルタ付き CSV エクスポート相当ですが、31 日固定の上限はありません（保持期間は上記 ILM ポリシーで管理されます）。

この実装が対応する CSF 2.0 機能全体のカバレッジ、および既知のデータソース上の注意点（FPolicy と audit log のカバレッジ差異、[データ分類ガイド](../../../docs/en/data-classification.md) 経由の PII 取り扱い）については [サイバーレジリエンス機能マップ](../../../docs/ja/cyber-resilience-capability-map.md#respond対応) を参照してください。
