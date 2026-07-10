# 配信保証パターン

🌐 **日本語**（このページ） | [English](../en/delivery-guarantees.md)

本ドキュメントでは、全ベンダー統合で利用可能な配信保証のティアを説明します。信頼性要件と運用複雑度のバランスに応じて適切なティアを選択してください。

## 判断マトリクス

| ティア | 配信保証 | 複雑度 | コスト | 用途 |
|--------|---------|--------|--------|------|
| Quickstart | At-least-once | 低 | Lambda のみ | PoC、開発、低ボリューム本番 |
| Medium | At-least-once + リプレイ | 中 | Lambda + SQS DLQ | 運用手順書付き本番 |
| Higher reliability | At-least-once + バッファリング | 高 | Lambda + SQS + DynamoDB | 高ボリューム、厳格な SLA |
| Multi-backend | At-least-once + ルーティング | 高 | Collector コンピュート | 複数送信先、エンリッチメント、リダクション |

## Tier 1: Quickstart（本プロジェクトのデフォルト）

```
EventBridge Scheduler → Lambda → Vendor API
                    ↓ (失敗時)
              Scheduler DLQ
```

**構成要素**:
- Lambda からベンダー API への直接送信
- EventBridge Scheduler リトライポリシー（2回リトライ、1時間イベント保持）
- Scheduler DLQ（失敗した呼び出しの保持）
- SSM Parameter Store ハイウォーターマーク チェックポイント
- Lambda reserved concurrency = 1（重複実行防止）
- 処理上限（MAX_KEYS_PER_RUN, SAFETY_THRESHOLD_MS）

**配信セマンティクス**: At-least-once。Lambda が送信に成功したがチェックポイント更新前に失敗した場合、次回実行で再処理されます。重複は稀ですが発生し得ます。

**障害ハンドリング**:
- ベンダー API の一時的エラー → Lambda が指数バックオフでリトライ（1回の呼び出しで最大3回）
- Lambda タイムアウト → Scheduler DLQ に失敗イベントが保持され、次回スケジュール実行でチェックポイントからリトライ
- 永続的な障害 → Scheduler DLQ に蓄積、オペレーターが調査

**制限事項**:
- オブジェクト単位のリトライ追跡なし（poison-pill ファイルが後続ファイルをブロック）
- ベンダー障害時のバッファリングなし（Scheduler リトライウィンドウに依存）
- 単一同時実行によるスループット制限

## Tier 2: Medium Volume（リプレイ付き本番）

```
EventBridge Scheduler → Lambda → Vendor API
                    ↓ (失敗時)
              Scheduler DLQ
              Lambda failure destination → SQS
                                           ↓
                                    リプレイ手順書
```

**追加構成要素**:
- Lambda failure destination（非同期呼び出し失敗 → SQS）
- 運用リプレイ手順書（手動または自動 DLQ ドレイン）
- パイプラインヘルス CloudWatch アラーム
- Poison-pill 検出（リトライ回数追跡）

**Quickstart からのアップグレード条件**:
- 個別オブジェクトの処理失敗を可視化する必要がある
- ベンダー API に1時間超のメンテナンスウィンドウがある
- 監査コンプライアンスで配信証明またはリトライ記録が必要

**実装ノート**:
- Lambda failure destination を追加し、非同期呼び出し失敗をキャプチャ
- DynamoDB または SSM タグでオブジェクト単位のリトライ回数を追跡
- N回失敗後の poison-pill 隔離を実装
- Scheduler DLQ 深度、Lambda エラー、チェックポイント経過時間に CloudWatch アラームを設定

## Tier 3: Higher Reliability（SQS バッファリング）

```
EventBridge Scheduler → Lambda (reader) → SQS バッファ
                                              ↓
                                    Lambda (shipper) → Vendor API
                                              ↓ (失敗時)
                                           SQS DLQ
```

**追加構成要素**:
- Reader と Shipper Lambda 間の SQS キュー
- オブジェクト単位チェックポイント台帳（DynamoDB）
- DynamoDB conditional writes による重複排除
- SQS DLQ と自動リプレイ
- 並行 Shipper Lambda（SQS event source mapping）

**Medium からのアップグレード条件**:
- 高イベントボリューム（>1000 ファイル/時）
- ベンダー API に厳格なレート制限がありバックプレッシャーが必要
- 重複排除付き並行処理が必要
- ベンダー長時間障害時のバッファリングが必要

**実装ノート**:
- Reader Lambda がファイルを一覧し、S3 キーを SQS にエンキュー
- Shipper Lambda がメッセージごとに1キーを処理（SQS event source mapping）
- DynamoDB でオブジェクト単位の状態を追跡: PENDING → IN_PROGRESS → COMPLETE
- Conditional writes で重複処理を防止
- SQS visibility timeout > Lambda timeout
- Batch size = 1（オブジェクト単位のエラー分離）

## Tier 4: Multi-Backend / エンリッチメント / リダクション

```
EventBridge Scheduler → Lambda (reader) → OTel Collector / Grafana Alloy
                                              ↓
                                    複数バックエンド
                                    (Grafana + Datadog + S3 アーカイブ)
```

**追加構成要素**:
- OTel Collector または Grafana Alloy（ECS/EC2）
- Persistent queue（Collector ファイルベースキュー）
- ルーティング、フィルタリング、エンリッチメント プロセッサ
- マルチバックエンド ファンアウト

**使用条件**:
- 複数の Observability バックエンドへの同時配信
- ログエンリッチメント（メタデータ追加、ID 解決）
- リダクション（PII 除去）
- ルーティング（異なるログを異なるバックエンドへ）
- ベンダー移行（段階的カットオーバー）

**参考**: [Part 5 — OTel Collector](https://dev.to/aws-builders/escape-vendor-lock-in-multi-backend-log-delivery-with-otel-collector-for-fsx-for-ontap) で Collector ベースアーキテクチャの詳細を参照。

## チェックポイント戦略

| 戦略 | ストレージ | 同時実行 | 重複排除 | 複雑度 |
|------|-----------|---------|---------|--------|
| SSM ハイウォーターマーク | SSM Parameter Store | 単一（reserved=1） | 辞書順 | 低 |
| DynamoDB オブジェクト台帳 | DynamoDB | 複数ワーカー | Conditional writes | 中 |
| SQS メッセージ重複排除 | SQS FIFO | 複数ワーカー | Message dedup ID | 中 |

### SSM ハイウォーターマーク（Quickstart）

最後に正常処理された S3 キーを保存します。次回実行時はその値以降のキーを一覧取得します。シンプルで無料（SSM 制限内）ですが、単調増加するキーと単一同時実行が必要です。

### DynamoDB オブジェクト台帳（Production）

Conditional writes によるオブジェクト単位の処理状態を保存します:

```python
table.put_item(
    Item={"object_key": key, "etag": etag, "status": "IN_PROGRESS", "ttl": ...},
    ConditionExpression="attribute_not_exists(object_key)"
)
```

並行ワーカー、重複排除、リトライ追跡、poison-pill 検出をサポートします。

## 一般的な障害シナリオ

| シナリオ | Quickstart の動作 | 本番推奨 |
|---------|------------------|----------|
| ベンダー API 5xx | Lambda が3回リトライ → 失敗 → 次回実行でチェックポイントからリトライ | 長時間障害に備え SQS バッファを追加 |
| ベンダー API 429 | Lambda がバックオフ付きリトライ → タイムアウトの可能性 | MAX_KEYS_PER_RUN を削減; バックプレッシャー用に SQS を追加 |
| 不正な監査ファイル | パースエラー → チェックポイント停滞 | N回リトライ後の poison-pill 隔離 |
| Lambda タイムアウト | 最後に成功したキーでチェックポイント | MAX_KEYS_PER_RUN を削減またはタイムアウトを延長 |
| 認証情報ローテーション | コールドスタートまで 401/403 | reload-on-401/403 付き auth_cache を使用 |
| Scheduler スロットル | DLQ がイベントをキャプチャ | 次回スケジュール実行でギャップをカバー |

## 障害オーナーシップマトリクス

異なる障害タイプは異なるレイヤーが所有します。この分離を理解することで運用責任の割り当てが明確になります:

| 障害 | オーナーレイヤー | Quickstart の動作 | 本番オプション |
|------|----------------|------------------|---------------|
| Scheduler が Lambda を起動できない | EventBridge Scheduler | リトライ + Scheduler DLQ | DLQ アラーム + リプレイ手順書 |
| Lambda が処理中にクラッシュ | Lambda ランタイム | チェックポイント未更新; 次回実行でリトライ | Lambda failure destination → SQS |
| ベンダー API が 429/5xx を返す | Shipper リトライロジック | 3回リトライ後に raise | SQS バッファリングまたは Collector パス |
| 1ファイルが繰り返しパース失敗 | アプリケーションロジック | チェックポイント進行停止 | DynamoDB poison-pill 台帳 |
| 認証情報の期限切れ/ローテーション | Auth cache レイヤー | キャッシュ更新まで 401/403 | reload-on-401/403 付き auth_cache.py |
| Lambda 同時実行数の枯渇 | Lambda サービス | スロットル; Scheduler DLQ | ReservedConcurrency=1 では想定内 |

## パイプラインヘルス監視

全ティアで監視すべき項目:

| シグナル | メトリクス | アラーム閾値 |
|---------|-----------|-------------|
| Scheduler DLQ 深度 | SQS `ApproximateNumberOfMessagesVisible` | > 0 |
| Lambda エラー | Lambda `Errors` | > 0 |
| Lambda スロットル | Lambda `Throttles` | > 0 |
| Lambda 実行時間 | Lambda `Duration` p95 | > タイムアウトの80% |
| チェックポイント経過時間 | カスタムメトリクス | > スケジュール間隔の2倍 |
| ベンダー送信失敗 | カスタムメトリクス | > 0 |

ベンダー固有の `docs/en/operations.md` で CloudWatch アラームの例を参照してください。
