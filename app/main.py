import base64
import json
import os
import random
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Request
from google.cloud import storage
from google.cloud import bigquery

app = FastAPI(title="Document Processor")

# Initialize clients lazily
storage_client = None
bq_client = None

def get_storage_client() -> storage.Client:
    global storage_client
    if storage_client is None:
        storage_client = storage.Client()
    return storage_client

def get_bq_client() -> bigquery.Client:
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client()
    return bq_client

def process_file(bucket_name: str, object_name: str) -> Dict[str, Any]:
    """
    Downloads the file from GCS, simulates OCR/metadata extraction.
    """
    # Initialize mock data
    word_count = 0
    tags: List[str] = []
    
    # Optionally, we can skip actual download in offline test mode
    if os.environ.get("SKIP_GCS_DOWNLOAD") != "1":
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        try:
            content = blob.download_as_bytes()
        except Exception as e:
            print(f"Error downloading {object_name} from {bucket_name}: {e}")
            raise

        # Process text files specifically
        if object_name.lower().endswith(".txt"):
            text = content.decode('utf-8', errors='ignore')
            words = text.split()
            word_count = len(words)
            # Simple tag extraction: unique words longer than 5 chars, top 5
            long_words = [w.strip(".,!?()[]{}\"'") for w in words if len(w) > 5]
            word_freq = {}
            for w in long_words:
                w_lower = w.lower()
                word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
            sorted_words = sorted(word_freq.items(), key=lambda item: item[1], reverse=True)
            tags = [w[0] for w in sorted_words[:5]]
        else:
            # Simulate OCR for PDF/images
            print(f"Simulating OCR for non-text file: {object_name}")
            word_count = random.randint(100, 5000)
            mock_tags_pool = ["invoice", "report", "receipt", "confidential", "scan", "diagram", "chart"]
            tags = random.sample(mock_tags_pool, k=min(3, len(mock_tags_pool)))
    else:
        # Offline simulation
        print(f"Skipping GCS download for {object_name} (offline mode)")
        word_count = random.randint(50, 1000)
        tags = ["offline", "test", "mock"]

    return {
        "filename": object_name,
        "upload_time": datetime.utcnow().isoformat(),  # Use current UTC as approximation
        "tags": ", ".join(tags),
        "word_count": word_count,
        "processed_time": datetime.utcnow().isoformat(),
    }

def stream_to_bigquery(record: Dict[str, Any]):
    """
    Streams the metadata record to BigQuery.
    """
    if os.environ.get("SKIP_BQ_INSERT") == "1":
        print(f"Skipping BigQuery insert for {record['filename']} (offline mode)")
        return
        
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    dataset_id = os.environ.get("BQ_DATASET", "document_processing")
    table_id = os.environ.get("BQ_TABLE", "metadata")
    
    client = get_bq_client()
    
    # If project_id is available in env or inferred by client, construct table ref
    # If project_id is missing, client.project is usually populated by default creds
    proj = project_id if project_id else client.project
    table_ref = f"{proj}.{dataset_id}.{table_id}"
    
    print(f"Streaming to BigQuery table: {table_ref}")
    
    errors = client.insert_rows_json(table_ref, [record])
    if errors:
        print(f"Errors occurred while inserting rows: {errors}")
        raise Exception(f"BigQuery insert failed: {errors}")

@app.post("/pubsub")
async def handle_pubsub_message(request: Request):
    """
    Endpoint for Cloud Pub/Sub push subscription.
    """
    try:
        body = await request.json()
        print(f"Received Pub/Sub message body: {json.dumps(body)}")
        
        message = body.get("message", {})
        attributes = message.get("attributes", {})
        
        # GCS notifications put bucketId and objectId in attributes
        bucket_name = attributes.get("bucketId")
        object_name = attributes.get("objectId")
        
        if not bucket_name or not object_name:
            print("Missing bucketId or objectId in attributes. Attempting to parse data payload.")
            data = message.get("data")
            if data:
                decoded_data = base64.b64decode(data).decode('utf-8')
                data_json = json.loads(decoded_data)
                bucket_name = data_json.get("bucket")
                object_name = data_json.get("name")
        
        if not bucket_name or not object_name:
            error_msg = "Could not find bucket or object name in message"
            print(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
            
        print(f"Processing file: gs://{bucket_name}/{object_name}")
        
        # Process file
        record = process_file(bucket_name, object_name)
        
        # Stream to BigQuery
        stream_to_bigquery(record)
        
        print(f"Successfully processed and recorded {object_name}")
        return {"status": "success", "file": object_name}
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        # Return 500 so Pub/Sub retries the message if needed
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
