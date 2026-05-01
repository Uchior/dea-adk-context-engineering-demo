"""BigQuery tools for inspecting DEA-generated tables and running queries."""

import os

from google.cloud import bigquery

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
DATASET = os.environ.get("BQ_DATASET", "alphabet_reports")

_client = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def list_tables() -> str:
    """alphabet_reportsデータセット内のテーブル一覧を返す。"""
    client = _get_client()
    tables = list(client.list_tables(f"{PROJECT_ID}.{DATASET}"))
    if not tables:
        return "テーブルが見つかりません。"
    lines = [f"- {t.table_id} ({t.table_type})" for t in tables]
    return "\n".join(lines)


def preview_table(table_name: str, max_rows: int = 10) -> str:
    """指定テーブルの先頭行をプレビューする。

    Args:
        table_name: テーブル名（データセット内）。
        max_rows: 返す最大行数。
    """
    client = _get_client()
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET}.{table_name}` LIMIT {max_rows}"
    rows = list(client.query(query).result())
    if not rows:
        return f"テーブル {table_name} にデータがありません。"
    header = list(rows[0].keys())
    lines = [" | ".join(header)]
    lines.append(" | ".join("---" for _ in header))
    for row in rows:
        lines.append(" | ".join(str(row[k]) for k in header))
    return "\n".join(lines)


def run_query(sql: str) -> str:
    """任意のSQLクエリを実行して結果を返す。

    Args:
        sql: 実行するGoogleSQL クエリ。
    """
    client = _get_client()
    rows = list(client.query(sql).result())
    if not rows:
        return "結果なし。"
    header = list(rows[0].keys())
    lines = [" | ".join(header)]
    for row in rows:
        lines.append(" | ".join(str(row[k]) for k in header))
    return "\n".join(lines)
