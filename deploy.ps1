$ErrorActionPreference = "Stop"

# Configuration variables
$PROJECT_ID = if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { $(gcloud config get-value project) }
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "us-central1" }
$BUCKET_NAME = if ($env:GCP_BUCKET_NAME) { $env:GCP_BUCKET_NAME } else { "${PROJECT_ID}-upload-bucket" }
$TOPIC_NAME = if ($env:GCP_TOPIC_NAME) { $env:GCP_TOPIC_NAME } else { "document-uploads" }
$DATASET_NAME = if ($env:BQ_DATASET) { $env:BQ_DATASET } else { "document_processing" }
$TABLE_NAME = if ($env:BQ_TABLE) { $env:BQ_TABLE } else { "metadata" }
$SERVICE_NAME = "document-processor"
$SERVICE_ACCOUNT_NAME = "doc-processor-sa"
$SERVICE_ACCOUNT_EMAIL = "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

Write-Host "Deploying to Project: ${PROJECT_ID} in Region: ${REGION}"

# 1. Enable Required APIs
Write-Host "Enabling necessary GCP APIs..."
gcloud services enable run.googleapis.com pubsub.googleapis.com storage.googleapis.com bigquery.googleapis.com cloudbuild.googleapis.com

# 2. Create Service Account
Write-Host "Creating Service Account: ${SERVICE_ACCOUNT_EMAIL}..."
try {
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME --display-name="Document Processor Service Account" 2>$null
} catch {
    Write-Host "Service account might already exist. Continuing..."
}

# 3. Grant Permissions to Service Account
Write-Host "Granting roles to Service Account..."
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/storage.objectViewer" | Out-Null
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/bigquery.dataEditor" | Out-Null
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" --role="roles/run.invoker" | Out-Null

# 4. Create BigQuery Dataset and Table
Write-Host "Creating BigQuery Dataset and Table..."
try { bq mk -d --location=$REGION "${PROJECT_ID}:${DATASET_NAME}" 2>$null } catch {}
try { bq mk -t --schema="filename:STRING,upload_time:TIMESTAMP,tags:STRING,word_count:INTEGER,processed_time:TIMESTAMP" "${PROJECT_ID}:${DATASET_NAME}.${TABLE_NAME}" 2>$null } catch {}

# 5. Build and Deploy Cloud Run Service
Write-Host "Deploying Cloud Run Service..."
Set-Location app
gcloud run deploy $SERVICE_NAME `
    --source . `
    --region $REGION `
    --service-account $SERVICE_ACCOUNT_EMAIL `
    --set-env-vars "BQ_DATASET=$DATASET_NAME,BQ_TABLE=$TABLE_NAME" `
    --no-allow-unauthenticated

$SERVICE_URL = gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'
Write-Host "Service deployed at: ${SERVICE_URL}"
Set-Location ..

# 6. Create Pub/Sub Topic and GCS Notification
Write-Host "Creating Pub/Sub Topic..."
try { gcloud pubsub topics create $TOPIC_NAME 2>$null } catch {}

Write-Host "Creating GCS Bucket..."
try { gcloud storage buckets create "gs://${BUCKET_NAME}" --location=$REGION 2>$null } catch {}

Write-Host "Setting up GCS Notification to Pub/Sub..."
$GCS_SA = gcloud storage service-agent --project=$PROJECT_ID --format="value(email_address)"
gcloud pubsub topics add-iam-policy-binding $TOPIC_NAME --member="serviceAccount:${GCS_SA}" --role="roles/pubsub.publisher" | Out-Null

try {
    gcloud storage buckets notifications create "gs://${BUCKET_NAME}" --topic=$TOPIC_NAME --event-types=OBJECT_FINALIZE 2>$null
} catch {}

# 7. Create Pub/Sub Push Subscription
Write-Host "Creating Pub/Sub Push Subscription to Cloud Run..."
$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" --role="roles/iam.serviceAccountTokenCreator" | Out-Null

try {
    gcloud pubsub subscriptions create "${SERVICE_NAME}-sub" `
        --topic=$TOPIC_NAME `
        --push-endpoint="${SERVICE_URL}/pubsub" `
        --push-auth-service-account=$SERVICE_ACCOUNT_EMAIL 2>$null
} catch {}

Write-Host "Deployment complete! Upload a file to gs://${BUCKET_NAME} to trigger the pipeline."
