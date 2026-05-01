#!/usr/bin/env python3
"""Demo runner: ADK orchestrator for Alphabet PDF analysis.

Usage:
  # Interactive mode via ADK Web UI
  adk web --memory_service_uri=agentengine://$AGENT_ENGINE_ID demo_agent

  # Or run this script for a scripted demo flow
  python run_demo.py
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv("demo_agent/.env")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import VertexAiMemoryBankService
from google.genai.types import Content, Part

from demo_agent.agent import root_agent

APP_NAME = "alphabet_pdf_analysis"
USER_ID = "demo_user"

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "")

session_service = InMemorySessionService()
memory_service = VertexAiMemoryBankService(
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
    location=os.environ.get("DATAFORM_LOCATION", "us-central1"),
    agent_engine_id=AGENT_ENGINE_ID,
)


async def send_message(runner: Runner, session_id: str, text: str) -> str:
    """Send a message to the orchestrator and collect the final response."""
    message = Content(parts=[Part(text=text)], role="user")
    final = "(応答なし)"
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = event.content.parts[0].text
    return final


async def run_demo():
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service,
    )

    session = await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    sid = session.id

    print("=" * 60)
    print("Alphabet決算PDF分析デモ")
    print("  DEA + ADK/A2A + BigQuery AI Functions + Memory Bank")
    print("=" * 60)

    # --- Step 1: PDF Pipeline ---
    print("\n Step 1: DEAにPDF解析パイプラインの構築を指示")
    print("-" * 40)
    resp = await send_message(
        runner, sid,
        f"GCSバケット gs://{GCS_BUCKET}/ にある"
        "Alphabet社の決算PDF（Q1 2023, Q1 2024）を解析するパイプラインを"
        "作ってください。AI.PARSE_DOCUMENTまたはAI.GENERATEを使って"
        "財務データを構造化テーブルに抽出してください。"
    )
    print(f"応答: {resp}\n")

    # --- Step 2: Check tables ---
    print("\n Step 2: 生成されたテーブルを確認")
    print("-" * 40)
    resp = await send_message(
        runner, sid,
        "alphabet_reportsデータセットにどんなテーブルが作られたか確認して、"
        "データをプレビューしてください。"
    )
    print(f"応答: {resp}\n")

    # --- Step 3: Key Driver Analysis Pipeline ---
    print("\n Step 3: DEAにKey Driver分析パイプラインの構築を指示")
    print("-" * 40)
    resp = await send_message(
        runner, sid,
        "Q1 2023とQ1 2024のセグメント別収益データを比較して、"
        "AI.KEY_DRIVERS関数で変動要因分析を行うパイプラインを作ってください。"
    )
    print(f"応答: {resp}\n")

    # --- Step 4: Review analysis ---
    print("\n Step 4: 分析結果の確認")
    print("-" * 40)
    resp = await send_message(
        runner, sid,
        "Key Driver分析の結果を確認して、Q1 2023からQ1 2024で"
        "最も大きな変動があったセグメントとその要因を教えてください。"
    )
    print(f"応答: {resp}\n")

    # --- Step 5: Memory ---
    print("\n Step 5: Memory Bankにプロファイル生成")
    print("-" * 40)
    completed = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=sid
    )
    await memory_service.add_session_to_memory(completed)
    print("セッション履歴からMemory Bankプロファイルを生成しました。")

    # --- Step 6: New session, recall from memory ---
    print("\n Step 6: 新規セッションで過去の分析コンテキストを活用")
    print("-" * 40)
    session2 = await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    resp = await send_message(
        runner, session2.id,
        "前回のAlphabet決算分析で分かったことを踏まえて、"
        "Google Cloudの成長率が他のセグメントと比べてどうだったか教えてください。"
    )
    print(f"応答: {resp}\n")

    print("=" * 60)
    print("デモ完了!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_demo())
