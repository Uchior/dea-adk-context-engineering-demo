"""Memory Bank structured profile schemas.

Defines Pydantic schemas for Memory Bank's Structured Profiles API.
These schemas are registered with Agent Engine via setup_memory_bank.py,
and Memory Bank automatically extracts/consolidates profile data from
conversation events.

Agents access profiles via PreloadMemoryTool (auto-inject each turn)
and LoadMemoryTool (on-demand retrieval).
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Profile Schemas (Pydantic) — registered with Agent Engine's Memory Bank
# ---------------------------------------------------------------------------

class PipelineProfile(BaseModel):
    """DEAが生成したパイプラインの状態を記憶するプロファイル。"""

    dataform_files: str = Field(
        default="",
        description="カンマ区切りのDataformファイル一覧（例: 1_bronze.sqlx, 2_silver.sqlx）",
    )
    pipeline_architecture: str = Field(
        default="",
        description="パイプラインのアーキテクチャ概要（例: Bronze→Silver→Gold medallion）",
    )
    ai_functions_used: str = Field(
        default="",
        description="使用されたBigQuery AI関数（例: ML.GENERATE_TEXT, AI.KEY_DRIVERS）",
    )
    compilation_status: str = Field(
        default="unknown",
        description="直近のDataformコンパイル結果（success/error/unknown）",
    )
    last_errors: str = Field(
        default="",
        description="直近のコンパイルエラー内容（解消済みなら空）",
    )


class AnalysisProfile(BaseModel):
    """財務分析の結果とインサイトを記憶するプロファイル。"""

    quarters_analyzed: str = Field(
        default="",
        description="分析対象の四半期（例: Q1 2023, Q1 2024）",
    )
    segments_analyzed: str = Field(
        default="",
        description="分析対象のセグメント（例: Google Services, Google Cloud, YouTube Ads）",
    )
    key_findings: str = Field(
        default="",
        description="主要な分析結果・インサイト",
    )
    revenue_highlights: str = Field(
        default="",
        description="収益に関する主要な数値（例: Google Cloud +28% YoY）",
    )
    data_quality_notes: str = Field(
        default="",
        description="データ品質に関する注記（欠損値、異常値等）",
    )


# Schema configs for Agent Engine registration (used by setup_memory_bank.py)
PROFILE_SCHEMAS = [
    {
        "id": "pipeline-profile",
        "memory_schema": PipelineProfile.model_json_schema(),
    },
    {
        "id": "analysis-profile",
        "memory_schema": AnalysisProfile.model_json_schema(),
    },
]
