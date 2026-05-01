"""Dataform workspace tools.

Compile the Dataform workspace and report errors so the pipeline agent
can feed them back to DEA for autonomous correction.

Context engineering: gather_workspace_context() implements the "Suitcase
pattern" — packing the right information at the right time for DEA.
"""

import base64
import os
import time

import google.auth
import google.auth.transport.requests
import requests

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GCP_REGION = os.environ.get("GCP_REGION", "us")
LOCATION = os.environ.get("DATAFORM_LOCATION", "us-central1")
REPO = os.environ.get("DATAFORM_REPO", "dea-pipeline-repo")
WORKSPACE = os.environ.get("DATAFORM_WORKSPACE", "dea-workspace")
BQ_DATASET = os.environ.get("BQ_DATASET", "alphabet_reports")
BQ_CONNECTION_ID = os.environ.get("BQ_CONNECTION_ID", "ai-connection")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
DOCAI_PROCESSOR = os.environ.get("DOCAI_PROCESSOR", "")

_BASE = (
    f"https://dataform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
    f"/locations/{LOCATION}/repositories/{REPO}/workspaces/{WORKSPACE}"
)
_REPO_BASE = (
    f"https://dataform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
    f"/locations/{LOCATION}/repositories/{REPO}"
)

_last_compilation_result: str | None = None


def _build_project_context() -> str:
    bq_connection = f"{PROJECT_ID}.{GCP_REGION}.{BQ_CONNECTION_ID}"
    return f"""## プロジェクト環境
- project: {PROJECT_ID}
- region: {GCP_REGION}
- BigQuery接続: {bq_connection}
- データセット: {BQ_DATASET}
- GCSバケット: gs://{GCS_BUCKET}/
- Document AIプロセッサ: {DOCAI_PROCESSOR}

## 重要な制約
- ML.PARSE_DOCUMENT はこのプロジェクトではまだ利用不可。代わりに ML.PROCESS_DOCUMENT + リモートモデル、または ML.GENERATE_TEXT を使うこと
- AI.KEY_DRIVERS はDataformコンパイラが認識できないため type: "operations" + hasOutput: true で定義すること
- 接続IDは必ず {bq_connection} の形式で指定すること
- リモートモデルのendpointは必ず gemini-2.5-flash を使うこと。gemini-pro, gemini-1.5-flash, gemini-2.0-flash 等は利用不可（Publisher Model not found エラーになる）
- CREATE OR REPLACE MODEL 文の ENDPOINT は 'gemini-2.5-flash' のみ使用可能
- テーブルは schema: "{BQ_DATASET}" に出力すること"""


def _get_access_token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def gather_workspace_context() -> str:
    """DEAに指示を送る前に呼ぶ。ワークスペースの現状とプロジェクト制約を収集する。

    Suitcase pattern: DEAが正しいパイプラインを生成するために必要な情報を
    「正しい情報・正しい構造・正しいタイミング」でパッキングする。
    この出力を send_instruction_to_dea の instruction に含めること。
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 既存ファイル一覧
    resp = requests.get(f"{_BASE}:queryDirectoryContents", headers=headers,
                        params={"path": "definitions"})
    existing_files = []
    if resp.status_code == 200:
        for e in resp.json().get("directoryEntries", []):
            if "file" in e:
                existing_files.append(e["file"])

    # 直近のコンパイル結果
    compile_url = (
        f"https://dataform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
        f"/locations/{LOCATION}/repositories/{REPO}/compilationResults"
    )
    body = {
        "workspace": (
            f"projects/{PROJECT_ID}/locations/{LOCATION}"
            f"/repositories/{REPO}/workspaces/{WORKSPACE}"
        ),
    }
    compile_resp = requests.post(compile_url, headers=headers, json=body)
    compile_status = "不明"
    compile_errors = []
    if compile_resp.status_code == 200:
        result = compile_resp.json()
        errors = result.get("compilationErrors", [])
        if errors:
            compile_status = f"エラー {len(errors)}件"
            for err in errors:
                compile_errors.append(
                    f"  - {err.get('path', '?')}: {err.get('message', '')}"
                )
        else:
            compile_status = "成功"

    lines = [
        "# ワークスペース現状レポート",
        "",
        _build_project_context(),
        "",
        "## 既存ファイル",
    ]
    if existing_files:
        for f in existing_files:
            lines.append(f"- {f}")
    else:
        lines.append("（なし — 新規作成が必要）")

    lines.append("")
    lines.append(f"## コンパイル状態: {compile_status}")
    if compile_errors:
        lines.extend(compile_errors)

    return "\n".join(lines)


def compile_dataform() -> str:
    """Dataformワークスペースをコンパイルし、エラーがあれば返す。

    エラーがなければ成功メッセージとコンパイル済みアクション一覧を返す。
    エラーがあればファイル名とエラーメッセージを返す。
    このツールの出力をそのままDEAへのエラー修正指示に使える。
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    compile_url = (
        f"https://dataform.googleapis.com/v1beta1/projects/{PROJECT_ID}"
        f"/locations/{LOCATION}/repositories/{REPO}/compilationResults"
    )
    body = {
        "workspace": (
            f"projects/{PROJECT_ID}/locations/{LOCATION}"
            f"/repositories/{REPO}/workspaces/{WORKSPACE}"
        ),
    }

    resp = requests.post(compile_url, headers=headers, json=body)
    if resp.status_code != 200:
        return f"コンパイルAPI呼び出しエラー: {resp.status_code} {resp.text}"

    global _last_compilation_result
    result = resp.json()
    compilation_name = result.get("name")
    _last_compilation_result = compilation_name

    errors = result.get("compilationErrors", [])
    if errors:
        lines = ["[コンパイルエラーが見つかりました]"]
        for err in errors:
            path = err.get("path", "unknown")
            message = err.get("message", "")
            action = err.get("actionTarget", {}).get("name", "")
            lines.append(f"- {path} ({action}): {message}")
        return "\n".join(lines)

    if compilation_name:
        get_resp = requests.get(
            f"https://dataform.googleapis.com/v1beta1/{compilation_name}",
            headers=headers,
        )
        if get_resp.status_code == 200:
            result = get_resp.json()

    tables = result.get("compiledGraph", {}).get("tables", [])
    operations = result.get("compiledGraph", {}).get("operations", [])
    assertions = result.get("compiledGraph", {}).get("assertions", [])

    lines = ["[コンパイル成功]"]
    lines.append(f"テーブル/ビュー: {len(tables)}件")
    lines.append(f"オペレーション: {len(operations)}件")
    if assertions:
        lines.append(f"アサーション: {len(assertions)}件")

    for t in tables:
        target = t.get("target", {})
        name = target.get("name", "?")
        ttype = t.get("type", "?")
        lines.append(f"  - {name} ({ttype})")
    for o in operations:
        target = o.get("target", {})
        name = target.get("name", "?")
        lines.append(f"  - {name} (operations)")

    lines.append(f"\nrun_dataform() で実行できます。")
    return "\n".join(lines)


def list_dataform_files() -> str:
    """Dataformワークスペース内のファイル一覧を返す。"""
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(
        f"{_BASE}:queryDirectoryContents",
        headers=headers,
    )
    if resp.status_code != 200:
        return f"エラー: {resp.status_code} {resp.text}"

    entries = resp.json().get("directoryEntries", [])
    lines = []
    for e in entries:
        if "file" in e:
            lines.append(f"  {e['file']}")
        elif "directory" in e:
            lines.append(f"  {e['directory']}/")
            sub_resp = requests.get(
                f"{_BASE}:queryDirectoryContents",
                headers=headers,
                params={"path": e["directory"]},
            )
            if sub_resp.status_code == 200:
                for se in sub_resp.json().get("directoryEntries", []):
                    if "file" in se:
                        lines.append(f"    {se['file']}")
    return "\n".join(lines)


def read_dataform_file(file_path: str) -> str:
    """Dataformワークスペース内のファイルを読み取る。

    Args:
        file_path: 読み取るファイルパス（例: definitions/1_bronze.sqlx）
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(
        f"{_BASE}:readFile",
        headers=headers,
        params={"path": file_path},
    )
    if resp.status_code != 200:
        return f"エラー: {resp.status_code} {resp.text}"

    content = resp.json().get("fileContents", "")
    return base64.b64decode(content).decode()


def get_latest_run() -> str:
    """直近のDataformワークフロー実行の状態を取得する。

    ユーザーが手動実行した結果を確認するために使う。
    実行がまだ進行中の場合はその旨を返す。
    失敗の場合は get_run_actions で詳細を確認できる。
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(
        f"{_REPO_BASE}/workflowInvocations",
        headers=headers,
        params={"pageSize": 1, "orderBy": "name desc"},
    )
    if resp.status_code != 200:
        return f"エラー: {resp.status_code} {resp.text}"

    invocations = resp.json().get("workflowInvocations", [])
    if not invocations:
        return "実行履歴がありません。Dataformコンソールからパイプラインを実行してください。"

    data = invocations[0]
    return _format_invocation_result(data)


def get_run_actions() -> str:
    """直近のDataformワークフロー実行の各アクション詳細を取得する。

    各アクションの成功/失敗、エラーメッセージ、実行されたSQLを返す。
    失敗したアクションのエラー内容をDEAにフィードバックして修正依頼する際に使う。
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(
        f"{_REPO_BASE}/workflowInvocations",
        headers=headers,
        params={"pageSize": 1, "orderBy": "name desc"},
    )
    if resp.status_code != 200:
        return f"エラー: {resp.status_code} {resp.text}"

    invocations = resp.json().get("workflowInvocations", [])
    if not invocations:
        return "実行履歴がありません。"

    invocation_name = invocations[0].get("name", "")

    actions_resp = requests.get(
        f"https://dataform.googleapis.com/v1beta1/{invocation_name}:query",
        headers=headers,
    )
    if actions_resp.status_code != 200:
        return f"エラー: {actions_resp.status_code} {actions_resp.text}"

    actions = actions_resp.json().get("workflowInvocationActions", [])
    if not actions:
        return "アクションが見つかりません。"

    lines = [f"[invocation: {invocation_name}]"]
    for a in actions:
        target = a.get("target", {})
        name = target.get("name", "?")
        state = a.get("state", "?")
        failure = a.get("failureReason", "")
        lines.append(f"- {name}: {state}")
        if failure:
            lines.append(f"  エラー: {failure}")
        bq_action = a.get("bigqueryAction", {})
        if bq_action.get("sqlScript"):
            sql_preview = bq_action["sqlScript"][:500]
            lines.append(f"  SQL: {sql_preview}")

    return "\n".join(lines)


def _format_invocation_result(data: dict) -> str:
    """ワークフロー実行結果を整形する。"""
    state = data.get("state", "UNKNOWN")
    name = data.get("name", "")

    lines = [f"[Dataform実行結果: {state}]"]
    lines.append(f"invocation: {name}")

    if state == "SUCCEEDED":
        lines.append("全アクションが正常に完了しました。")
        lines.append("get_invocation_actions で各アクションの詳細を確認できます。")
    elif state == "FAILED":
        lines.append("一部のアクションが失敗しました。")
        lines.append("get_invocation_actions で失敗の詳細を確認してください。")
    elif state == "CANCELLED":
        lines.append("実行がキャンセルされました。")
    else:
        lines.append(f"状態: {state}（タイムアウトの可能性あり）")

    return "\n".join(lines)
