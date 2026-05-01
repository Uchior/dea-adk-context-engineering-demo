"""ADK multi-agent orchestrator for the BigQuery PDF analysis demo.

Context engineering techniques:
  1. Suitcase pattern     — gather_workspace_context packs project state before DEA calls
  2. Progressive Disclosure — pipeline_agent loads context on-demand via phased workflow
  3. Memory Profiles      — Memory Bank Structured Profiles for pipeline state & analysis results
  4. State-aware routing  — orchestrator decides next action based on current profile state
"""

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.load_memory_tool import LoadMemoryTool
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

from demo_agent.tools.dea_client import (
    send_instruction_to_dea,
    reset_dea_conversation,
)
from demo_agent.tools.dataform_tools import (
    gather_workspace_context,
    compile_dataform,
    list_dataform_files,
    read_dataform_file,
    get_latest_run,
    get_run_actions,
)
from demo_agent.tools.bq_tools import list_tables, preview_table, run_query

MODEL = "claude-opus-4-5"


# ---------------------------------------------------------------------------
# Memory Bank callback — send conversation events for profile extraction
# ---------------------------------------------------------------------------
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_events_to_memory(
        events=callback_context.session.events[-5:-1]
    )
    return None


# ---------------------------------------------------------------------------
# pipeline_agent: DEA連携 + 自律修正ループ
# ---------------------------------------------------------------------------
pipeline_agent = Agent(
    name="pipeline_agent",
    model=MODEL,
    description="DEAにパイプライン生成を指示し、コンパイルエラーを自律修正するエージェント。",
    instruction="""あなたはDEAに事実を渡してパイプライン構築を依頼するエージェントです。
修正方針やデバッグ判断はすべてDEAに任せる。あなたはSQLの修正方法を考えない。

## コンテキスト管理の原則
- DEAとはマルチターン会話（ConversationToken）で繋がっている。一度渡した情報はDEAが覚えている。
- 初回のみ gather_workspace_context の全文（制約含む）を渡す。2回目以降は渡さない。
- エラー修正時はエラーメッセージと該当ファイル内容だけを渡す。制約の再送は不要。
- 同じ情報を繰り返し送らない。新しい事実だけを送る。

## ワークフロー

### Phase 1: コンテキスト収集
gather_workspace_context を呼ぶ。

### Phase 2: DEAへの初回指示
send_instruction_to_dea に以下を含める:
- gather_workspace_context の返り値（全文）
- ユーザーの要件

### Phase 3: コンパイル検証
compile_dataform を呼ぶ。

### Phase 4: エラー修正ループ（最大5回）
コンパイルエラーがあれば:
1. read_dataform_file で該当ファイルの内容を取得
2. DEAにはエラーメッセージ + ファイル内容のみ送る（制約は初回で伝達済み）
3. 再コンパイル → エラーが残れば繰り返す

実行エラー（BQエラー）の場合:
1. get_run_actions でエラー詳細を取得
2. read_dataform_file で該当ファイルの内容を取得
3. DEAにはエラーメッセージ + ファイル内容のみ送る

### Phase 5: 実行結果の確認
コンパイル成功後、ユーザーにDataformコンソールからの手動実行を促す。
ユーザーが実行したら get_latest_run で状態を確認。失敗なら Phase 4 へ。""",
    tools=[
        gather_workspace_context,
        send_instruction_to_dea,
        reset_dea_conversation,
        compile_dataform,
        get_latest_run,
        get_run_actions,
        list_dataform_files,
        read_dataform_file,
    ],
)

# ---------------------------------------------------------------------------
# analysis_agent: BQデータ確認 + 分析
# ---------------------------------------------------------------------------
analysis_agent = Agent(
    name="analysis_agent",
    model=MODEL,
    description="BigQueryのテーブルを確認・分析するエージェント。",
    instruction="""あなたはBigQueryのデータを確認・分析するエージェントです。
環境変数で設定されたプロジェクトとデータセットを対象にします。

## ワークフロー
1. list_tables でテーブル一覧を確認
2. preview_table / run_query でデータを取得・分析
3. 分析結果を会話に含めることで、Memory Bankが自動的にAnalysisProfileを更新する""",
    tools=[
        list_tables,
        preview_table,
        run_query,
    ],
)

# ---------------------------------------------------------------------------
# memory_agent: プロファイル参照・横断検索
# ---------------------------------------------------------------------------
memory_agent = Agent(
    name="memory_agent",
    model=MODEL,
    description="Memory Bankのプロファイルから過去のパイプライン状態・分析結果を参照するエージェント。",
    instruction="""あなたは Memory Bank のプロファイルを使って過去のコンテキストを提供するエージェントです。

LoadMemoryTool を使って以下の構造化プロファイルを取得できます:
- PipelineProfile: パイプラインの状態（ファイル一覧、アーキテクチャ、AI関数、コンパイル状態）
- AnalysisProfile: 分析結果（四半期、セグメント、Key Findings、収益ハイライト）

これらはMemory Bankによって会話イベントから自動的に抽出・統合されます。
プロファイルの内容を分かりやすく要約してユーザーに伝えてください。""",
    tools=[LoadMemoryTool()],
)

# ---------------------------------------------------------------------------
# root_agent: State-aware orchestrator
# ---------------------------------------------------------------------------
root_agent = Agent(
    name="orchestrator",
    model=MODEL,
    description="PDF分析パイプラインデモのオーケストレーター",
    instruction="""あなたはAlphabet社の決算PDF分析デモのオーケストレーターです。

## コンテキストエンジニアリング
このデモは以下のテクニックを活用しています:
- Suitcase pattern: DEAに指示する前にワークスペースの現状を自動収集
- Progressive Disclosure: 必要な情報を必要なタイミングでロード
- Memory Profiles: Memory Bankがパイプライン状態・分析結果を自動抽出・構造化
- State-aware routing: プロファイルの状態に基づいて次のアクションを判断

## サブエージェント

### pipeline_agent — パイプライン構築＆自律修正
DEAにパイプライン生成を指示 → Dataformコンパイルで検証 → エラー自動修正。

### analysis_agent — データ確認・分析
BigQueryのテーブル確認、データ分析。

### memory_agent — プロファイル参照
Memory Bankから過去のPipelineProfile・AnalysisProfileを参照して
コンテキストを提供する。

## デモフロー
1. pipeline_agent → PDF解析パイプラインを構築（コンテキスト収集→DEA指示→コンパイル→修正ループ）
2. analysis_agent → 生成されたテーブルを確認・分析
3. pipeline_agent → Key Driver分析パイプラインを構築
4. analysis_agent → 分析結果を確認
5. memory_agent → プロファイルからセッション横断のコンテキストを提供

日本語で応答してください。""",
    sub_agents=[pipeline_agent, analysis_agent, memory_agent],
    tools=[PreloadMemoryTool()],
    after_agent_callback=generate_memories_callback,
)
