# CI ポリシーと品質ゲート

## 現在の CI ジョブ

| Job | Tool | Blocking | Purpose |
|-----|------|----------|---------|
| lint-and-test | npm, pytest, cfn-lint | Yes | コード品質とテンプレート検証 |
| cfn-guard | CloudFormation Guard | No (continue-on-error) | CloudFormation 向け Policy-as-code |
| security-scan | Trivy, custom checks | Yes | 脆弱性およびシークレット検出 |
| markdown-links | markdown-link-check | No (continue-on-error) | ドキュメントリンクの整合性確認 |
| actionlint | actionlint | No (continue-on-error) | GitHub Actions ワークフロー構文チェック |

## 現在の適用状況

| Check | Current Mode | Target Mode |
|---|---|---|
| cfn-lint | Blocking | Blocking |
| cfn-guard | Non-blocking | Blocking on main after rule tuning |
| markdown-link-check | Non-blocking | Blocking with external-link ignore rules |
| actionlint | Non-blocking | Blocking |
| Trivy | Blocking for high/critical findings | Blocking |

## cfn-guard 導入ロードマップ

```
Phase 1 (current): continue-on-error: true
  - Observe rule violations
  - Identify false positives

Phase 2: Adjust rules
  - Suppress known false positives
  - Add integration-specific rule files

Phase 3: Blocking on main
  - Remove continue-on-error for main branch pushes
  - PRs must pass cfn-guard

Phase 4: Release gate
  - Release tags require full cfn-guard pass
  - No exceptions without documented waiver
```

## cfn-guard ルール構成

誤検知を減らすため、スコープ別にルールを整理しています:

```
guard/rules/
├── lambda-security.guard       # Common Lambda best practices
├── secrets-management.guard    # Secrets Manager and NoEcho rules
├── audit-poller.guard          # (planned) Scheduler + checkpoint patterns
├── webhook-handler.guard       # (planned) API Gateway + sync invocation
└── eventbridge-handler.guard   # (planned) EventBridge + SQS patterns
```

すべての Lambda 関数が直接 DLQ を必要とするわけではありません:
- **Audit poller**: Scheduler DLQ を使用（Lambda DLQ ではない）
- **EMS webhook**: API Gateway の同期呼び出し。失敗レスポンス + アラームが主要な対応手段
- **FPolicy handler**: SQS ソース側の DLQ が障害を処理

## セキュリティスキャンのカバレッジ

### Trivy（ファイルシステムスキャン）
- 依存関係の脆弱性検出（Python, Node.js）
- IaC 設定ミスの検出
- シークレットパターンの検出

### カスタムセキュリティチェック
- `.kiro/` ディレクトリが git で追跡されていないこと
- `docs/blog/` ディレクトリが git で追跡されていないこと
- `.env` ファイルが git で追跡されていないこと
- 個人ファイルパス（PEM 鍵、ユーザーディレクトリ）が含まれていないこと

### トークンパターンの取り扱い
本リポジトリには多数のサンプルトークンパターン（Datadog API キー、Splunk HEC トークン、Grafana API トークン）が含まれています。誤検知を避けるため:
- すべてのサンプルトークンは明らかにダミーの値を使用（例: `dd-api-key-placeholder`）
- 実際のトークンは AWS Secrets Manager にのみ保存
- CI は実際のトークンに見えるパターン（長さ、プレフィックス、エントロピー）をチェック

## Markdown リンクチェック

外部リンクはレート制限や一時的な障害により不安定な失敗を起こすことがあります。`.markdown-link-check.json` の設定:
- HTTP 429（レート制限）に対して最大 3 回リトライ
- `dev.to` リンクを無視（自動チェックで頻繁に 403 が発生するため）
- 20 秒のタイムアウトを使用
- ノンブロッキング（continue-on-error）として実行

CI でリンクチェックが失敗した場合:
1. リンクが実際に壊れているか確認（手動検証）
2. 不安定な場合: `.markdown-link-check.json` の `ignorePatterns` に追加
3. 壊れている場合: ソースドキュメントのリンクを修正

## 関連ドキュメント

- [セキュリティレビューチェックリスト](security-review-checklist.md)
- [ガバナンス・コンプライアンス](governance-and-compliance.md)
