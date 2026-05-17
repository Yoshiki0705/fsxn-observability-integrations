# 検知ユースケース

## イベントソース選択マトリクス

| 検知ユースケース | 最適ソース | 理由 | レイテンシ |
|-------------------|-------------|-----|---------|
| ランサムウェア暗号化挙動 | EMS (ARP) | ONTAP ネイティブ ML ベース検知 | リアルタイム (webhook) |
| 大量ファイル削除 | Audit Logs or FPolicy | Audit はニアリアルタイム、FPolicy はリアルタイム | 分 / 秒 |
| 異常な読み取りボリューム | Audit Logs | ポリシー依存、ボリューム大 | 分 |
| 不正アクセス試行 | Audit Logs | 失敗アクセスイベント (Result: Failure) | 分 |
| リアルタイムファイルブロック / DLP | FPolicy | プロトコルレベルインターセプト | サブ秒 |
| クォータ閾値超過 | EMS | ONTAP ネイティブクォータ監視 | リアルタイム (webhook) |
| 不審なユーザー行動 | FPolicy + Audit Logs | リアルタイム操作と履歴パターンの相関 | 秒 + 分 |
| 権限変更 | Audit Logs | SACL/ACL 変更イベント | 分 |

## ソース特性

| ソース | レイテンシモデル | ボリューム | 最適用途 |
|--------|--------------|--------|----------|
| ファイルアクセス監査ログ | ニアリアルタイム (Scheduler 頻度 + rotation 間隔) | 高 (特に read auditing 有効時) | コンプライアンス、フォレンジック、パターン分析 |
| EMS Webhook | リアルタイム (HTTPS push) | 低 (重要イベントのみ) | セキュリティアラート、運用監視 |
| FPolicy | リアルタイム (TCP ストリーム) | 中〜高 (全ファイル操作) | DLP、リアルタイム監視、不審行動検知 |

## ユースケース別 Datadog Monitor 例

### ランサムウェア検知 (ARP + EMS)

```
Query: source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.parameters.state:attack-detected
Threshold: critical > 0
Action: PagerDuty + Slack + 影響ボリュームのスナップショット
```

### 大量アクセス失敗 (Audit Logs)

```
Query: source:fsxn @attributes.result:Failure
Threshold: critical > 10 in 5 minutes
Action: ユーザー + クライアント IP の調査
```

### 異常なファイル削除率 (FPolicy)

```
Query: source:fsxn-fpolicy @attributes.operation:delete
Threshold: warning > 50 in 5 minutes, critical > 200 in 5 minutes
Action: ユーザー ID との相関
```

### 機密パスへのアクセス (Audit Logs)

```
Query: source:fsxn @attributes.path:"/vol/data/confidential/*"
Threshold: warning > 0 (機密パスへのアクセス)
Action: ログレビュー + ユーザー確認
```

## 相関パターン

高度な検知のため、ソース間で相関分析:

1. **ARP アラート + FPolicy 大量操作** — ファイルレベルの詳細でランサムウェア活動を確認
2. **アクセス失敗スパイク + 新規 IP からの成功アクセス** — 認証情報漏洩の可能性
3. **クォータ警告 + 単一ユーザーからの大量書き込み** — データ持ち出しまたは不正利用の可能性
