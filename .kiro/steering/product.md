# プロジェクト概要

## FSxN Observability Integrations

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、S3 Access Points 経由で各 Observability ベンダーへサーバーレスに配信するパターン集。

## コアコンセプト

- **S3 Access Point**: FSx ONTAP 監査ログへのアクセス制御レイヤー
- **サーバーレス配信**: Lambda / Firehose による EC2 不要のログ転送
- **マルチベンダー対応**: 統一アーキテクチャで複数ベンダーをサポート
- **Infrastructure as Code**: CloudFormation テンプレートによる再現可能なデプロイ

## 差別化ポイント

既存の AWS ブログ（Splunk 統合）は EC2 ベース（syslog-ng + Universal Forwarder）。
本プロジェクトは完全サーバーレスの代替パターンを提供する。

## ターゲットユーザー

- FSx for ONTAP を使用している AWS ユーザー
- 監査ログを外部 Observability プラットフォームに送信したいユーザー
- サーバーレスアーキテクチャを好むユーザー
