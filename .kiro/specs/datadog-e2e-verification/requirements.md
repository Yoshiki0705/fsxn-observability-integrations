# Requirements Document

## Introduction

Datadog 統合の End-to-End 動作確認（E2E テスト）を実施し、Datadog 側の設定手順をスクリーンショット付きで文書化する。デモシナリオ1「不正アクセス検知」を実際に実行し、統合が正しく動作することを検証する。また、セットアップガイドが日英2言語で完全に対応していることを確認する。

## Glossary

- **Lambda_Shipper**: FSx ONTAP 監査ログを Datadog Logs API v2 に配信する Lambda 関数 (`fsxn-datadog-integration-shipper`)
- **Datadog_Logs_UI**: Datadog コンソールの Logs → Search 画面
- **Log_Pipeline**: Datadog のログ処理パイプライン（Grok Parser, Status Remapper, Date Remapper を含む）
- **Facet**: Datadog Logs で検索・フィルタリングに使用するインデックス付きフィールド
- **Dashboard**: Datadog で作成する FSx ONTAP 監査ログ可視化ダッシュボード
- **E2E_Test**: Lambda デプロイからログ到着確認までの一連の動作確認
- **Verification_Results_Document**: 動作確認結果を記録するマークダウンドキュメント (`docs/ja/verification-results-datadog.md`)
- **Setup_Guide**: Datadog 統合のセットアップ手順書 (`integrations/datadog/docs/{ja,en}/setup-guide.md`)
- **Demo_Scenario**: `docs/ja/demo-scenarios.md` に記載されたシナリオ1「不正アクセス検知」
- **Screenshot_Directory**: スクリーンショットを配置するディレクトリ (`docs/screenshots/`)

## Requirements

### Requirement 1: Lambda 関数のデプロイとテストイベント送信

**User Story:** As a プロジェクト管理者, I want to Lambda 関数をデプロイしてテストイベントを送信する, so that Datadog 統合が正しく動作することを確認できる。

#### Acceptance Criteria

1. WHEN CloudFormation テンプレートがデプロイされる, THE Lambda_Shipper SHALL スタック `fsxn-datadog-integration` としてステータス `CREATE_COMPLETE` で作成され、Lambda 関数、IAM ロール、Dead Letter Queue、CloudWatch Alarms の各リソースが作成される
2. WHEN S3 イベント通知形式（`Records[].s3.bucket.name` および `Records[].s3.object.key` を含む JSON）のテストイベントが Lambda_Shipper に送信される, THE Lambda_Shipper SHALL 全レコード処理成功時にステータスコード 200 を返却し、レスポンスボディに `total_logs`、`total_shipped`、`errors` フィールドを含める
3. WHEN Lambda_Shipper がテストイベントを処理する, THE Lambda_Shipper SHALL CloudWatch Logs にログレベル INFO で受信イベント内容および処理完了サマリ（処理件数、配信件数、エラー件数）を記録する
4. IF Lambda_Shipper がテストイベント処理中に S3 オブジェクト読み取り失敗または Datadog API への配信失敗（3 回リトライ後）を検出した場合, THEN THE Lambda_Shipper SHALL CloudWatch Logs にエラーレベルで対象バケット名・オブジェクトキー・エラー内容を記録し、ステータスコード 207 を返却する
5. IF Lambda_Shipper の呼び出しが非同期実行で失敗した場合, THEN THE Lambda_Shipper SHALL 失敗したイベントを Dead Letter Queue に送信する

### Requirement 2: Datadog Logs UI でのログ到着確認

**User Story:** As a プロジェクト管理者, I want to Datadog Logs UI でログの到着を確認する, so that Lambda から Datadog へのログ配信が正常に動作していることを証明できる。

#### Acceptance Criteria

1. WHEN Lambda_Shipper がテストイベントを処理し statusCode 200 かつ total_shipped >= 1 を返した後, THE Datadog_Logs_UI SHALL 検索クエリ `source:fsxn` で該当ログを5分以内に1件以上表示する
2. WHEN ログが Datadog_Logs_UI に到着する, THE Datadog_Logs_UI SHALL 各ログエントリに対して `attributes.svm`, `attributes.user`, `attributes.operation`, `attributes.client_ip`, `attributes.result`, `attributes.path` フィールドを空文字でない値で表示する
3. WHEN ログ到着が確認される, THE E2E_Test SHALL Datadog_Logs_UI のログ一覧画面のスクリーンショットを Screenshot_Directory に `datadog-logs-arrival.png` のファイル名で保存する
4. IF 検索クエリ `source:fsxn` で5分以内にログが1件も表示されない場合, THEN THE E2E_Test SHALL タイムアウトエラーを報告し、Lambda_Shipper の実行ログ（statusCode および errors フィールド）を診断情報として出力する

### Requirement 3: Log Pipeline 設定と文書化

**User Story:** As a プロジェクト管理者, I want to Datadog Log Pipeline を設定してスクリーンショットを撮影する, so that セットアップ手順を視覚的に文書化できる。

#### Acceptance Criteria

1. WHEN Log_Pipeline が作成される, THE Log_Pipeline SHALL フィルタ `source:fsxn` と名前 `FSx ONTAP Audit Logs` で構成される
2. WHEN Log_Pipeline に Grok Parser プロセッサが追加される, THE Log_Pipeline SHALL FSx ONTAP 監査ログから以下の属性をパースできる: `timestamp`, `EventID`, `SVMName`, `UserName`, `ClientIP`, `Operation`, `ObjectName`, `Result`
3. WHEN Log_Pipeline に Status Remapper が追加される, THE Log_Pipeline SHALL `attributes.result` フィールド（値: `Success` または `Failure`）をログステータスにマッピングする
4. WHEN Log_Pipeline に Date Remapper が追加される, THE Log_Pipeline SHALL `attributes.timestamp` フィールド（ISO 8601 形式）をログタイムスタンプにマッピングする
5. WHEN Log_Pipeline の全プロセッサ（Grok Parser, Status Remapper, Date Remapper）が追加され Pipeline が保存される, THE E2E_Test SHALL Pipeline 設定画面のスクリーンショットを PNG 形式で Screenshot_Directory に保存する
6. IF Log_Pipeline の作成時に同名の Pipeline が既に存在する, THEN THE E2E_Test SHALL 既存の Pipeline を再利用し、エラーを発生させずに処理を継続する

### Requirement 4: Facets 設定と文書化

**User Story:** As a プロジェクト管理者, I want to Datadog Facets を設定してスクリーンショットを撮影する, so that ログ検索の利便性向上と設定手順の文書化を同時に達成できる。

#### Acceptance Criteria

1. WHEN Facet が作成される, THE Datadog_Logs_UI SHALL 以下の6つの Facet をログ検索画面の左側フィルタパネルに表示し、各 Facet をクリックして値一覧が展開可能な状態にする: SVM (`@attributes.svm`), User (`@attributes.user`), Operation (`@attributes.operation`), Client IP (`@attributes.client_ip`), Result (`@attributes.result`), File Path (`@attributes.path`)
2. WHEN 全ての6つの Facet が作成される, THE E2E_Test SHALL Facets 設定画面のスクリーンショットを PNG 形式で Screenshot_Directory に `datadog-facets-config.png` のファイル名で保存する
3. WHEN Facet を使用してログを検索する, THE Datadog_Logs_UI SHALL 選択した Facet 値に一致するログのみを検索結果に表示し、一致しないログが結果に含まれないこと
4. IF Facet 作成対象の属性パスにログデータが存在しない, THEN THE Datadog_Logs_UI SHALL Facet を作成可能とするが、値一覧には項目が表示されない状態となること

### Requirement 5: ダッシュボード作成と文書化

**User Story:** As a プロジェクト管理者, I want to Datadog ダッシュボードを作成してスクリーンショットを撮影する, so that 監査ログの可視化パターンを文書化できる。

#### Acceptance Criteria

1. WHEN Dashboard が作成される, THE Dashboard SHALL ログ量推移ウィジェットとして `source:fsxn` のログカウント時系列を過去24時間の範囲で表示するウィジェットを含む
2. WHEN Dashboard が作成される, THE Dashboard SHALL 操作別内訳ウィジェットとして `@attributes.operation` のトップリスト（上位10件）を表示するウィジェットを含む
3. WHEN Dashboard が作成される, THE Dashboard SHALL ユーザー別アクティビティウィジェットとして `@attributes.user` のトップリスト（上位10件）を表示するウィジェットを含む
4. WHEN Dashboard が作成される, THE Dashboard SHALL エラー率ウィジェットとして `@attributes.result:Failure` の割合をクエリウィジェットで表示するウィジェットを含む
5. WHEN Dashboard の作成が完了する, THE E2E_Test SHALL ダッシュボード全体（4つのウィジェットすべてが視認可能な状態）のスクリーンショットを PNG 形式で Screenshot_Directory に保存する
6. IF Dashboard の作成が失敗した場合, THEN THE E2E_Test SHALL エラー内容を示すメッセージをログに出力し、テストを失敗として終了する
7. WHEN スクリーンショットが保存される, THE E2E_Test SHALL ファイル名を `datadog-dashboard.png` として保存する

### Requirement 6: デモシナリオ1「不正アクセス検知」の実行

**User Story:** As a プロジェクト管理者, I want to デモシナリオ1を実際に実行する, so that 不正アクセス検知のユースケースが正しく動作することを実証できる。

#### Acceptance Criteria

1. WHEN 権限のないユーザーが機密ファイルにアクセスを試行する, THE Lambda_Shipper SHALL アクセス試行から60秒以内にアクセス失敗イベント（`@attributes.result:Failure` を含むログエントリ1件以上）を Datadog に配信する
2. WHEN 不正アクセスイベントが Datadog に到着する, THE Datadog_Logs_UI SHALL 検索クエリ `source:fsxn @attributes.result:Failure` で該当イベントを1件以上表示する
3. WHEN 検索クエリ `source:fsxn @attributes.result:Failure` で該当イベントが表示される, THE Datadog_Logs_UI SHALL 各イベントに `@attributes.user`（空文字でない）, `@attributes.path`（空文字でない）, `@attributes.client_ip`（空文字でない）の3フィールドを含む追跡可能な情報を表示する
4. WHEN デモシナリオ1の実行が完了する, THE E2E_Test SHALL 不正アクセス検知結果のスクリーンショット（Datadog Logs UIに該当イベントが表示されている画面を含む）を Screenshot_Directory に `datadog-unauthorized-access.png` として保存する
5. IF Lambda_Shipper がアクセス失敗イベントの Datadog への配信に失敗する, THEN THE Lambda_Shipper SHALL CloudWatch Logs にエラーログを出力し、該当イベントを Dead Letter Queue に送信する

### Requirement 7: スクリーンショットの配置と管理

**User Story:** As a プロジェクト管理者, I want to 全てのスクリーンショットを適切なディレクトリに配置する, so that ドキュメントから参照可能な状態で管理できる。

#### Acceptance Criteria

1. THE Screenshot_Directory SHALL `docs/screenshots/` パスに存在する
2. WHEN スクリーンショットが保存される, THE E2E_Test SHALL ファイル名にプレフィックス `datadog-` と内容を示すサフィックスを付与し、以下の5ファイルを生成する: `datadog-logs-arrival.png`, `datadog-pipeline-config.png`, `datadog-facets-config.png`, `datadog-dashboard.png`, `datadog-unauthorized-access.png`
3. WHEN 全てのスクリーンショットが保存される, THE Screenshot_Directory SHALL 上記5ファイルを全て含み、各ファイルのサイズが 1KB 以上であること
4. THE E2E_Test SHALL スクリーンショットを PNG 形式で保存する
5. IF スクリーンショットの保存に失敗した場合, THEN THE E2E_Test SHALL 失敗したファイル名と失敗理由を標準エラー出力に記録し、処理を中断する

### Requirement 8: 動作確認結果ドキュメントの作成

**User Story:** As a プロジェクト管理者, I want to 動作確認結果を構造化されたドキュメントに記録する, so that 検証の再現性と監査証跡を確保できる。

#### Acceptance Criteria

1. THE Verification_Results_Document SHALL `docs/ja/verification-results-datadog.md` パスに Markdown 形式で作成される
2. WHEN Verification_Results_Document が作成される, THE Verification_Results_Document SHALL 検証日時（ISO 8601 形式: YYYY-MM-DDTHH:MM:SS+09:00）、検証環境（AWS リージョン、CloudFormation スタック名）、検証者情報（氏名およびロール）を含むヘッダーセクションを持つ
3. WHEN Verification_Results_Document が作成される, THE Verification_Results_Document SHALL 各検証ステップについて、ステップ番号、ステップ名、実行結果（成功/失敗）、実行コマンド（コードブロック形式）、および出力結果（最大200行以内に省略）を含む
4. WHEN Verification_Results_Document が作成される, THE Verification_Results_Document SHALL スクリーンショットへの相対パス参照を Markdown 画像リンク形式で含む
5. WHEN Verification_Results_Document が作成される, THE Verification_Results_Document SHALL 検出された問題点と対処方法のセクションを含む
6. IF 検証において問題が検出されなかった場合, THEN THE Verification_Results_Document SHALL 問題点セクションに「問題なし」と明記する

### Requirement 9: セットアップガイドの日英2言語対応確認

**User Story:** As a プロジェクト管理者, I want to セットアップガイドが日英で完全に対応していることを確認する, so that 両言語のユーザーが同等の情報にアクセスできることを保証できる。

#### Acceptance Criteria

1. WHEN Setup_Guide の日本語版と英語版を比較する, THE E2E_Test SHALL 両ドキュメントの見出し構造が一致していること（見出しレベル（h1〜h6）の数・順序・階層が同一であること）を確認する
2. WHEN Setup_Guide の日本語版と英語版を比較する, THE E2E_Test SHALL 両ドキュメントのコードブロックが同一であること（コードブロックの数が等しく、出現順に内容がバイト単位で一致すること）を確認する
3. WHEN Setup_Guide の日本語版と英語版を比較する, THE E2E_Test SHALL 両ドキュメントのパラメータテーブルが同一の情報を含むこと（テーブルの数・行数・列数が等しく、パラメータ名およびコード値のセルが一致すること）を確認する
4. IF Setup_Guide の日英間に差異が検出された場合, THEN THE E2E_Test SHALL 差異の内容（対象ファイルパス、差異が発生したセクション名、差異の種別（見出し/コードブロック/テーブル）、および期待値と実際値）を Verification_Results_Document に記録する
5. WHEN 2言語対応確認が完了する, THE Verification_Results_Document SHALL 確認結果（合格/不合格）、比較対象ファイルの一覧、確認した見出し数・コードブロック数・テーブル数、および検出された差異件数を記録する
6. WHEN E2E_Test が比較対象の Setup_Guide ファイルを特定する, THE E2E_Test SHALL 各ベンダーディレクトリ配下の docs/ja/ と docs/en/ に存在する setup-guide.md ファイルの全ペアを比較対象とする
7. IF 一方の言語にのみ Setup_Guide ファイルが存在し対応するもう一方の言語版が存在しない場合, THEN THE E2E_Test SHALL 当該ファイルを不合格として Verification_Results_Document に記録する
