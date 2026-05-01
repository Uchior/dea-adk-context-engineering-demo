# 変数の定義
variable "project_id" {}
variable "project_number" {}
variable "region" { default = "us" }

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# 1. PDF格納用のGCSバケット
resource "google_storage_bucket" "pdf_storage" {
  name          = "alphabet-reports-${var.project_id}"
  location      = var.region
  force_destroy = true
}

# 2. BigQuery 外部接続 (Cloud Resource Connection)
resource "google_bigquery_connection" "ai_connection" {
  connection_id = "ai-connection"
  location      = var.region
  cloud_resource {}
}

# 3. サービスアカウントへの権限付与
# 接続用サービスアカウントを取得して各権限をバインド
locals {
  sa_email = "serviceAccount:${google_bigquery_connection.ai_connection.cloud_resource[0].service_account_id}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.sa_email
}

resource "google_project_iam_member" "storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = local.sa_email
}

resource "google_project_iam_member" "doc_ai_admin" {
  project = var.project_id
  role    = "roles/documentai.admin"
  member  = local.sa_email
}

# 4. BigQuery データセット
resource "google_bigquery_dataset" "alphabet_reports" {
  dataset_id = "alphabet_reports"
  location   = var.region
}

# 5. Dataform 実行用サービスアカウント
resource "google_service_account" "dataform_sa" {
  account_id   = "dataform-executor"
  display_name = "Dataform Executor SA"
}

resource "google_project_iam_member" "dataform_bq_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.dataform_sa.email}"
}

resource "google_project_iam_member" "dataform_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.dataform_sa.email}"
}

resource "google_project_iam_member" "dataform_vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.dataform_sa.email}"
}

resource "google_project_iam_member" "dataform_doc_ai_admin" {
  project = var.project_id
  role    = "roles/documentai.admin"
  member  = "serviceAccount:${google_service_account.dataform_sa.email}"
}

resource "google_project_iam_member" "dataform_connection_user" {
  project = var.project_id
  role    = "roles/bigquery.connectionUser"
  member  = "serviceAccount:${google_service_account.dataform_sa.email}"
}

# Dataform サービスエージェントが dataform_sa のトークンを生成できるようにする
resource "google_service_account_iam_member" "dataform_agent_token_creator" {
  service_account_id = google_service_account.dataform_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-dataform.iam.gserviceaccount.com"
}

# 6. Dataform リポジトリ（SA設定付き）
resource "google_dataform_repository" "pipeline_repo" {
  provider = google-beta
  name     = "dea-pipeline-repo"
  region   = "us-central1"

  workspace_compilation_overrides {
    default_database = var.project_id
    schema_suffix    = ""
  }

  service_account = google_service_account.dataform_sa.email
}

output "connection_sa" {
  value = local.sa_email
}

output "dataform_sa" {
  value = google_service_account.dataform_sa.email
}
