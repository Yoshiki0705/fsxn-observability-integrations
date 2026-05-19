# Glossary / 用語集

| English | 日本語 | Description |
|---------|--------|-------------|
| Telemetry pipeline | テレメトリーパイプライン | The flow of collecting, processing, and sending data |
| Receiver | レシーバー | Component that receives data into the Collector |
| Processor | プロセッサー | Component that processes data within the Collector |
| Exporter | エクスポーター | Component that sends data from the Collector to backends |
| Semantic conventions | セマンティック規約 | Standard naming rules for attribute names and values |
| Resource attributes | リソース属性 | Attributes that identify the source of telemetry |
| Log attributes | ログ属性 | Attributes attached to individual log records |
| Routing layer | ルーティング層 | Layer that determines data delivery destinations |
| Fan-out | ファンアウト | Distributing a single input to multiple outputs |
| Backpressure | バックプレッシャー | Control mechanism when downstream capacity is exceeded |
| Sending queue | 送信キュー | Buffering mechanism within exporters |
| Wire format | ワイヤーフォーマット | Data transmission format on the network |
| Direct send | ダイレクト送信 | Pattern of sending directly to backends without a Collector |
| Vendor lock-in | ベンダーロックイン | State of dependency on a specific vendor |
