# FSx for ONTAP S3 Access Points の代替トリガーとしての CloudTrail データイベント

## サマリー

**CloudTrail データイベントは FSx for ONTAP S3 Access Points で動作します。** これにより、プライマリ統合で使用しているポーリングパターンに代わるイベント駆動型の代替手段が提供されます。

ただし、ポーリングパターン（EventBridge Scheduler + チェックポイント）が本プロジェクトの**推奨プライマリアプローチ**として維持されます。理由:

1. CloudTrail データイベントはコストが追加される（$0.10 / 100,000 イベント）
2. ポーリングパターンの方がデプロイとデバッグが簡単
3. CloudTrail は EventBridge への配信に 5-15 分のレイテンシーが追加される
4. NetApp Workload Factory の Journal table 機能が既にこの CloudTrail パターンを使用しており、重複する必要がない

## エビデンス: FSx for ONTAP S3 AP に対する CloudTrail サポート

### AWS ドキュメント

CloudTrail は標準 S3 Access Points に対する S3 データイベント（GetObject, PutObject, DeleteObject 等）をサポートしています。FSx for ONTAP S3 Access Points は AWS コントロールプレーンから見ると標準 S3 Access Points として表示されるため、CloudTrail データイベントはこれらを通じた操作をキャプチャします。

CloudTrail の `resources.ARN` フィールドには Access Point ARN が含まれます:
```
arn:aws:s3:<region>:<account-id>:accesspoint/<access-point-name>/object/<key>
```

### NetApp Workload Factory による検証

NetApp の Workload Factory 製品は、**Journal table** 機能でまさにこのパターンを使用しています:
- CloudTrail データイベントが FSx for ONTAP Access Points 上の S3 API コールをキャプチャ
- イベントは CloudTrail → EventBridge → 処理パイプラインへ流れる
- これにより本番環境でパターンが動作することが確認されている

### Journal Table vs ポーリング: 使い分け

| パターン | ソースデータ | ユースケース |
|---------|------------|----------|
| **Journal table / CloudTrail** | S3 Access Point データプレーン操作（GetObject, PutObject 等） | S3 API 経由でファイルにアクセスした人を追跡 |
| **ポーリング（本プロジェクト）** | ONTAP が生成した監査ログファイル（FSx ボリューム上） | ONTAP 監査ログをオブザーバビリティバックエンドに配信 |

S3 Access Point データプレーン操作の履歴（どの Lambda やユーザーがどのキーに対して GetObject を呼び出したか）が必要な場合は Journal table / CloudTrail データイベントを使用してください。プライマリソースが ONTAP 生成の監査ログファイル（ONTAP の監査サブシステムが書き込む SMB/NFS ファイルアクセスイベント）で、それを Grafana、Datadog、Splunk などのオブザーバビリティバックエンドに配信したい場合はポーリングパターンを使用してください。

参考: [NetApp Workload Factory — Journal Table Setup](https://docs.netapp.com/us-en/workload-fsx-ontap/setup-journal-table.html)

## アーキテクチャ: CloudTrail → EventBridge → Lambda

```
FSx for ONTAP S3 Access Point
        │
        ▼ (GetObject/PutObject via S3 API)
   CloudTrail Trail
   (S3 data events)
        │
        ▼ (5-15 min latency)
   EventBridge Rule
   (detail-type: "AWS API Call via CloudTrail")
        │
        ▼
   Lambda (log shipper)
        │
        ▼
   Grafana Cloud (OTLP Gateway)
```

## CloudFormation 例

以下のスニペットは、FSx for ONTAP S3 Access Point に対する CloudTrail データイベントを設定し、EventBridge 経由で Lambda 関数にルーティングする方法を示します:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >
  CloudTrail data events trigger for FSx for ONTAP S3 Access Point.
  Alternative to EventBridge Scheduler polling pattern.

Parameters:
  S3AccessPointArn:
    Type: String
    Description: ARN of the FSx for ONTAP S3 Access Point
    # Example: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap

  LogShipperFunctionArn:
    Type: String
    Description: ARN of the log shipper Lambda function

  CloudTrailBucketName:
    Type: String
    Description: S3 bucket for CloudTrail log delivery

Resources:
  # --- CloudTrail Trail with S3 Data Events ---
  AuditTrail:
    Type: AWS::CloudTrail::Trail
    Properties:
      TrailName: fsxn-s3ap-data-events
      IsLogging: true
      S3BucketName: !Ref CloudTrailBucketName
      EnableLogFileValidation: true
      IsMultiRegionTrail: false
      EventSelectors:
        - ReadWriteType: ReadOnly
          IncludeManagementEvents: false
          DataResources:
            - Type: AWS::S3::Object
              Values:
                - !Sub "${S3AccessPointArn}/"

  # --- EventBridge Rule ---
  # Matches CloudTrail S3 data events for GetObject on the access point
  S3DataEventRule:
    Type: AWS::Events::Rule
    Properties:
      Name: fsxn-s3ap-object-access
      Description: Trigger Lambda on S3 GetObject via FSx for ONTAP Access Point
      State: ENABLED
      EventPattern:
        source:
          - aws.s3
        detail-type:
          - "AWS API Call via CloudTrail"
        detail:
          eventSource:
            - s3.amazonaws.com
          eventName:
            - GetObject
            - PutObject
          requestParameters:
            bucketName:
              - !Select [5, !Split [":", !Ref S3AccessPointArn]]
      Targets:
        - Id: LogShipperLambda
          Arn: !Ref LogShipperFunctionArn

  # --- Lambda Permission for EventBridge ---
  LambdaInvokePermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref LogShipperFunctionArn
      Action: lambda:InvokeFunction
      Principal: events.amazonaws.com
      SourceArn: !GetAtt S3DataEventRule.Arn
```

## コスト比較

| アプローチ | トリガーコスト | レイテンシー | 複雑度 |
|----------|-------------|---------|------|
| EventBridge Scheduler（ポーリング） | ~$0.00（5分に1回の呼び出し） | 最大5分（設定可能） | 低 |
| CloudTrail データイベント | $0.10/100K イベント + Trail ストレージ | 5-15分（CloudTrail 配信） | 中 |
| S3 Event Notifications | FSx for ONTAP S3 AP では非対応 | — | — |

## CloudTrail トリガーを使用すべき場合

以下の場合に CloudTrail アプローチを検討してください:
- S3 API 経由でファイルに**誰が**アクセスしたかの監査証跡が必要（CloudTrail は呼び出し元 ID を提供）
- コンプライアンスのために既に CloudTrail データイベントを有効化している
- ポーリングなしのイベント駆動処理が必要（CloudTrail レイテンシーを許容）
- NetApp Workload Factory の Journal table パターンの上に構築している

## ポーリングを使用すべき場合（推奨デフォルト）

以下の場合は EventBridge Scheduler ポーリングパターンを維持してください:
- 最もシンプルで低コストなデプロイが必要
- 予測可能で設定可能なレイテンシーが必要（rate(1 minute) ～ rate(15 minutes)）
- CloudTrail の呼び出し元 ID メタデータが不要
- 高ボリュームでの CloudTrail データイベントコストを避けたい

## NetApp Workload Factory Journal Table パターン

NetApp の Workload Factory は CloudTrail ベースパターンのマネージド版を提供します:
- CloudTrail Trail、EventBridge ルール、処理パイプラインを自動デプロイ
- FSx for ONTAP S3 Access Points 上のユーザーアクセスイベントとオブジェクト操作をキャプチャ
- 結果をクエリ可能な「Journal table」（DynamoDB）に保存
- 監視用の CloudWatch ロググループを含む

既に Workload Factory を使用している場合は、並列の CloudTrail パイプラインを構築するのではなく、Journal table の出力をデータソースとして活用することを検討してください。

## 制限事項

1. **レイテンシー**: CloudTrail は EventBridge へのイベント配信に 5-15 分の遅延がある
2. **コスト**: 100,000 データイベントあたり $0.10（高ボリュームでは大きくなる可能性）
3. **スコープ**: S3 API 操作のみキャプチャ — NFS/SMB ファイルアクセスはキャプチャしない
4. **重複排除**: CloudTrail は重複イベントを配信する可能性がある。Lambda は冪等に処理する必要がある
5. **Access Point ネットワークオリジン**: 外部呼び出し元からのイベントを CloudTrail がキャプチャするには、S3 Access Point が Internet-origin として設定されている必要がある

## 参考リンク

- [AWS CloudTrail — S3 データイベントのログ記録](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
- [AWS CloudTrail — 高度なイベントセレクター](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/filtering-data-events.html)
- [Amazon S3 — Access Points の監視とログ記録](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-monitoring-logging.html)
- [NetApp Workload Factory — Journal Table Setup](https://docs.netapp.com/us-en/workload-fsx-ontap/setup-journal-table.html)
- [FSx for ONTAP — CloudTrail による監視](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/logging-using-cloudtrail-win.html)


## サービスフィードバックサマリー

### 観測された顧客ニーズ

- FSx for ONTAP S3 Access Points からのニアリアルタイム監査ログ配信
- CloudTrail データイベント配信よりも低いレイテンシー（検証で 5-15 分を観測）
- 高ボリュームワークロードでのポーリングよりも低い運用複雑度
- CloudTrail データイベントの $0.10/100K イベントコストなしのイベント駆動トリガー

### 現在のワークアラウンド

- EventBridge Scheduler ポーリング + SSM / DynamoDB チェックポイント
- ポーリング間隔は設定可能（デフォルト: 5分）
- アプリケーション側でリスト、読み取り、チェックポイント、リトライを管理

### トレードオフ分析

| アプローチ | レイテンシー | コスト | 複雑度 | 信頼性 |
|----------|---------|------|--------|--------|
| Scheduler ポーリング（本プロジェクト） | ≤ スケジュール間隔 | Lambda のみ | 中（アプリ側チェックポイント） | At-least-once + DLQ |
| CloudTrail データイベント → EventBridge | 5-15分（観測値） | $0.10/100K イベント + Lambda | 低（イベント駆動） | At-least-once |
| ネイティブオブジェクト通知（仮想） | ニアリアルタイム | TBD | 低 | TBD |

### 将来の改善可能性

FSx アタッチ S3 Access Points に対するネイティブ object-created スタイルのイベンティングまたは低レイテンシーデータプレーンイベント配信が実現すれば、監査ログ配信ユースケースの運用設計が簡素化され、アプリケーション側のポーリング、チェックポイント、重複防止ロジックの必要性が軽減されます。
