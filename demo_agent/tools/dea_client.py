"""Data Engineering Agent A2A client.

Sends natural-language prompts to the DEA via the A2A protocol and returns
streamed responses. Multi-turn conversations are supported through
ConversationToken propagation.
"""

import json
import os
import uuid
from typing import Optional

import google.auth
import google.auth.transport.requests
import requests

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("DATAFORM_LOCATION", "us-central1")
REPO = os.environ.get("DATAFORM_REPO", "dea-pipeline-repo")
WORKSPACE = os.environ.get("DATAFORM_WORKSPACE", "dea-workspace")

DEA_HOST = "https://geminidataanalytics.googleapis.com"
DEA_TENANT = f"projects/{PROJECT_ID}/locations/{LOCATION}/agents/dataengineeringagent"
DEA_ENDPOINT = f"{DEA_HOST}/v1/a2a/{DEA_TENANT}/v1/message:stream"

GCP_RESOURCE_ID = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}"
    f"/repositories/{REPO}/workspaces/{WORKSPACE}"
)

A2A_EXTENSIONS = ", ".join([
    "https://geminidataanalytics.googleapis.com/a2a/extensions/gcpresource/v1",
    "https://geminidataanalytics.googleapis.com/a2a/extensions/conversationtoken/v1",
    "https://geminidataanalytics.googleapis.com/a2a/extensions/messagelevel/v1",
    "https://geminidataanalytics.googleapis.com/a2a/extensions/finishreason/v1",
    "https://geminidataanalytics.googleapis.com/a2a/extensions/pipelinecontext/v1",
    "https://geminidataanalytics.googleapis.com/a2a/extensions/instruction/v1",
])

_last_conversation_token: Optional[str] = None


def _get_access_token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def send_to_dea(
    prompt: str,
    conversation_token: Optional[str] = None,
) -> dict:
    """DEAにプロンプトを送信し、ストリーミングレスポンスを取得する。"""
    token = _get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "A2A-Extensions": A2A_EXTENSIONS,
    }

    metadata = {
        "https://geminidataanalytics.googleapis.com/a2a/extensions/gcpresource/v1": {
            "gcpResourceId": GCP_RESOURCE_ID,
        },
    }
    if conversation_token:
        metadata[
            "https://geminidataanalytics.googleapis.com/a2a/extensions/conversationtoken/v1"
        ] = conversation_token

    body = {
        "request": {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_USER",
            "contextId": f"demo-{uuid.uuid4().hex[:8]}",
            "content": [{"text": prompt}],
        },
        "metadata": metadata,
        "tenant": DEA_TENANT,
    }

    resp = requests.post(DEA_ENDPOINT, headers=headers, json=body, stream=True)
    resp.raise_for_status()

    messages: list[str] = []
    next_token: Optional[str] = None
    status: Optional[str] = None
    finish_reason: Optional[str] = None

    chunks = json.loads(resp.text)
    for chunk in chunks:
        su = chunk.get("statusUpdate", {})
        st = su.get("status", {})
        msg = st.get("message", {})
        for part in msg.get("content", []):
            if "text" in part:
                messages.append(part["text"])

        if st.get("state"):
            status = st["state"]

        meta = su.get("metadata", {})
        tok = meta.get(
            "https://geminidataanalytics.googleapis.com/a2a/extensions/conversationtoken/v1"
        )
        if tok:
            next_token = tok
        fr = meta.get(
            "https://geminidataanalytics.googleapis.com/a2a/extensions/finishreason/v1"
        )
        if fr:
            finish_reason = fr

    return {
        "messages": messages,
        "conversation_token": next_token,
        "status": status,
        "finish_reason": finish_reason,
    }


def _format_dea_response(result: dict) -> str:
    """DEAレスポンスをエージェント向けに整形する。"""
    parts = []
    parts.append(f"[DEA status: {result.get('status', 'unknown')}]")
    for msg in result.get("messages", []):
        if not msg:
            continue
        skip_prefixes = (
            "Reading file", "Writing file", "Analyzing the pipeline",
            "Validation failed",
        )
        if any(msg.startswith(p) for p in skip_prefixes):
            continue
        parts.append(msg)
    if result.get("finish_reason"):
        parts.append(f"[finish_reason: {result['finish_reason']}]")
    return "\n\n".join(parts)


# ---------- ADK Tool wrappers ----------

def send_instruction_to_dea(instruction: str) -> str:
    """DEAに自然言語指示を送信してパイプラインを生成・修正させる。

    新規パイプラインの作成にもエラー修正にも使える汎用ツール。
    マルチターン会話は自動的に維持される（前回のconversation_tokenを引き継ぐ）。

    Args:
        instruction: DEAへの自然言語指示。パイプライン生成指示でも、
                     エラーメッセージを含む修正依頼でもよい。
    Returns:
        DEAからのレスポンス（生成されたファイル情報、修正内容等）。
    """
    global _last_conversation_token
    result = send_to_dea(instruction, conversation_token=_last_conversation_token)
    _last_conversation_token = result.get("conversation_token")
    return _format_dea_response(result)


def reset_dea_conversation() -> str:
    """DEAとの会話をリセットして新しいセッションを開始する。

    新しいパイプラインを一から作り直したい場合に使用。
    """
    global _last_conversation_token
    _last_conversation_token = None
    return "DEAとの会話をリセットしました。新しいセッションで指示を送信できます。"
