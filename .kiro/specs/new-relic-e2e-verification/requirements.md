# Requirements Document

## Introduction

New Relic 統合の E2E（End-to-End）動作確認を実施し、セットアップガイドの新規作成、デモシナリオ3「クォータ閾値超過アラート」の実行、およびスクリーンショット付き検証結果ドキュメントを作成する。既存の Lambda 関数とCloudFormation テンプレートが正しく動作することを確認し、ユーザーが再現可能な手順書を整備する。

## Glossary

- **E2E_Verification_System**: New Relic 統合の動作確認プロセス全体（デプロイ、テストイベント送信、ログ到着確認、NRQL クエリ実行、アラート設定を含む）
- **Lambda_Shipper**: `integrations/new-relic/lambda/handler.py` に実装された FSxN 監査ログ配信 Lambda 関数
- **New_Relic_Log_API**: New Relic Log API v1 エンドポイント（US: `https://log-api.newrelic.com/log/v1`、EU: `https://log-api.eu.newrelic.com/log/v1`）
- **Setup_Guide**: `integrations/new-relic/docs/{ja,en}/setup-guide.md` に配置するバイリンガルセットアップガイド
- **Verification_Report**: `docs/ja/verification-results-new-relic.md` に記録する動作確認結果ドキュメント
- **Screenshot_Assets**: `docs/screenshots/` ディレクトリに配置するスクリーンショット画像ファイル
- **Demo_Scenario_3**: `docs/ja/demo-scenarios.md` のシナリオ3「クォータ閾値超過アラート」
- **NRQL**: New Relic Query Language（New Relic のデータ問い合わせ言語）
- **Alert_Condition**: New Relic Alerts で定義する閾値ベースの通知条件

## Requirements

### Requirement 1: Lambda 関数のデプロイとテストイベント送信

**User Story:** As a DevOps エンジニア, I want to deploy the New Relic Lambda shipper and send test events, so that I can verify the integration pipeline works end-to-end.

#### Acceptance Criteria

1. WHEN the CloudFormation stack `fsxn-new-relic-integration` is deployed, THE E2E_Verification_System SHALL confirm the stack reaches `CREATE_COMPLETE` status with all resources provisioned
2. WHEN a test S3 event is sent to the Lambda_Shipper, THE Lambda_Shipper SHALL process the event and return a response with `statusCode` 200
3. WHEN the Lambda_Shipper processes a valid audit log file, THE Lambda_Shipper SHALL send logs to the New_Relic_Log_API and receive HTTP 202 response
4. IF the Lambda_Shipper encounters an error during processing, THEN THE Lambda_Shipper SHALL log the error to CloudWatch and route the failed event to the Dead Letter Queue
5. THE Verification_Report SHALL record the CloudFormation deploy output, Lambda invocation result, and CloudWatch log excerpts as evidence

### Requirement 2: New Relic Logs UI でのログ到着確認

**User Story:** As a DevOps エンジニア, I want to confirm audit logs arrive in New Relic Logs UI, so that I can verify the data pipeline delivers logs correctly.

#### Acceptance Criteria

1. WHEN the Lambda_Shipper successfully ships logs, THE E2E_Verification_System SHALL confirm log entries appear in New Relic Logs UI within 2 minutes
2. WHEN viewing logs in New Relic Logs UI, THE E2E_Verification_System SHALL verify that `source:fsxn-ontap` filter returns the shipped log entries
3. THE E2E_Verification_System SHALL verify that each log entry contains the attributes: `source`, `service`, `event_type`, `svm`, `user`, `client_ip`, `operation`, `path`, and `result`
4. THE Screenshot_Assets SHALL include a screenshot of the New Relic Logs UI showing the arrived FSxN audit log entries with visible attributes
5. THE Verification_Report SHALL record the timestamp of log arrival, the number of log entries received, and any attribute mapping discrepancies

### Requirement 3: NRQL クエリ実行と検証

**User Story:** As a DevOps エンジニア, I want to execute NRQL queries against the shipped logs, so that I can demonstrate querying capabilities for monitoring and alerting.

#### Acceptance Criteria

1. WHEN NRQL queries are executed against shipped logs, THE E2E_Verification_System SHALL confirm that `SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago` returns a non-zero count
2. WHEN a faceted NRQL query is executed, THE E2E_Verification_System SHALL confirm that `SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET operation SINCE 1 hour ago` returns results grouped by operation type
3. THE Setup_Guide SHALL include at least 5 example NRQL queries covering: log count, operation breakdown, user activity, error filtering, and time-series visualization
4. THE Screenshot_Assets SHALL include a screenshot of the New Relic Query Builder showing NRQL query results with chart visualization
5. THE Verification_Report SHALL record each executed NRQL query, its result, and execution timestamp

### Requirement 4: Alert Condition 設定と検証

**User Story:** As a DevOps エンジニア, I want to configure New Relic Alert Conditions for FSxN audit events, so that anomalous activity triggers notifications.

#### Acceptance Criteria

1. THE E2E_Verification_System SHALL create an Alert_Condition in New Relic that triggers when `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure'` exceeds a defined threshold within a 5-minute window
2. THE Setup_Guide SHALL document the step-by-step procedure for creating Alert Conditions including: policy creation, NRQL condition definition, threshold configuration, and notification channel setup
3. THE Screenshot_Assets SHALL include screenshots of: Alert Policy creation screen, NRQL Alert Condition configuration, threshold settings, and notification channel configuration
4. IF the Alert_Condition threshold is exceeded during testing, THEN THE E2E_Verification_System SHALL confirm that a notification is generated
5. THE Verification_Report SHALL record the Alert Condition configuration details and test trigger results

### Requirement 5: デモシナリオ3「クォータ閾値超過アラート」の実行

**User Story:** As a DevOps エンジニア, I want to execute Demo Scenario 3 (quota threshold exceeded alert), so that I can validate the complete workflow from FSx ONTAP event to New Relic alert.

#### Acceptance Criteria

1. WHEN Demo_Scenario_3 is executed, THE E2E_Verification_System SHALL simulate a quota soft-limit exceeded event by writing a large file to the FSx ONTAP mount point
2. WHEN the `wafl.quota.softlimit.exceeded` EMS event is generated, THE E2E_Verification_System SHALL confirm the event is captured in the S3 audit log bucket
3. WHEN the EMS event reaches New Relic via the Lambda_Shipper, THE E2E_Verification_System SHALL confirm the log entry appears in New Relic Logs UI with `event_type` containing `wafl.quota`
4. WHEN the NRQL query `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND event_type LIKE 'wafl.quota%' SINCE 1 hour ago` is executed, THE E2E_Verification_System SHALL return a non-zero result
5. THE Verification_Report SHALL record the complete execution timeline: file write timestamp, EMS event timestamp, S3 object creation timestamp, Lambda invocation timestamp, and New Relic log arrival timestamp

### Requirement 6: セットアップガイドの新規作成（日本語）

**User Story:** As a DevOps エンジニア, I want a comprehensive Japanese setup guide for the New Relic integration, so that Japanese-speaking users can deploy and configure the integration independently.

#### Acceptance Criteria

1. THE Setup_Guide SHALL be created at `integrations/new-relic/docs/ja/setup-guide.md`
2. THE Setup_Guide SHALL include the following sections: 概要、前提条件、Step 1（New Relic License Key の準備）、Step 2（S3 Access Point の設定）、Step 3（CloudFormation デプロイ）、Step 4（New Relic 側の設定）、Step 5（動作確認）、トラブルシューティング
3. THE Setup_Guide SHALL include all CloudFormation parameter descriptions with a parameter table
4. THE Setup_Guide SHALL include New Relic region endpoint information (US and EU)
5. THE Setup_Guide SHALL reference Screenshot_Assets for New Relic UI configuration steps
6. THE Setup_Guide SHALL include troubleshooting procedures for: logs not arriving, rate limit errors, and authentication failures

### Requirement 7: セットアップガイドの新規作成（英語）

**User Story:** As a DevOps engineer, I want a comprehensive English setup guide for the New Relic integration, so that English-speaking users can deploy and configure the integration independently.

#### Acceptance Criteria

1. THE Setup_Guide SHALL be created at `integrations/new-relic/docs/en/setup-guide.md`
2. THE Setup_Guide SHALL mirror the same heading structure and section order as the Japanese version at `integrations/new-relic/docs/ja/setup-guide.md`
3. THE Setup_Guide SHALL contain identical code examples and CLI commands as the Japanese version
4. THE Setup_Guide SHALL use natural English expressions rather than direct translations from Japanese
5. THE Setup_Guide SHALL reference the same Screenshot_Assets as the Japanese version

### Requirement 8: スクリーンショット配置と管理

**User Story:** As a ドキュメント管理者, I want screenshots organized in a dedicated directory, so that documentation references are consistent and maintainable.

#### Acceptance Criteria

1. THE Screenshot_Assets SHALL be stored in `docs/screenshots/new-relic/` directory
2. THE Screenshot_Assets SHALL use kebab-case file naming: `{step-description}.png` (e.g., `logs-ui-arrival.png`, `nrql-query-result.png`, `alert-condition-config.png`)
3. THE Screenshot_Assets SHALL include at minimum: Logs UI showing arrived logs, NRQL Query Builder with results, Alert Condition configuration, and Alert Policy overview
4. THE Setup_Guide SHALL reference screenshots using relative paths from the guide location
5. THE Verification_Report SHALL embed or reference all screenshots captured during the E2E verification process

### Requirement 9: 動作確認結果ドキュメントの作成

**User Story:** As a プロジェクト管理者, I want a verification results document, so that the E2E test execution is recorded as evidence for project completion.

#### Acceptance Criteria

1. THE Verification_Report SHALL be created at `docs/ja/verification-results-new-relic.md`
2. THE Verification_Report SHALL include the following sections: 実施概要、環境情報、テスト結果サマリー、各ステップの詳細結果、スクリーンショット一覧、既知の問題と対応策
3. THE Verification_Report SHALL record the execution environment: AWS account ID (masked), region, FSx ONTAP file system ID, New Relic account ID (masked), and stack name
4. THE Verification_Report SHALL include a pass/fail status for each acceptance criterion tested
5. WHEN all verification steps are completed, THE Verification_Report SHALL include a final conclusion stating whether the New Relic integration is production-ready
