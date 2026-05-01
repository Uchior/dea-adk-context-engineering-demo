# DEA × ADK × コンテキストエンジニアリングで作る自律パイプライン構築エージェント

## TL;DR

「GCSに置いたPDFから財務データを抽出・構造化・分析するBigQueryパイプラインを作って」——この一言から、エージェントが自律的にパイプラインを構築・デバッグ・完成させるデモを作りました。コンテキストエンジニアリングのテクニック（Suitcase pattern、Progressive Disclosure、Memory Profiles）を活用し、エージェント間の情報共有を最適化しています。

## このタスクの何が難しいか

今回エージェントにやらせたのは「非構造データ（PDF）→ 構造化データ（BQテーブル）→ AI分析」というEnd-to-Endの分析パイプライン構築です。人間のデータエンジニアがやっても、以下の理由でそれなりに骨が折れるタスクです。

- **複数のGCPサービスの連携**: GCS（PDF格納）→ Document AI（OCR/パース）→ BigQuery ML関数（LLM構造化抽出）→ Dataform（パイプラインオーケストレーション）を正しく繋ぐ必要がある
- **Document AIの出力構造の理解**: `ML.PROCESS_DOCUMENT` の出力JSONは `$.documentLayout.blocks` というネストされた構造で、ドキュメントを読んだだけでは正しいパース方法がわからない
- **BigQuery AI関数の制約**: `ML.GENERATE_TEXT` の出力は `$.candidates[0].content.parts[0].text` にネストされ、さらにMarkdownコードブロックで囲まれる。プロジェクトごとに利用可能なモデルも異なる
- **5層のSQLパイプライン設計**: Bronze（外部テーブル）→ Silver（Document AI処理）→ Gold（LLM構造化抽出）→ Gold（UNPIVOT）→ Gold（AI.KEY_DRIVERS分析）のメダリオンアーキテクチャ

これを「自然言語の指示だけ」でエージェントに構築させ、途中のエラーも自律的に修正させたのが今回のデモです。

## 何を作ったか

Alphabet（Google親会社）の決算PDF（Q1 2023, Q1 2024）をGCSに配置し、以下を自動化するマルチエージェントシステムを構築しました。

1. **DEA（Data Engineering Agent）がDataformパイプラインを自動生成**（Bronze→Silver→Gold medallion architecture）
2. **ADKエージェントがコンパイル・実行エラーを検知し、事実をDEAにフィードバック**
3. **DEAが自律的にデバッグ・修正**（接続ID誤り、存在しない関数、JSON構造の不一致などを自力で解決）
4. **分析結果をMemory Profilesに構造化記録し、エージェント間で共有**

## アーキテクチャ

```
ユーザー → [ADK orchestrator (Claude Opus 4.5)]
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
   [pipeline_agent] [analysis_agent] [memory_agent]
   DEA A2A通信       BQ結果確認       Memory Profiles
          │              │              │
          ▼              ▼              ▼
   DEA API           BigQuery       構造化プロファイル
   (パイプライン      (テーブル参照    (PipelineProfile,
    自動生成)          & 分析)         AnalysisProfile)
```

### エージェント構成

| エージェント | 役割 | ツール |
|---|---|---|
| **orchestrator** | State-aware routing でサブエージェントに振り分け | transfer_to_agent |
| **pipeline_agent** | DEAへの事実伝達、コンパイル/実行検証 | gather_workspace_context, send_instruction_to_dea, compile_dataform, get_latest_run, get_run_actions, read_dataform_file |
| **analysis_agent** | BQテーブルの確認・分析 | list_tables, preview_table, run_query |
| **memory_agent** | 構造化プロファイルの参照・要約 | retrieve_profiles |

## コンテキストエンジニアリング

### 1. Suitcase pattern — DEAに渡す前に現状をパッキング

`gather_workspace_context()` がDEAへの指示送信前に呼ばれ、以下を自動収集してまとめます：

- プロジェクト環境（project ID, region, 接続ID, データセット）
- 重要な制約（利用不可の関数、正しいendpoint名、接続ID形式）
- 既存のDataformファイル一覧
- 直近のコンパイル状態

```python
def gather_workspace_context() -> str:
    """DEAに指示を送る前に呼ぶ。ワークスペースの現状とプロジェクト制約を収集する。

    Suitcase pattern: DEAが正しいパイプラインを生成するために必要な情報を
    「正しい情報・正しい構造・正しいタイミング」でパッキングする。
    """
```

ポイントは **初回のみ** この全文をDEAに渡すこと。DEAとはConversationTokenでマルチターン会話が維持されるため、2回目以降のエラー修正では新しい事実（エラーメッセージ + ファイル内容）だけを送ります。

### 2. Progressive Disclosure — 段階的に情報をロード

pipeline_agentのワークフローは6つのPhaseに分かれており、各Phaseで必要な情報だけを取得します：

```
Phase 1: コンテキスト収集 → gather_workspace_context + retrieve_profiles
Phase 2: DEAへの初回指示 → コンテキスト全文 + ユーザー要件
Phase 3: コンパイル検証 → compile_dataform
Phase 4: エラー修正ループ → エラーメッセージ + ファイル内容のみ（制約は再送しない）
Phase 5: 実行結果確認 → get_latest_run + get_run_actions
Phase 6: プロファイル記録 → update_pipeline_profile
```

### 3. Memory Profiles — Pydanticスキーマで構造化記憶

```python
class PipelineProfile(BaseModel):
    dataform_files: str       # 生成されたファイル一覧
    pipeline_architecture: str # アーキテクチャ概要
    ai_functions_used: str     # 使用されたBigQuery AI関数
    compilation_status: str    # success/error/unknown
    last_errors: str           # 直近のエラー内容

class AnalysisProfile(BaseModel):
    quarters_analyzed: str     # 分析対象の四半期
    segments_analyzed: str     # 分析対象のセグメント
    key_findings: str          # 主要な発見
    revenue_highlights: str    # 収益ハイライト
    data_quality_notes: str    # データ品質の注記
```

pipeline_agentが書いたPipelineProfileをanalysis_agentやmemory_agentが参照でき、エージェント間で構造化されたコンテキストを共有できます。

## DEA連携: A2Aプロトコル

DEAとの通信はA2A（Agent-to-Agent）プロトコルで行います。

```python
DEA_ENDPOINT = f"{DEA_HOST}/v1/a2a/{DEA_TENANT}/v1/message:stream"

# A2A拡張ヘッダー
A2A_EXTENSIONS = [
    "gcpresource/v1",        # Dataformワークスペースの指定
    "conversationtoken/v1",  # マルチターン会話の維持
    "messagelevel/v1",
    "finishreason/v1",
    "pipelinecontext/v1",
    "instruction/v1",
]
```

**重要な設計判断**: pipeline_agentはデバッグの方針判断をしません。エラーメッセージ・ファイル内容・制約を事実としてDEAに渡し、修正プランニングはDEAに委ねます。

```
# pipeline_agentの原則
- あなたはSQLの修正方法を考えない
- DEAへの指示は「こう直して」ではなく
  「こういうエラーが出た。ファイル内容はこう。修正してください」の形
- 同じ情報を繰り返し送らない。新しい事実だけを送る
```

## 実際のデモフロー（ADKセッションログより）

デモセッションでは、エージェントが以下のエラーを自律的に検知・修正し、最終的に全アクション成功に至りました。

| Round | トリガー | 検知した問題 | DEAの修正 |
|-------|----------|-------------|-----------|
| 1 | 「パイプラインを修正して」 | 接続ID誤り (`us.ai-connection` → `us-central1.ai-connection`) + JSONパス不正 | 接続ID修正 + `$.candidates[0].content.parts[0].text` への変更 |
| 2 | 「確認と修正お願い」 | 実行エラー: `Function not found: SAFE_PARSE_JSON` | `SAFE_PARSE_JSON` → `JSON_VALUE` に修正 |
| 3 | 「チャンキング調整は必要ないかDEAに確認して」 | DEAが8000文字制限のリスクを指摘 | ページ単位チャンキング + VIEW→TABLE変更を提案・実装 |
| 4 | 「分析して」→ テーブルが空 | Document AI出力が `$.pages` ではなく `$.documentLayout.blocks` | `REGEXP_EXTRACT_ALL` ベースの全文抽出に修正 |

特にRound 4では **analysis_agentがテーブル空を発見 → orchestratorがpipeline_agentに切り替え → DEAに原因と実際のJSON構造を送信** というエージェント間連携が機能しました。

最終的に全5アクションが成功:

```
✅ 1_bronze_unstructured_reports  (外部テーブル)
✅ 2_silver_parsed_reports        (Document AI処理)
✅ 3_gold_financial_summary       (ML.GENERATE_TEXT)
✅ 4_gold_financial_metrics_unpivoted (UNPIVOT)
✅ 5_gold_key_driver_analysis     (AI.KEY_DRIVERS)
```

## インフラ構成（Terraform）

```hcl
# GCSバケット（PDF格納）
resource "google_storage_bucket" "pdf_storage" { ... }

# BigQuery外部接続（AI関数用）
resource "google_bigquery_connection" "ai_connection" { ... }

# BigQueryデータセット
resource "google_bigquery_dataset" "alphabet_reports" { ... }

# Dataform実行用サービスアカウント
resource "google_service_account" "dataform_sa" {
  account_id = "dataform-executor"
}

# SA権限: BigQuery Admin, Storage Viewer, Vertex AI User,
#         Document AI Admin, BigQuery Connection User

# Dataformサービスエージェントがdataform_saのトークンを生成できるようにする
resource "google_service_account_iam_member" "dataform_agent_token_creator" {
  role   = "roles/iam.serviceAccountTokenCreator"
  member = "serviceAccount:service-PROJECT_NUMBER@gcp-sa-dataform.iam.gserviceaccount.com"
}

# Dataformリポジトリ（SA設定付き）
resource "google_dataform_repository" "pipeline_repo" {
  provider        = google-beta
  service_account = google_service_account.dataform_sa.email
}
```

## プロジェクト構成

```
new-bq-hands-on/
├── main.tf                      # GCS, BQ接続, IAM, Dataform SA & リポジトリ
├── pdf-uploading.sh             # Alphabet決算PDF取得・GCSアップロード
├── requirements.txt             # google-adk, google-cloud-bigquery, etc.
├── demo_agent/
│   ├── __init__.py
│   ├── .env                     # GOOGLE_GENAI_USE_VERTEXAI=true
│   ├── agent.py                 # root_agent + 3サブエージェント定義
│   └── tools/
│       ├── __init__.py
│       ├── dea_client.py        # DEA A2Aクライアント（ConversationToken管理）
│       ├── dataform_tools.py    # Suitcase pattern + コンパイル/実行結果取得
│       ├── bq_tools.py          # BigQueryテーブル参照・クエリ実行
│       └── memory_tools.py     # Memory Profiles（Pydanticスキーマ）
```

## 得られた知見

### DEAの特性
- 自然言語指示からDataform `.sqlx` ファイルを生成できるが、プロジェクト固有の制約（利用可能なモデル、接続ID形式）を正確に伝えないと誤った構成を生成する
- ConversationTokenによるマルチターン会話を活用すると、エラー修正の文脈を維持できる
- デバッグの方針判断はDEAに委ね、ADKエージェントは事実の収集・伝達に徹するのが効果的

### コンテキストエンジニアリングの効果
- **Suitcase pattern**: DEAが生成するSQLの品質が制約の事前提供で大幅に向上
- **初回のみコンテキスト全文**: ConversationTokenを活用し、2回目以降はdiff（新しい事実のみ）を送る
- **Memory Profiles**: エージェント間でパイプライン状態を構造化共有でき、analysis_agentがpipeline_agentの成果物を即座に参照可能

### ハマりポイント
- `gemini-pro`, `gemini-2.0-flash` 等のPublisher ModelがBigQueryリモートモデルで利用不可（`gemini-2.5-flash` のみ可能だった）
- Document AIの出力構造が `$.pages` ではなく `$.documentLayout.blocks` で、ネストされた `textBlock` から再帰的にテキスト抽出が必要
- `SAFE_PARSE_JSON` はBigQueryに存在しない関数（DEAが生成した誤り）
- Dataformリポジトリのサービスアカウント設定と、Dataformサービスエージェントへの `serviceAccountTokenCreator` ロール付与が必要

## 今後の展望
- **Memory Bank API連携**: 現在はインメモリだが、Vertex AI Memory Bank APIと接続すればセッション横断で永続化可能（`adk web --memory_service_uri=agentengine://AGENT_ENGINE_ID`）
- **Dataform実行の自動化**: 現在は手動実行だが、SA権限を整備すればエージェントからの自動実行も可能
- **追加のBigQuery AI関数活用**: `AI.GENERATE`, `AI.TRANSLATE`, `AI.CLASSIFY` 等を使った高度な分析パイプライン
