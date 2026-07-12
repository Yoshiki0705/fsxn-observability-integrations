# 保持ポリシーマトリクス

🌐 **日本語**（このページ） | [English](../en/retention-policy-matrix.md)

## 概要

本マトリクスは、規制上の保持要件をベンダー固有の設定にマッピングします。適用される規制に基づいて、FSx for ONTAP 監査ログの最小保持期間を決定するために使用してください。

> **ガバナンス上の注意**
>
> 本マトリクスはパイプライン設定のための技術的な認識を提供するものです。法的またはコンプライアンス上のアドバイスを構成するものではありません。拘束力のある規制解釈および組織固有の保持義務については、コンプライアンスチームに相談してください。

## 規制上の保持要件

| 規制 | 適用範囲 | 最小保持期間 | 備考 |
|------|---------|-------------|------|
| **APPI**（日本） | 個人情報取扱記録 | 明示的な最小期間なし；「必要な期間」 | 利用目的に沿った保持が必要 |
| **FISC ガイドライン**（日本金融） | 金融システム監査証跡 | 7 年（推奨） | 金融機関等コンピュータシステムの安全対策基準 |
| **ISMAP**（日本政府クラウド） | クラウドサービス監査ログ | 最低 1 年 | ISMAP 管理基準 |
| **J-SOX**（日本） | 内部統制証拠 | 7 年 | 金融商品取引法 |
| **GDPR**（EU） | 個人データ処理記録 | 明示的な最小期間なし；「必要以上に長くない」 | データ最小化原則が適用 |
| **SOC 2** | サービス組織統制 | 1 年（監査期間） | 通常 12 ヶ月の観察期間 |
| **PCI DSS** | 決済カードデータアクセス | 1 年（即時利用可能）；1 年アーカイブ | 要件 10.7 |
| **HIPAA**（米国医療） | PHI アクセスログ | 6 年 | 45 CFR 164.530(j) |
| **SEC Rule 17a-4**（米国金融） | 電子記録 | 記録種別により 3〜6 年 | ブローカーディーラー要件 |

## ベンダー保持設定

| ベンダー | 無料枠の保持期間 | 有料最小 | 最大 | 設定方法 |
|---------|----------------|---------|------|---------|
| **Datadog** | 15 日 | 15 日 | カスタム（Online Archive） | Organization Settings > Logs > Indexes |
| **New Relic** | 30 日 | 30 日 | カスタム | Data Management > Retention |
| **Splunk** | N/A（セルフホスト） | 設定可能 | 無制限 | indexes.conf: frozenTimePeriodInSecs |
| **Grafana Cloud** | 14 日 | 14 日 | 365 日 | Loki retention_period per tenant |
| **Elastic** | 14 日（トライアル） | ILM 設定可能 | 無制限 | Index Lifecycle Management policy |
| **Dynatrace** | 35 日 | 35 日 | 10 年（Grail） | Settings > Log Monitoring > Retention |
| **Sumo Logic** | 7 日 | 30 日 | 5000 日 | Partition retention settings |
| **Honeycomb** | 60 日 | 60 日 | カスタム | Dataset settings |
| **OTel Collector** | N/A（パススルー） | N/A | N/A | バックエンド依存 |

## 規制別ベンダーマッピング

### FISC / J-SOX（7 年）

| ベンダー | 達成可能？ | 方法 |
|---------|-----------|------|
| Datadog | はい | Online Archive（コールドストレージ） |
| Splunk | はい | Frozen bucket を S3 へ |
| Elastic | はい | ILM: hot > warm > cold > frozen (S3) |
| Dynatrace | はい | Grail ストレージ（最大 10 年） |
| Sumo Logic | はい | Partition retention 最大 5000 日 |
| Grafana/Honeycomb/New Relic | 部分的 | 長期保存は別途 S3 にアーカイブ |

**7 年保持の推奨パターン**：
```
Lambda -> Vendor (hot, 30-90 days) -> Vendor archive OR S3 Glacier (7 years)
```

### ISMAP / SOC 2（1 年）

すべてのベンダーが有料プランで 1 年保持をサポートしています。無料枠では不十分です。

| ベンダー | 1 年保持の有料プラン | 推定コスト（10 GB/月） |
|---------|---------------------|----------------------|
| Datadog | Standard プラン | 約 $150/月 |
| Sumo Logic | Professional | 約 $108/月 |
| Elastic | Standard | 約 $95/月 |
| Dynatrace | Standard (Grail) | 約 $25/月（DDU ベース） |
| Grafana Cloud | Pro プラン | 約 $50/月 |

### APPI / GDPR（目的限定）

固定の最小期間なし — 記載された目的に必要な期間のみ保持。

**推奨アプローチ**：
1. 目的を定義：「セキュリティ調査およびコンプライアンス監査」
2. 保持期間を設定：90 日 hot + 1 年アーカイブ（一般的）
3. 保持期間後の自動削除を実装
4. 保持決定を文書化し、年次でレビュー

## 長期保持のためのデュアルパスアーキテクチャ

1 年超の保持が必要な規制には、デュアルパスを実装します：

```
FSx for ONTAP -> Lambda -> +-> Vendor (hot, 30-90 days) -- リアルタイムクエリ
                       +-> S3 (archive, 7 years) -- コンプライアンス証拠
                               |
                               +-> S3 Standard (0-90 days)
                               +-> S3 Standard-IA (90 days - 1 year)
                               +-> S3 Glacier Deep Archive (1-7 years)
```

S3 Lifecycle の CloudFormation スニペット：
```yaml
AuditArchiveBucket:
  Type: AWS::S3::Bucket
  Properties:
    LifecycleConfiguration:
      Rules:
        - Id: TransitionToIA
          Status: Enabled
          Transitions:
            - StorageClass: STANDARD_IA
              TransitionInDays: 90
            - StorageClass: DEEP_ARCHIVE
              TransitionInDays: 365
          ExpirationInDays: 2555  # 7 years
```

## 実装チェックリスト

- [ ] 組織に適用される規制を特定
- [ ] 最小保持期間を決定（上記マトリクスを使用）
- [ ] ベンダー保持設定を構成（必要に応じて有料プラン）
- [ ] ベンダー最大を超える場合は S3 アーカイブパスを実装
- [ ] コスト最適化のための S3 Lifecycle ルールを設定
- [ ] 改ざん防止が必要な場合は S3 Object Lock を有効化
- [ ] 保持ポリシーとレビュースケジュールを文書化
- [ ] 保持期限接近のアラートを設定

## 関連ドキュメント

- [データ分類ガイド](data-classification.md)
- [データレジデンシーマトリクス](data-residency.md)
- [ガバナンス & コンプライアンス](governance-and-compliance.md)
- [Pipeline SLO](pipeline-slo.md)
