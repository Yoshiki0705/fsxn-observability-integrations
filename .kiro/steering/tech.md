# 技術スタック

## Infrastructure

- **CloudFormation (YAML)**: メインの IaC ツール。各ベンダー統合は独立したテンプレート
- **CDK (TypeScript)**: 複雑なリソース構成が必要な場合のみ使用
- **SAM**: Lambda のローカルテスト用

## Lambda ランタイム

### Python 3.12 (ログ処理)
- FSx ONTAP 監査ログのパース（EVTX/JSON）
- ベンダー API へのログ配信
- 共通 Lambda Layer として提供

### TypeScript (API 連携)
- 設定管理、オーケストレーション
- CDK コンストラクト

## AWS サービス

- **S3 Access Points**: 監査ログアクセス制御
- **EventBridge**: イベントルーティング
- **Lambda**: ログ変換・配信
- **Kinesis Data Firehose**: 大量ログのバッファリング配信
- **Secrets Manager**: API キー管理
- **CloudWatch**: 監視・アラート
- **SQS**: Dead Letter Queue
- **X-Ray**: 分散トレーシング

## テスト

- **Jest**: TypeScript ユニットテスト
- **pytest**: Python ユニットテスト
- **cfn-lint**: CloudFormation テンプレート検証

## CI/CD

- **GitHub Actions**: PR チェック、デプロイパイプライン
- **ワークフロー**: lint → test → validate-cfn → deploy (staging) → deploy (prod)

## コーディング規約

- Python: PEP 8、型ヒント必須、docstring (Google style)
- TypeScript: strict mode、ESLint + Prettier
- YAML: 2スペースインデント
- コミットメッセージ: Conventional Commits
