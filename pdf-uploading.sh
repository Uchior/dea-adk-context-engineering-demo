#!/bin/bash
# GCS_BUCKET 環境変数を設定してから実行すること
# 例: export GCS_BUCKET=alphabet-reports-your-project-id

if [ -z "$GCS_BUCKET" ]; then
  echo "Error: GCS_BUCKET environment variable is not set."
  echo "Usage: export GCS_BUCKET=your-bucket-name && bash pdf-uploading.sh"
  exit 1
fi

# 2024 Q1 と 2023 Q1 のPDF
PDF_2024="https://s206.q4cdn.com/479360582/files/doc_financials/2024/q1/2024q1-alphabet-earnings-release-pdf.pdf"
PDF_2023="https://s206.q4cdn.com/479360582/files/doc_financials/2023/q1/goog-exhibit-99-1-q1-2023-19.pdf"

echo "Downloading PDFs..."
curl -L -o q1_2024.pdf $PDF_2024
curl -L -o q1_2023.pdf $PDF_2023

echo "Uploading to GCS..."
gcloud storage cp *.pdf gs://${GCS_BUCKET}/

echo "Done!"
