# 用語集 / Glossary

| English | 日本語 | 説明 |
|---------|--------|------|
| Telemetry pipeline | テレメトリーパイプライン | データの収集・処理・送信の流れ |
| Receiver | レシーバー | Collector がデータを受信するコンポーネント |
| Processor | プロセッサー | Collector 内でデータを処理するコンポーネント |
| Exporter | エクスポーター | Collector からバックエンドにデータを送信するコンポーネント |
| Semantic conventions | セマンティック規約 | 属性名や値の標準的な命名規則 |
| Resource attributes | リソース属性 | テレメトリーの発生元を識別する属性 |
| Log attributes | ログ属性 | 個々のログレコードに付与される属性 |
| Routing layer | ルーティング層 | データの配信先を決定する層 |
| Fan-out | ファンアウト | 1つの入力を複数の出力に分配すること |
| Backpressure | バックプレッシャー | 下流の処理能力を超えた場合の制御機構 |
| Sending queue | 送信キュー | エクスポーター内のバッファリング機構 |
| Wire format | ワイヤーフォーマット | ネットワーク上でのデータ伝送形式 |
| Direct send | ダイレクト送信 | Collector を経由せず直接バックエンドに送信するパターン |
| Vendor lock-in | ベンダーロックイン | 特定ベンダーへの依存状態 |
