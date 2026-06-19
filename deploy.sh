#!/bin/bash
set -e

# Configuration variables (modify these or pass them via environment)
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}
REGION=${GCP_REGION:-"us-central1"}
BUCKET_NAME=${GCP_BUCKET_NAME:-"${PROJECT_ID}-upload-bucket"}
TOPIC_NAME=${GCP_TOPIC_NAME:-"document-uploads"}
DATASET_NAME=${BQ_DATASET:-"document_processing"}
TABLE_NAME=${BQ_TABLE:-"metadata"}
SERVICE_NAME="document-processor"
SERVICE_ACCOUNT_NAME="doc-processor-sa"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Deploying to Project: ${PROJECT_ID} in Region: ${REGION}"

# 1. Enable Required APIs
echo "Enabling necessary GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    pubsub.googleapis.com \
    storage.googleapis.com \
    bigquery.googleapis.com \
    cloudbuild.googleapis.com

# 2. Create Service Account
echo "Creating Service Account: ${SERVICE_ACCOUNT_EMAIL}..."
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
    --display-name="Document Processor Service Account" || true

# 3. Grant Permissions to Service Account
echo "Granting roles to Service Account..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/run.invoker"

# 4. Create BigQuery Dataset and Table
echo "Creating BigQuery Dataset and Table..."
bq mk -d --location=${REGION} ${PROJECT_ID}:${DATASET_NAME} || true
bq mk -t --schema=filename:STRING,upload_time:TIMESTAMP,tags:STRING,word_count:INTEGER,processed_time:TIMESTAMP \
    ${PROJECT_ID}:${DATASET_NAME}.${TABLE_NAME} || true
# Note: Tags changed to STRING (comma-separated or JSON) for simple CLI schema setup. If you want ARRAY<STRING>, use JSON schema file or BigQuery UI.

# 5. Build and Deploy Cloud Run Service
echo "Deploying Cloud Run Service..."
# Go into app directory
cd app
gcloud run deploy ${SERVICE_NAME} \
    --source . \
    --region ${REGION} \
    --service-account ${SERVICE_ACCOUNT_EMAIL} \
    --set-env-vars BQ_DATASET=${DATASET_NAME},BQ_TABLE=${TABLE_NAME} \
    --no-allow-unauthenticated

SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
echo "Service deployed at: ${SERVICE_URL}"
cd ..

# 6. Create Pub/Sub Topic and GCS Notification
echo "Creating Pub/Sub Topic..."
gcloud pubsub topics create ${TOPIC_NAME} || true

echo "Creating GCS Bucket..."
gcloud storage buckets create gs://${BUCKET_NAME} --location=${REGION} || true

echo "Setting up GCS Notification to Pub/Sub..."
gcloud storage service-agent --project=${PROJECT_ID}
# Give GCS service account publisher role on topic
GCS_SA=$(gcloud storage service-agent --project=${PROJECT_ID} --format="value(email_address)")
gcloud pubsub topics add-iam-policy-binding ${TOPIC_NAME} \
    --member="serviceAccount:${GCS_SA}" \
    --role="roles/pubsub.publisher"

gcloud storage buckets notifications create gs://${BUCKET_NAME} \
    --topic=${TOPIC_NAME} \
    --event-types=OBJECT_FINALIZE || true

# 7. Create Pub/Sub Push Subscription
echo "Creating Pub/Sub Push Subscription to Cloud Run..."
PUBSUB_SA="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")

# Grant Pub/Sub permission to create tokens
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountTokenCreator"

gcloud pubsub subscriptions create ${SERVICE_NAME}-sub \
    --topic=${TOPIC_NAME} \
    --push-endpoint="${SERVICE_URL}/pubsub" \
    --push-auth-service-account=${SERVICE_ACCOUNT_EMAIL} || true

echo "Deployment complete! Upload a file to gs://${BUCKET_NAME} to trigger the pipeline."
