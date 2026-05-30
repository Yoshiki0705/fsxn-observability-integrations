# アーキテクチャ

## 全体構成

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FSx for ONTAP                                    │
├─────────────────┬──────────────────┬────────────────────────────────────┤
│  監査ログ        │  EMS イベント     │  FPolicy ファイル操作通知            │
│  (EVTX/XML)     │  (ARP, Quota等)  │  (create/write/rename/delete)      │
└────────┬────────┴────────┬─────────┴──────────────┬─────────────────────┘
         │                  │                         │
         ▼                  ▼                         ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐
│ S3 Access Point │  │ EMS Webhook  │  │ FPolicy TCP:9898                 │
│ + EventBridge   │  │ (HTTPS POST) │  │ (proprietary binary protocol)    │
│   Scheduler     │  │              │  │                                  │
└────────┬────────┘  └──────┬───────┘  └──────────────┬───────────────────┘
         │                  │                          │
         ▼                  ▼                          ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐
│ Lambda          │  │ API Gateway  │  │ ECS Fargate                      │
│ (ログパース・配信) │  │ → Lambda     │  │ (FPolicy Server → SQS → Lambda)  │
└────────┬────────┘  └──────┬───────┘  └──────────────┬───────────────────┘
         │                  │                          │
         └──────────────────┼──────────────────────────┘
                            ▼
                 ┌──────────────────────┐
                 │  Observability       │
                 │  Vendor API          │
                 │  (Datadog, Splunk等)  │
                 └──────────────────────┘
```

## 3つのテレメトリパス

本プロジェクトは ONTAP の3つのテレメトリソースに対応します:

### パス 1: 監査ログ（S3 AP + EventBridge Scheduler）
```
ONTAP 監査ログ → S3 Access Point → EventBridge Scheduler → Lambda → Vendor API
```
- **用途**: コンプライアンス向けファイルアクセス履歴
- **レイテンシ**: ニアリアルタイム（Scheduler 間隔依存、通常5分）
- **形式**: EVTX / XML

### パス 2: EMS イベント（Webhook）
```
ONTAP EMS → Webhook (HTTPS) → API Gateway → Lambda → Vendor API
```
- **用途**: ARP ランサムウェア検知、クォータ超過、HA フェイルオーバー等
- **レイテンシ**: リアルタイム（~30秒）
- **形式**: JSON

### パス 3: FPolicy ファイル操作（ECS Fargate）
```
ONTAP FPolicy → ECS Fargate (TCP:9898) → SQS → Lambda → Vendor API
```
- **用途**: リアルタイムファイル操作監視（create, write, rename, delete）
- **レイテンシ**: リアルタイム（~6-8秒）
- **形式**: FPolicy バイナリプロトコル → JSON 正規化
- **注意**: FPolicy は独自バイナリプロトコルのため Lambda 不可、ECS Fargate が必要

> **本シリーズにおける「サーバーレス」の意味**: サーバー管理や差別化されないコレクター運用を最小化すること — 全てを Lambda に押し込むことではありません。FPolicy は永続的な TCP リスナーが必要なため ECS Fargate（サーバーレスコンテナ）を使用し、イベントのデカップリングには SQS、短時間処理には Lambda を使用します。各 AWS サービスはその運用特性に応じて選択しています。

## ONTAP テレメトリソース選択ガイド

| 要件 | 最適ソース | レイテンシ |
|------|-----------|----------|
| コンプライアンス向けファイルアクセス履歴 | 監査ログ | ニアリアルタイム（Scheduler 間隔依存） |
| ランサムウェア検知 | ARP via EMS | リアルタイム（webhook） |
| イベント駆動ファイル操作詳細 | FPolicy | イベント駆動（TCP） |
| 運用アラート（クォータ、HA、ボリューム満杯） | EMS | リアルタイム（webhook） |
| ベンダーニュートラルパイプライン | OpenTelemetry | 構成依存 |

## コンポーネント詳細

### 1. FSx for ONTAP 監査ログ

FSx for ONTAP の監査ログ機能を有効化し、SVM 内の audit volume に出力します。

- **ログ形式**: EVTX (Windows Event Log) または XML
- **出力先**: SVM 内の audit volume（`vserver audit create -destination /audit_log`）
- **ログ内容**: ファイルアクセス（SMB/NFS）、認証イベント
- **アクセス方式**: FSx for ONTAP S3 Access Point 経由で S3 API としてアクセス

> **重要**: 監査ログは FSx ボリューム上に保存されます。S3 バケットには書き込まれません。Lambda は FSx for ONTAP S3 Access Point を通じて S3 API でログファイルを読み取ります。

### 2. FSx for ONTAP S3 Access Point

FSx for ONTAP ボリュームにアタッチされる S3 Access Point です。

- **目的**: Lambda が NFS/SMB マウントなしで監査ログを読み取るためのアクセス境界
- **特性**: データは FSx ファイルシステム上に残り、S3 API でアクセス可能
- **制約**: S3 Event Notifications / EventBridge 通知は非対応
- **VPC 制約**: Internet-origin S3 AP の場合、VPC 内 Lambda + Gateway Endpoint のみではタイムアウト（NAT Gateway または VPC-origin AP が必要）

### 3. トリガー方式

FSx for ONTAP S3 Access Points は S3 イベント通知をサポートしないため、EventBridge Scheduler による定期起動を使用します。

**EventBridge Scheduler + チェックポイント**
- EventBridge Scheduler が Lambda を定期的に起動（例: 5分間隔）
- Lambda は前回処理済みファイルをチェックポイント（DynamoDB）で管理
- 新しくローテーションされたログファイルのみを処理

### 4. Lambda 関数

監査ログを取得・パースし、各ベンダーの API へ配信します。

- **ランタイム**: Python 3.12
- **処理フロー**:
  1. FSx for ONTAP S3 Access Point 経由でログファイル一覧取得
  2. チェックポイントと比較し、未処理ファイルを特定
  3. EVTX/XML パース
  4. ベンダー固有フォーマットへ変換
  5. API エンドポイントへバッチ送信
  6. 失敗時リトライ（exponential backoff）
  7. チェックポイント更新

### 5. 代替パターン: Kinesis Data Firehose

大量ログの場合、Firehose 経由で直接ベンダーへ配信します。

```
FSx S3 AP → Lambda (変換) → Kinesis Data Firehose → ベンダー API
```

- **利点**: 自動バッファリング、リトライ、スケーリング
- **対応ベンダー**: Splunk (HEC), Datadog, New Relic, HTTP エンドポイント全般

### 6. AWS ネイティブ代替案との比較

| 方式 | 最適用途 | トレードオフ |
|------|---------|------------|
| Lambda → ベンダー API 直接 | ベンダー固有マッピング、EVTX/XML パース | カスタムリトライ/バックオフが必要 |
| Kinesis Data Firehose | マネージドバッファリング | 変換の柔軟性に制限 |
| CloudWatch Logs 経由 | AWS ネイティブ運用優先 | 外部ツールへの追加ルーティングが必要 |
| SQS バッファ（パーサーとシッパー間） | 疎結合、バックプレッシャー対応 | コンポーネント数が増加 |
| OpenTelemetry Collector | ベンダーニュートラル標準 | スキーマ/マッピング設計が必要 |
| Security Lake / OCSF | セキュリティ分析、長期保存 | OCSF スキーマへの変換が必要 |

本プロジェクトでは Lambda → ベンダー API 直接方式を採用。理由:
- EVTX/XML パースにフル制御が必要
- ベンダー固有の API セマンティクス（バッチサイズ、認証、リトライ）に対応
- AWS ネイティブロギングを優先する場合、CloudWatch Logs や S3 アーカイブを並列出力として追加可能

## セキュリティ設計

### IAM 最小権限

```yaml
# Lambda 実行ロール
- s3:GetObject (FSx for ONTAP S3 Access Point ARN のみ)
- s3:ListBucket (FSx for ONTAP S3 Access Point ARN のみ)
- secretsmanager:GetSecretValue (API Key Secret のみ)
- dynamodb:GetItem, dynamodb:PutItem (チェックポイントテーブルのみ)
- logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
```

### シークレット管理

- API キーは AWS Secrets Manager に保存
- Lambda 環境変数には ARN のみ設定
- KMS カスタマーマネージドキーで暗号化推奨

### ネットワーク

- FSx for ONTAP S3 Access Point へのアクセスは NAT Gateway 経由（VPC 内配置時）
- **注意**: Internet-origin S3 AP は VPC 内から Gateway Endpoint のみではアクセス不可（NAT Gateway 必要）
- Lambda を VPC 外に配置する場合は問題なくアクセス可能（推奨: 読み取り専用の場合）
- セキュリティグループで最小限のアウトバウンドのみ許可

## 監視・アラート

- **CloudWatch Metrics**: Lambda エラー率、実行時間、スロットリング
- **CloudWatch Alarms**: 配信失敗率閾値超過時に SNS 通知
- **Dead Letter Queue**: 処理失敗イベントを SQS DLQ に退避
- **X-Ray**: 分散トレーシングによるボトルネック特定
