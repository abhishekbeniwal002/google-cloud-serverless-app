# Serverless Event-Driven Document Processing Pipeline

A Google Cloud serverless architecture for processing documents uploaded to Cloud Storage. This project utilizes Cloud Storage, Pub/Sub Notifications, Cloud Run, and BigQuery.

## Architecture

1. **Ingestion**: A user or system uploads a file to a Google Cloud Storage (GCS) bucket.
2. **Trigger**: GCS sends an `OBJECT_FINALIZE` event to a Pub/Sub topic via object change notifications.
3. **Execution**: A Pub/Sub Push Subscription invokes the Cloud Run service (FastAPI).
4. **Processing**:
   - The FastAPI service downloads the file from GCS.
   - For `.txt` files, it counts the words and extracts tags based on frequency.
   - For other files (e.g., `.pdf`, `.png`), it simulates OCR by generating a mock word count and random tags.
5. **Storage**: The processed metadata is streamed into a BigQuery table.

## Prerequisites

- [Google Cloud SDK (gcloud)](https://cloud.google.com/sdk/docs/install) installed and authenticated.
- Python 3.11+
- Billing enabled on your Google Cloud Project.

## Local Development & Testing

You can run the FastAPI service locally to test it without deploying to GCP.

1. **Install dependencies:**
   ```bash
   cd app
   pip install -r requirements.txt
   ```

2. **Run the local server:**
   You can run it in fully offline mode (skipping GCS download and BigQuery insert) by setting environment variables:
   
   **Linux/macOS:**
   ```bash
   SKIP_GCS_DOWNLOAD=1 SKIP_BQ_INSERT=1 uvicorn main:app --reload --port 8080
   ```
   **Windows (PowerShell):**
   ```powershell
   $env:SKIP_GCS_DOWNLOAD="1"; $env:SKIP_BQ_INSERT="1"; uvicorn main:app --reload --port 8080
   ```

3. **Send a mock Pub/Sub payload:**
   In another terminal, run the local test script:
   ```bash
   python scripts/test_local.py
   ```
   *You should see a successful response from the FastAPI server.*

## Streamlit Dashboard

We provide a simple, interactive Streamlit web application to view and filter the processed documents directly from BigQuery.

1. **Install dashboard dependencies:**
   ```bash
   cd dashboard
   pip install -r requirements.txt
   ```

2. **Authenticate with GCP (if not already done):**
   ```bash
   gcloud auth application-default login
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **Run the dashboard:**
   ```bash
   streamlit run app.py
   ```
   *This will open the dashboard in your default web browser.*

## Deployment to Google Cloud

We provide deployment scripts for both PowerShell (Windows) and Bash (Linux/macOS/Git Bash).

**Note:** Ensure you are authenticated with `gcloud auth login` and have set your default project: `gcloud config set project YOUR_PROJECT_ID`.

### Using PowerShell (Recommended for Windows)

Run the script from the project root:
```powershell
.\deploy.ps1
```

### Using Bash (Linux/macOS)

Run the script from the project root:
```bash
chmod +x deploy.sh
./deploy.sh
```

### What the script does:
- Enables necessary GCP APIs.
- Creates a Service Account with necessary roles.
- Creates the BigQuery dataset (`document_processing`) and table (`metadata`).
- Deploys the Python FastAPI application to Cloud Run.
- Creates the Pub/Sub topic and configures the GCS bucket to send notifications to it.
- Creates the Pub/Sub push subscription that routes messages to your secure Cloud Run endpoint.

## Usage

1. Find the name of your created GCS bucket (usually `YOUR_PROJECT_ID-upload-bucket`).
2. Upload a file:
   ```bash
   gcloud storage cp my_document.txt gs://YOUR_BUCKET_NAME/
   ```
3. Check the Cloud Run logs to see the processing.
4. Check the BigQuery table to see the extracted metadata:
   ```bash
   bq query --use_legacy_sql=false "SELECT * FROM \`document_processing.metadata\` LIMIT 10"
   ```
