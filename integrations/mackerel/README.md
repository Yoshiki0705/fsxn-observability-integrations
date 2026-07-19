# Mackerel Integration (Logs, Open Beta)

🌐 [日本語](#概要) | [English](#overview)

---

## 概要

FSx for ONTAP 監査ログを [Mackerel](https://mackerel.io/ja/) のログ機能（2026年7月16日にオープンβとして公開）に OpenTelemetry (OTLP) 経由でサーバーレス配信するパターンです。

> **ステータス: E2E 検証済み（両配信経路、2026年7月18日）**
> Collector 経由の経路、Lambda から Mackerel へ直接送信する経路のどちらも、実際の Mackerel オーガニゼーション（Free プラン）に対して E2E 送信を確認済みです。Collector 経由では OTel Collector のデフォルト送信形式（Protobuf）がそのまま使えるため変更不要でしたが、Lambda 直接送信では当初 OTLP/JSON のみに対応していたため `{"code":400,"message":"json is not supported yet"}` エラーで失敗することが判明しました（Mackerel の OTLP エンドポイントは JSON 未対応、Protobuf のみ受理）。この問題に対応するため、外部依存を追加しない自作の軽量 OTLP/Protobuf エンコーダー（`otlp_protobuf.py`）と、新しい `OTLP_CONTENT_TYPE=protobuf` オプションを追加しました。修正後、`handler.py` の実際の関数（`build_otlp_payload`・`_send_otlp_payload`）を直接呼び出し、Mackerel のログ検索 API（`findLogs` GraphQL クエリ）で実データ（`SVMName`・`UserName`・`ClientIP`・`Operation`・`Result` 等の全属性）が届いていることを確認しました。本ディレクトリ（`integrations/mackerel/`）自体には独立した `lambda/`・`template.yaml` はありません（Mackerel 専用の新規スタックではなく既存 `otel-collector/template.yaml` のパラメータ指定で対応する方針のため）。ただし、Mackerel のログ機能自体がβ版である点（データ保持の保証なし等）は変わらないため、他の9ベンダーとは異なる注意点が残ります。詳細は[実装ステータス](#実装ステータス)を参照してください。

### 配信方式

| 方式 | エンドポイント | 認証 | 備考 |
|------|-------------|------|------|
| **OTLP/HTTP（唯一の方式）** | `https://otlp-vaxila.mackerelio.com` | `Mackerel-Api-Key` ヘッダー（Write 権限） | トレース機能と同一エンドポイント・同一認証方式 |

Mackerel はログ機能について独自 API での直接投稿を提供していません。OpenTelemetry Collector（OSS の OTel Collector Contrib、または Mackerel 提供の MDOT Collector）を経由した OTLP `logs` パイプラインが唯一の送信経路です。

### アーキテクチャ

既存の [`otel-collector`](../otel-collector/) 統合と同じ構造です。Lambda はバックエンド中立の OTLP `resourceLogs` ペイロードを構築し、バックエンドの選択は Collector の `exporters` 設定のみで切り替えます。

```
FSx for ONTAP → S3 Access Point → EventBridge Scheduler → Lambda (OTLP変換)
  → OTel Collector (otlphttp/mackerel exporter) → Mackerel ログ機能 (OTLP/HTTP)
```

### 前提条件

準備が必要なリソース ID・値のチェックリスト:

- [ ] Mackerel アカウント（フリープラン、スタンダードプラン、いずれかのトライアルで利用可。パートナープログラム経由の契約では利用不可の場合あり）
- [ ] Write 権限のある Mackerel API キー（[セットアップガイド Step 1.1](docs/ja/setup-guide.md#11-write-権限のある-api-キーの取得) で取得）
- [ ] OpenTelemetry Collector を動作させる環境（Docker、ECS Fargate、EC2 など。既存プロジェクトの推奨構成は ECS Fargate。直接送信経路のみ使う場合は不要）
- [ ] 既存の FSx for ONTAP 監査ログ用 S3 バケット名（`S3BucketName` パラメータ用。未作成の場合は [`docs/ja/prerequisites.md`](../../docs/ja/prerequisites.md) を先に参照）
- [ ] Lambda デプロイパッケージ（ZIP）の S3 アップロード先（`LambdaCodeS3Bucket`/`LambdaCodeS3Key` パラメータ用。ビルド手順は [`otel-collector/README.md`](../otel-collector/README.md) を参照）
- [ ] （直接送信経路の場合）Secrets Manager に保存した API キーの ARN（[セットアップガイド Step 1.2](docs/ja/setup-guide.md#12-aws-secrets-manager-への保存)）

### デプロイ時間の見積もり

| 作業 | 所要時間の目安 |
|------|---------------|
| ローカル Docker Compose での検証（Step 1〜4） | 約10〜15分（Mackerel APIキー取得、Collector起動、サンプルペイロード送信、ログ画面確認） |
| CloudFormation スタックデプロイ（Collector経由・直接送信いずれも） | 約3〜5分（3つの Lambda 関数 + IAM ロール + API Gateway + EventBridge ルール + DLQ + CloudWatch アラーム） |
| スタック削除（ロールバック） | 約2〜3分 |

### コストに関する補足

- **Mackerel 側のコスト**: β期間中のログ取り込み自体は無料。正式版（2026年秋予定）以降はインジェスト量に応じた課金（70円/GB、税抜。1.1GB取り込みなら140円、切り上げ計算）に切り替わる。スタンダードプランはログ専用の無料枠がなく、月額最低利用料金（2,180円、税込）の対象。フリープランは月間1GBまで、保存期間30日は正式版でも変わらない
- **AWS 側の固定コスト**: 本統合が新たに作成するリソース（Lambda × 3、S3 Access Point、EventBridge ルール、API Gateway、SQS DLQ、CloudWatch アラーム × 3）は、実行頻度が低ければ月額でごく小さい従量課金のみ（既存の [otel-collector 統合のコスト前提](../otel-collector/README.md) と同様、EC2 常時起動が不要な構成）
- **Collector 実行コスト（Collector経由の場合のみ）**: ローカル Docker は無料、ECS Fargate で常設運用する場合は別途 AWS インフラコストが発生（本統合ではまだ具体的な見積もりを行っていません — 直接送信経路を使えばこのコストは発生しません）
- **コスト最適化のヒント**: β版検証のみが目的であれば、Collector を立てずに直接送信経路（Step 5、`OtlpContentType=protobuf`）を使うことで ECS Fargate 等のコストを完全に回避できます

### β版の重要な制約（Mackerel 公式情報、2026年7月16日時点）

- **無料**: β期間中は課金なし。正式リリース後に遡って課金されることもない
- **データ保持の保証なし**: 「β版という位置づけのため、お預かりしているログデータの保持を保証することはできません」（Mackerel公式）
- **臨時メンテナンスの可能性**: 機能改善・不具合修正のため予告なくメンテナンスが入る場合がある
- **保存期間**: 正式版で30日間を予定。β版も同条件
- **正式リリースは2026年秋頃を予定**（Mackerel公式発表、2026年7月16日時点）。料金体系（インジェスト量課金、70円/GB税抜）は既に公表済み（下記「参考資料」の公式ブログを参照）

> **重要**: 本統合を本番のセキュリティ監視・コンプライアンス用途（ランサムウェア検知アラート等）に使う場合、上記の「データ保持の保証なし」という制約を必ず利用者に周知してください。他の9ベンダー統合とは異なり、Mackerel ログ機能は本稼働の SLA を現時点で提供していません。

### 実装ステータス

- [x] 技術検証（公式ドキュメント確認: OTLPエンドポイント、認証方式、Collector設定例）
- [x] セットアップドキュメント（本README、[setup-guide.md](docs/en/setup-guide.md)）
- [x] OTel Collector 設定・Docker Compose・テストスクリプト（[`otel-collector-config-mackerel.yaml`](../otel-collector/otel-collector-config-mackerel.yaml)、`docker-compose-mackerel.yaml`、`scripts/test-local-mackerel.sh`。`validate-configs.sh` でYAML構造検証済み。**実際の Mackerel オーガニゼーションへの E2E 送信を確認済み**）
- [x] Lambda ハンドラーの認証拡張（[OTel Collector 統合](../otel-collector/) の `handler.py`・`ems_handler.py`・`fpolicy_handler.py` に、Mackerel の `Mackerel-Api-Key` のような独自ヘッダー認証に対応する汎用オプション `AUTH_MODE=header` / `AUTH_HEADER_NAME` と、`Accept: */*` のような静的ヘッダーに対応する `EXTRA_HEADERS_JSON` を追加。**Mackerel 固有の分岐は一切追加していません** — 既存の `bearer`/`basic` と同列の汎用プリミティブとして実装）
- [x] `template.yaml`（CloudFormation スタック — `AuthMode=header`・`AuthHeaderName`・`ExtraHeadersJson`・`OtlpContentType` パラメータを既存 `otel-collector/template.yaml` に追加済み。Mackerel 専用の新規スタックは作成せず、既存スタックのパラメータ指定で対応する方針）
- [x] Lambda 直接送信経路の OTLP/Protobuf 対応（`OTLP_CONTENT_TYPE=protobuf` オプションを追加。詳細は下記「Lambda 直接送信経路の修正（OTLP/Protobuf 対応）」を参照）
- [x] 単体テスト（3つの Lambda ハンドラー全体で、`AUTH_MODE=header` 認証関連4件×3ハンドラー、`OTLP_CONTENT_TYPE=protobuf` エンコード関連3件×3ハンドラー、加えて専用の `test_otlp_protobuf.py` に11件、合計32件を追加。cfn-lint・gitleaks も実行しクリーン、OTel Collector 統合のテストスイート全体で110件パス）
- [x] ローカル Docker Compose・Lambda 直接送信、両経路の実 E2E 検証（2026年7月18日、Free プランの Mackerel オーガニゼーションで実施。Collector 経由では FSx 監査ログのサンプルペイロード4件を送信し、Mackerel の `findLogs` GraphQL クエリで全属性を保持したまま取り込まれていることを確認。Lambda 直接送信は当初 OTLP/JSON のみでMackerelに拒否されたため、`OTLP_CONTENT_TYPE=protobuf` を追加した上で `handler.py` の実関数を直接呼び出して再検証し、成功を確認。検証時に踏んだ落とし穴は下記「検証時の注意点」を参照）
- [ ] `docs/ja/vendor-comparison.md` / `docs/en/vendor-comparison.md` への正式掲載（β版の制約が残るため、βとして明記のうえ「Emerging/Beta Vendors」節に掲載。GA後に正式掲載を検討）

**このリポジトリでの位置づけ**: 既存の [OTel Collector 統合](../otel-collector/) に2つの配信経路を用意しました。(1) Collector 経由（`otlphttp/mackerel` exporter、Lambda 側は完全に変更不要）— 手順は [セットアップガイド Step 1〜4](docs/ja/setup-guide.md)、(2) Lambda から Mackerel の OTLP エンドポイントへ直接送信（Collector を経由しない場合。この経路では `Mackerel-Api-Key` という独自ヘッダーが必要なため、既存の `bearer`/`basic` だけでは対応できず、汎用の `AUTH_MODE=header` オプションを追加しました）— 手順は [セットアップガイド](docs/ja/setup-guide.md)の Step 5。どちらの経路でも Mackerel 固有のコード分岐は存在しません。両経路とも実際の API キーでの E2E 送信を確認済みです。

### Lambda 直接送信経路の修正（OTLP/Protobuf 対応）

Collector 経由の経路を E2E 検証した後、Lambda 直接送信経路（`AUTH_MODE=header`）も同様に実 API キーで検証したところ、`handler.py` の実際のコードが以下のエラーで失敗することが判明しました。

```
{"code":400,"message":"json is not supported yet"}
```

**原因**: `_send_otlp_payload` 関数は常に `Content-Type: application/json` で OTLP/JSON を送信していました。しかし Mackerel の OTLP エンドポイントは Protobuf 形式のみ受け付け、JSON を明示的に拒否します。Collector 経由の経路が動いたのは、OTel Collector のエクスポーターがデフォルトで Protobuf を使うためで、Lambda 直接送信のコード自体には元々 Protobuf 対応がありませんでした。

**対応**: 本プロジェクトは Lambda の依存関係を最小限（boto3/urllib3 のみ、いずれも Lambda ランタイム標準）に保つ方針のため、`protobuf`/`opentelemetry-proto` パッケージを追加する代わりに、OTLP Logs Data Model に必要な範囲だけを実装した依存ゼロの軽量 Protobuf エンコーダー（[`otlp_protobuf.py`](../otel-collector/lambda/otlp_protobuf.py)）を自作しました。フィールド番号は [OTLP公式 proto定義](https://github.com/open-telemetry/opentelemetry-proto)（Apache License 2.0）から取得し、実装は公式の `opentelemetry-proto` 生成クラスでデコードして構造が一致することを検証済みです。

新しい `OTLP_CONTENT_TYPE` 環境変数（デフォルト `json`、Mackerel 等には `protobuf` を指定）を3つの Lambda ハンドラー全てと `template.yaml` に追加しました。この修正後、`handler.py` の実際の `build_otlp_payload`・`_send_otlp_payload` 関数を直接呼び出し、`AUTH_MODE=header` + `OTLP_CONTENT_TYPE=protobuf` の組み合わせで実際の Mackerel API キーに対して送信し、`findLogs` GraphQL クエリで2件のログレコード（`ReadData`/`Success`、`Delete`/`Access Denied`）が全属性を保持したまま到着していることを確認しました。

### 検証時の注意点

E2E 検証中に踏んだ3つの落とし穴を記録しておきます（同じ調査手順を再現しないための備忘）。

1. **Docker Desktop の内部 DNS 解決エラー**: コンテナのデフォルト DNS リゾルバ（`127.0.0.11`）が `otlp-vaxila.mackerelio.com` の解決に `server misbehaving` エラーで失敗するケースが観測されました（ホスト側では同じホスト名を問題なく解決できていたため、コンテナ内 DNS 特有の問題）。`docker-compose-mackerel.yaml` に明示的な DNS サーバー（`8.8.8.8`、`1.1.1.1`）を指定することで解消しました。同じ症状に遭遇した場合の対処法として設定に含めています。
2. **Mackerel の GraphQL API 名の混同**: Mackerel のログ検索 UI の「サービスを選択」プルダウンは、`findIngestedServices`（トレース/APM機能専用のクエリ）ではなく `findLogIngestedServices` / `findLogs`（ログ機能専用のクエリ）を参照しています。ブラウザの開発者ツールで見えるネットワークリクエスト名だけで判断せず、GraphQL スキーマの introspection（`__schema`）で正しいクエリ名を確認する必要がありました。この混同により、実際には送信が成功していたログが「届いていない」ように見える誤診断が一時的に発生しました。
3. **Lambda 直接送信は OTLP/JSON のみでは Mackerel に届かない**: 「Collector経由の経路を検証したから直接送信も同様に動くはず」という前提は誤りでした。Mackerel の OTLP エンドポイントは Protobuf 専用で、JSON ペイロードを明示的に `400` エラーで拒否します。ペイロード形式（JSON/Protobuf）とネットワーク層の到達性は別の検証項目であり、片方の経路の検証結果を別経路に流用してはならないという教訓です。

### Day 2 運用

- **モニタリング**: `otel-collector/template.yaml` がデプロイする3つの CloudWatch アラーム（`<stack-name>-audit-errors`・`<stack-name>-ems-errors`・`<stack-name>-fpolicy-errors`）と共有 DLQ（`<stack-name>-dlq`）を監視してください。DLQ にメッセージが溜まる場合は OTLP 配信の継続的な失敗を意味します。
- **設定変更**: Mackerel の APIキーをローテーションする場合、Secrets Manager 上のシークレット値を直接更新するだけで済みます（`ApiKeySecretArn` 自体を変更しない限り、スタックの再デプロイは不要）。エンドポイントや認証方式を変更する場合は、`--parameter-overrides` を指定して再デプロイしてください（Lambda コードの変更は不要）。
- **β版の継続的な注意**: Mackerel のログ機能が正式版に移行した際は、保存期間の SLA・料金体系を確認し、本統合のβ版制約に関する記述（本README・セットアップガイド）を見直してください。

### ロールバックとクリーンアップ

```bash
# スタック削除（Mackerel 統合を含む otel-collector スタック全体）
aws cloudformation delete-stack --stack-name fsxn-otel-integration
aws cloudformation wait stack-delete-complete --stack-name fsxn-otel-integration
```

削除されるもの: S3 Access Point、3つの Lambda 関数のロググループ、共有 DLQ、EMS 用 API Gateway。
削除されないもの（本スタックが参照のみで所有していない外部リソース）: S3 バケット本体、`ApiKeySecretArn` が指すシークレット、`FPolicySqsQueueArn` が指すSQSキュー。これらは必要に応じて個別に削除してください。

ローカル Docker Compose 環境のクリーンアップ:

```bash
docker compose -f ../otel-collector/docker-compose-mackerel.yaml --env-file ../otel-collector/.env.mackerel down --remove-orphans
rm -f ../otel-collector/.env.mackerel   # 実APIキーを含むファイルを削除
```

### 参考資料

- [Mackerel のログ機能をオープンβ版として公開しました！（公式ブログ）](https://mackerel.io/ja/blog/entry/announcement/log-beta-release)
- [Mackerel にログを送信する（公式ヘルプ）](https://mackerel.io/ja/docs/entry/log/sending)
- [RailsのログをMackerelに送る3つの方法（公式ブログ、OTelログブリッジがない言語向けパターン）](https://mackerel.io/ja/blog/entry/tech/sending-logs-from-rails)

---

## Overview

Serverless delivery of FSx for ONTAP audit logs to [Mackerel](https://en.mackerel.io/)'s log feature (opened as public beta on July 16, 2026) via OpenTelemetry (OTLP).

> **Status: E2E verified, both delivery paths (2026-07-18)**
> Both the Collector-mediated path and the Lambda direct-send path have been confirmed end-to-end against a real Mackerel organization (Free plan). The Collector-mediated path worked as-is, since the OTel Collector's exporter already defaults to Protobuf. The direct-send path initially failed with `{"code":400,"message":"json is not supported yet"}`, because it only supported OTLP/JSON and Mackerel's OTLP endpoint rejects JSON outright (Protobuf only). To fix this, a dependency-free, hand-rolled OTLP/Protobuf encoder (`otlp_protobuf.py`) and a new `OTLP_CONTENT_TYPE=protobuf` option were added. After the fix, calling `handler.py`'s actual `build_otlp_payload`/`_send_otlp_payload` functions directly confirmed delivery via Mackerel's log search API (the `findLogs` GraphQL query), with all attributes intact (`SVMName`, `UserName`, `ClientIP`, `Operation`, `Result`, etc.). This directory (`integrations/mackerel/`) itself has no standalone `lambda/` or `template.yaml` — by design, this uses the existing `otel-collector/template.yaml`'s parameters rather than a separate Mackerel-specific stack. Mackerel's log feature itself remains a beta (no data retention guarantee, etc.), which is the main way this differs from the other 9 vendors. See [Implementation Status](#implementation-status) below.

### Delivery Method

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| **OTLP/HTTP (only method)** | `https://otlp-vaxila.mackerelio.com` | `Mackerel-Api-Key` header (Write scope) | Same endpoint and auth as Mackerel's tracing (APM) feature |

Mackerel's log feature does not offer a proprietary direct-ingest API. The only supported path is an OTLP `logs` pipeline through an OpenTelemetry Collector (either OSS OTel Collector Contrib, or Mackerel's own MDOT Collector distribution).

### Architecture

Same structural pattern as the existing [`otel-collector`](../otel-collector/) integration: the Lambda builds a backend-neutral OTLP `resourceLogs` payload, and backend selection is handled entirely in the Collector's `exporters` configuration.

```
FSx for ONTAP → S3 Access Point → EventBridge Scheduler → Lambda (OTLP conversion)
  → OTel Collector (otlphttp/mackerel exporter) → Mackerel log feature (OTLP/HTTP)
```

### Prerequisites

Checklist of resource IDs/values to gather before starting:

- [ ] Mackerel account (Free plan, Standard plan, or either plan's trial; may be unavailable under some partner-program contracts)
- [ ] Mackerel API key with Write scope (obtained in [setup guide Step 1.1](docs/en/setup-guide.md#11-obtaining-a-write-scoped-api-key))
- [ ] An environment to run an OpenTelemetry Collector (Docker, ECS Fargate, EC2, etc. — this project's recommended pattern is ECS Fargate; not needed if using the direct-send path only)
- [ ] Name of an existing S3 bucket receiving FSx for ONTAP audit logs (for the `S3BucketName` parameter — see [`docs/en/prerequisites.md`](../../docs/en/prerequisites.md) first if not yet created)
- [ ] An S3 location for your Lambda deployment package (ZIP) upload (for `LambdaCodeS3Bucket`/`LambdaCodeS3Key` — build steps in [`otel-collector/README.md`](../otel-collector/README.md))
- [ ] (Direct-send path only) ARN of the Secrets Manager secret storing the API key ([setup guide Step 1.2](docs/en/setup-guide.md#12-storing-the-api-key-in-aws-secrets-manager))

### Deployment Time Estimate

| Task | Approximate time |
|------|------------------|
| Local Docker Compose validation (Steps 1–4) | ~10–15 minutes (obtain Mackerel API key, start the Collector, send a sample payload, confirm in the log screen) |
| CloudFormation stack deploy (either Collector-mediated or direct-send) | ~3–5 minutes (3 Lambda functions + IAM role + API Gateway + EventBridge rules + DLQ + 3 CloudWatch alarms) |
| Stack deletion (rollback) | ~2–3 minutes |

### Cost Considerations

- **Mackerel-side cost**: log ingestion itself is free during the beta period. From GA (planned for fall 2026) onward, pricing switches to ingest-volume billing (¥70/GB, excl. tax; e.g. 1.1GB rounds up to ¥140). The Standard plan has no free tier specifically for logs and is subject to a monthly minimum charge (¥2,180, incl. tax) if log ingestion alone doesn't reach that amount. The Free plan allows up to 1GB/month; the 30-day retention window is unchanged at GA.
- **AWS fixed cost**: the resources this integration adds (3 Lambda functions, an S3 Access Point, EventBridge rules, an API Gateway, an SQS DLQ, 3 CloudWatch alarms) incur only small usage-based charges at low invocation volume — same cost profile as the rest of the [otel-collector integration](../otel-collector/README.md) (no always-on EC2 required).
- **Collector runtime cost (Collector-mediated path only)**: running locally in Docker is free; running the Collector persistently on ECS Fargate incurs its own AWS infrastructure cost, not yet estimated for this specific integration.
- **Cost optimization tip**: if you only need to validate the beta feature, skip standing up a Collector entirely and use the direct-send path (Step 5, `OtlpContentType=protobuf`) instead — this avoids ECS Fargate costs altogether.

### Critical Beta Constraints (per Mackerel's official announcement, as of 2026-07-16)

- **Free**: No charges during the beta period. Mackerel has stated logs sent during beta will not be retroactively billed after GA.
- **No data retention guarantee**: Mackerel's own wording: because this is a beta feature, they cannot guarantee retention of log data submitted during beta.
- **Unscheduled maintenance possible**: Maintenance may occur without notice for feature improvements or bug fixes.
- **Retention window**: 30 days planned for GA; beta currently operates under the same window.
- **GA is planned for fall 2026** (per Mackerel's official announcement, as of 2026-07-16). Pricing (ingest-volume billing, ¥70/GB excl. tax) has already been published — see the official blog post linked in "References" below.

> **Important**: If this integration is used for production security monitoring or compliance purposes (e.g., ransomware-detection alerting), the "no retention guarantee" constraint above must be communicated to stakeholders. Unlike the other 9 vendor integrations in this repo, Mackerel's log feature currently offers no production SLA.

### Implementation Status

- [x] Technical feasibility research (confirmed via official docs: OTLP endpoint, auth method, Collector config example)
- [x] Setup documentation (this README, [setup-guide.md](docs/en/setup-guide.md))
- [x] OTel Collector config, Docker Compose, and test script ([`otel-collector-config-mackerel.yaml`](../otel-collector/otel-collector-config-mackerel.yaml), `docker-compose-mackerel.yaml`, `scripts/test-local-mackerel.sh`; YAML structure validated via `validate-configs.sh`. **Confirmed end-to-end against a real Mackerel organization**)
- [x] Lambda handler auth extension (added generic `AUTH_MODE=header` / `AUTH_HEADER_NAME` for custom-header auth like Mackerel's `Mackerel-Api-Key`, plus `EXTRA_HEADERS_JSON` for static headers like the required `Accept: */*`, to [OTel Collector integration](../otel-collector/)'s `handler.py`, `ems_handler.py`, and `fpolicy_handler.py`. **No Mackerel-specific branching was added** — these are generic primitives alongside the existing `bearer`/`basic` modes)
- [x] `template.yaml` (CloudFormation stack — `AuthMode=header`, `AuthHeaderName`, `ExtraHeadersJson`, and `OtlpContentType` parameters have been added to the existing `otel-collector/template.yaml`; no standalone Mackerel stack planned)
- [x] OTLP/Protobuf support for the direct-send path (added `OTLP_CONTENT_TYPE=protobuf` option — see "Fixing the direct-send path (OTLP/Protobuf support)" below)
- [x] Unit tests (32 added: 4 auth-mode tests per handler covering `header` mode/`EXTRA_HEADERS_JSON` merging/missing-secret path/malformed-JSON fail-safe, plus 3 `OTLP_CONTENT_TYPE=protobuf` tests per handler, plus 11 in a dedicated `test_otlp_protobuf.py` — across all three Lambda handlers. cfn-lint and gitleaks also run clean; all 110 tests in the OTel Collector integration's suite pass)
- [x] Real E2E verification of both the Collector-mediated and Lambda direct-send paths (performed 2026-07-18 against a Free-plan Mackerel organization. Collector-mediated: sent 4 sample FSx audit log records and confirmed arrival with all attributes intact via Mackerel's `findLogs` GraphQL query. Direct-send: initially failed with OTLP/JSON — Mackerel rejected it — then re-verified successfully after adding `OTLP_CONTENT_TYPE=protobuf`, by calling `handler.py`'s actual functions directly. See "Verification gotchas" below for pitfalls hit during this process)
- [ ] Formal listing in `docs/en/vendor-comparison.md` / `docs/ja/vendor-comparison.md` (listed in the "Emerging/Beta Vendors" section, clearly marked beta, given Mackerel's log feature retains beta constraints; reconsider for the main vendor table at GA)

**Where this fits in the repo**: two delivery paths now exist. (1) Collector-mediated (`otlphttp/mackerel` exporter; zero Lambda changes) — see [setup guide Steps 1–4](docs/en/setup-guide.md). (2) Lambda sending directly to Mackerel's OTLP endpoint, bypassing a Collector — this path needed a small Lambda change, because Mackerel's `Mackerel-Api-Key` custom header wasn't expressible via the existing `bearer`/`basic` auth modes, so a generic `AUTH_MODE=header` option was added — see [setup guide Step 5](docs/en/setup-guide.md#step-5-direct-send-alternative-skip-the-collector). Neither path contains Mackerel-specific code branches. Both paths have been confirmed end-to-end with a real API key.

### Fixing the direct-send path (OTLP/Protobuf support)

After verifying the Collector-mediated path end-to-end, verifying the Lambda direct-send path (`AUTH_MODE=header`) with a real API key uncovered that the actual `handler.py` code failed with:

```
{"code":400,"message":"json is not supported yet"}
```

**Root cause**: `_send_otlp_payload` always sent OTLP/JSON with `Content-Type: application/json`. Mackerel's OTLP endpoint only accepts Protobuf and explicitly rejects JSON. The Collector-mediated path worked because the OTel Collector's exporter defaults to Protobuf — the direct-send Lambda code itself never had Protobuf support.

**Fix**: this project intentionally keeps the Lambda runtime dependency-free (only boto3/urllib3, both included in the Lambda Python runtime). Rather than adding the `protobuf`/`opentelemetry-proto` PyPI packages, a small hand-rolled Protobuf encoder ([`otlp_protobuf.py`](../otel-collector/lambda/otlp_protobuf.py)) was written, covering only the subset of the OTLP Logs Data Model this repo's payload builders already produce. Field numbers were taken from the [official OTLP proto definitions](https://github.com/open-telemetry/opentelemetry-proto) (Apache License 2.0), and the encoder's output was verified byte-for-byte against the official `opentelemetry-proto` generated Python classes in a throwaway virtualenv.

A new `OTLP_CONTENT_TYPE` environment variable (default `json`; set to `protobuf` for Mackerel and similar vendors) was added to all three Lambda handlers and `template.yaml`. After this fix, calling `handler.py`'s actual `build_otlp_payload`/`_send_otlp_payload` functions directly with `AUTH_MODE=header` + `OTLP_CONTENT_TYPE=protobuf` against a real Mackerel API key succeeded, and the `findLogs` GraphQL query confirmed both log records (`ReadData`/`Success` and `Delete`/`Access Denied`) arrived intact with all attributes preserved.

### Verification gotchas

Three pitfalls hit during E2E verification, recorded here so the same investigation doesn't need to repeat:

1. **Docker Desktop internal DNS resolution failure**: the container's default DNS resolver (`127.0.0.11`) intermittently failed to resolve `otlp-vaxila.mackerelio.com` with a `server misbehaving` error, even though the host machine resolved the same hostname without issue (a container-DNS-specific problem, not a Mackerel-side issue). Setting an explicit DNS server list (`8.8.8.8`, `1.1.1.1`) in `docker-compose-mackerel.yaml` resolved it; that override is now included in the config as a documented mitigation for the same symptom.
2. **Mackerel GraphQL query naming confusion**: Mackerel's log search UI's "Select service" dropdown is backed by `findLogIngestedServices` / `findLogs` (log-feature-specific queries), not `findIngestedServices` (a tracing/APM-feature query with a similar name). Relying only on the network request name visible in browser devtools was misleading; confirming the correct query name required a GraphQL schema introspection query (`__schema`). This naming collision temporarily produced a false "logs not arriving" diagnosis for logs that had, in fact, already been delivered successfully.
3. **Verifying one delivery path does not verify another**: assuming the direct-send path would "just work" the same way the Collector-mediated path did was wrong. Mackerel's OTLP endpoint is Protobuf-only and explicitly rejects JSON with a `400`. Payload wire format (JSON vs. Protobuf) and network-layer reachability are separate things to verify; a passing result on one delivery path must not be assumed to carry over to a different one.

### Day 2 Operations

- **Monitoring**: watch the 3 CloudWatch Alarms `otel-collector/template.yaml` creates (`<stack-name>-audit-errors`, `<stack-name>-ems-errors`, `<stack-name>-fpolicy-errors`) and the shared DLQ (`<stack-name>-dlq`). Messages accumulating in the DLQ indicate sustained OTLP delivery failures.
- **Config changes**: rotate the Mackerel API key by updating the secret's value directly in Secrets Manager — no stack redeploy needed unless `ApiKeySecretArn` itself changes. To change the endpoint or auth mode, redeploy with updated `--parameter-overrides` (no Lambda code changes required).
- **Ongoing beta awareness**: once Mackerel's log feature reaches GA, re-check the retention SLA and pricing, and revisit the beta-constraint language in this README and the setup guide.

### Rollback and Cleanup

```bash
# Delete the stack (the entire otel-collector stack, including the Mackerel integration)
aws cloudformation delete-stack --stack-name fsxn-otel-integration
aws cloudformation wait stack-delete-complete --stack-name fsxn-otel-integration
```

Deleted: the S3 Access Point, both Lambda functions' log groups, the shared DLQ, and the EMS API Gateway.
NOT deleted (external resources this stack only references, never owns): the S3 bucket itself, the secret referenced by `ApiKeySecretArn`, and the SQS queue referenced by `FPolicySqsQueueArn`. Delete these separately if no longer needed.

Cleaning up the local Docker Compose environment:

```bash
docker compose -f ../otel-collector/docker-compose-mackerel.yaml --env-file ../otel-collector/.env.mackerel down --remove-orphans
rm -f ../otel-collector/.env.mackerel   # remove the file containing your real API key
```

### References

- [Mackerel's log feature is now available as an open beta (official blog, JA)](https://mackerel.io/ja/blog/entry/announcement/log-beta-release)
- [Sending logs to Mackerel (official help, JA)](https://mackerel.io/ja/docs/entry/log/sending)
- [3 ways to send Rails logs to Mackerel (official blog, JA — pattern for languages without an OTel log bridge)](https://mackerel.io/ja/blog/entry/tech/sending-logs-from-rails)
