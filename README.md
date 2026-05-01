# DEA x ADK x Context Engineering: 自律パイプライン構築エージェント

「GCSに置いたPDFから財務データを抽出・構造化・分析するBigQueryパイプラインを作って」という自然言語の指示から、エージェントが自律的にパイプラインを構築・デバッグ・完成させるデモです。

詳細は [article_draft.md](article_draft.md) を参照してください。

## 前提条件

- GCPプロジェクト（課金有効）
- 以下のAPIが有効化済み:
  - BigQuery API / BigQuery Connection API
  - Dataform API
  - Document AI API
  - Vertex AI API
  - Agent Engine API
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- Python 3.11+
- [ADK CLI](https://google.github.io/adk-docs/) (`pip install google-adk[extensions]`)
- Terraform

## セットアップ

### 1. 依存関係のインストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 環境変数の設定

```bash
cp demo_agent/.env.example demo_agent/.env
# demo_agent/.env を編集して自分のプロジェクト情報を記入
```

### 3. GCPインフラの構築

```bash
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集

terraform init
terraform apply
```

### 4. PDFのアップロード

```bash
export GCS_BUCKET=alphabet-reports-<your-project-id>
bash pdf-uploading.sh
```

### 5. Memory Bank のセットアップ

```bash
python setup_memory_bank.py
# 出力された AGENT_ENGINE_ID を demo_agent/.env に記入
```

### 6. Dataformワークスペースの作成

GCPコンソールで Dataform > リポジトリ `dea-pipeline-repo` を開き、ワークスペース `dea-workspace` を作成。

## 実行

```bash
adk web --memory_service_uri=agentengine://$AGENT_ENGINE_ID demo_agent
```

`http://localhost:8000` を開き、例えば以下のように指示します:

> GCSバケットにあるAlphabet社の決算PDFを解析して、財務データを構造化テーブルに抽出するパイプラインを作ってください
