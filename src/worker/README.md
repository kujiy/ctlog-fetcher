# CT Log Fetcher Worker

Pythonワーカーは、証明書Transparencyログ（CT Log）から日本関連証明書を分散収集し、Manager APIへアップロードするためのツールです。

---

## 必要要件

- Python 3.11 以上
- `requests`, `python-dotenv` など（`requirements.txt` 参照）

---

## インストール

```bash
pip install -r requirements.txt
```

---

## 起動方法

### 1. コマンドライン実行

```bash
python src/worker/worker.py [--proxies http://proxy1,http://proxy2] [--worker-name 名前] [--manager http://manager-url] [--debug]
```

### 2. 環境変数による設定

すべてのオプションは環境変数でも指定できます（CLI引数が優先）。

| 環境変数      | 説明                                 | 例                                  |
|:------------- |:------------------------------------ |:----------------------------------- |
| PROXIES       | プロキシURL（カンマ区切り複数可）    | `http://proxy1,http://proxy2`       |
| WORKER_NAME   | ワーカー名                           | `my-worker`                         |
| MANAGER_URL   | Manager APIのベースURL               | `http://localhost:8000`             |
| DEBUG         | デバッグログ有効化（1/true/yes）     | `1`                                 |

例:
```bash
export PROXIES="http://proxy1,http://proxy2"
export WORKER_NAME="my-worker"
export MANAGER_URL="http://localhost:8000"
export DEBUG=1
python src/worker/worker.py
```

---

## オプション一覧

- `--proxies`: プロキシURL（カンマ区切りで複数指定可）
- `--worker-name`: ワーカー名（省略時は自動生成）
- `--manager`: Manager APIのベースURL
- `--debug`: デバッグログ有効化

---

## 主な機能

- Manager APIからジョブを取得し、CTログから証明書をバッチ取得
- 日本関連証明書のみ抽出しアップロード
- 進捗・完了・エラーをAPI経由で報告
- 失敗したリクエストはpendingディレクトリに保存し自動リトライ
- Ctrl+C等で安全に停止し、未完了ジョブはresumeリクエスト送信
- .envファイル対応

---

## アーキテクチャ概要

- マルチスレッド（ThreadPoolExecutor）で複数カテゴリのジョブを並列処理
- 進捗状況をコンソールにリアルタイム表示
- 証明書パース・アップロード・エラーハンドリングを自動化

---

## トラブルシューティング

- 失敗したアップロードは `pending/` ディレクトリにJSONで保存され自動再送
- エラー詳細はログまたはManager APIのエンドポイントに送信
- ディスク容量・ネットワーク・Manager APIの疎通を確認

---

## 開発・テスト

- テストは `tests/` ディレクトリ参照
- 主要ロジックは `src/worker/worker.py` に集約

---

## ライセンス

MIT License
