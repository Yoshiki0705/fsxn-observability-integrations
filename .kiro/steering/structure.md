# ディレクトリ構造と命名規約

## ディレクトリ構造

```
fsxn-observability-integrations/
├── README.md                    # バイリンガル（日英切替）
├── docs/                        # プロジェクト全体ドキュメント
│   ├── ja/                      # 日本語
│   ├── en/                      # 英語
│   └── images/                  # 共通画像
├── shared/                      # 共通モジュール
│   ├── lambda-layers/           # 共通 Lambda Layer
│   │   ├── log-parser/          # FSx ONTAP ログパーサー
│   │   └── s3ap-reader/         # S3 AP 読み取りユーティリティ
│   ├── templates/               # CloudFormation 共通テンプレート
│   └── scripts/                 # デプロイ・テストスクリプト
├── integrations/                # ベンダー別実装
│   ├── <vendor-name>/
│   │   ├── README.md
│   │   ├── template.yaml        # CloudFormation テンプレート
│   │   ├── lambda/              # Lambda 関数コード
│   │   ├── docs/
│   │   │   ├── ja/
│   │   │   └── en/
│   │   └── tests/
│   └── ...
├── .github/workflows/           # CI/CD
├── .kiro/steering/              # Kiro ステアリングファイル
├── package.json
├── tsconfig.json
└── jest.config.js
```

## 命名規約

### ディレクトリ名
- ケバブケース: `log-parser`, `s3ap-reader`, `new-relic`
- ベンダー名は公式表記のケバブケース化: `datadog`, `new-relic`, `grafana`

### ファイル名
- Python: スネークケース `log_parser.py`, `s3ap_reader.py`
- TypeScript: キャメルケース `logParser.ts`, `eventHandler.ts`
- CloudFormation: `template.yaml` (各ベンダーディレクトリ直下)
- ドキュメント: ケバブケース `getting-started.md`, `setup-guide.md`

### リソース名 (CloudFormation)
- パスカルケース: `LambdaExecutionRole`, `AuditLogAccessPoint`
- スタック名プレフィックス: `fsxn-<vendor>-integration`

### Lambda 関数名
- パターン: `fsxn-<vendor>-log-shipper`
- 例: `fsxn-datadog-log-shipper`, `fsxn-splunk-log-shipper`

## 新ベンダー追加時のディレクトリ作成

```bash
mkdir -p integrations/<vendor-name>/{lambda,docs/{ja,en},tests}
touch integrations/<vendor-name>/{README.md,template.yaml}
```
