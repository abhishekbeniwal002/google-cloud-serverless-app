import base64
import json
import urllib.request
import urllib.error

# This script simulates a push notification from Pub/Sub to the local FastAPI service.
URL = "http://localhost:8080/pubsub"

# Sample notification payload for an object being created in GCS
sample_notification = {
    "bucket": "my-local-test-bucket",
    "name": "sample_document.txt",
    "generation": "1587627537231057",
    "timeCreated": "2020-04-23T07:38:57.230Z",
    "updated": "2020-04-23T07:38:57.230Z"
}

# Pub/Sub push endpoints receive a message where `data` is base64 encoded
data_bytes = json.dumps(sample_notification).encode('utf-8')
encoded_data = base64.b64encode(data_bytes).decode('utf-8')

pubsub_message = {
    "message": {
        "attributes": {
            "bucketId": "my-local-test-bucket",
            "objectId": "sample_document.txt",
            "eventType": "OBJECT_FINALIZE"
        },
        "data": encoded_data,
        "messageId": "1234567890",
        "publishTime": "2020-04-23T07:38:57.230Z"
    },
    "subscription": "projects/my-project/subscriptions/my-subscription"
}

req = urllib.request.Request(
    URL,
    data=json.dumps(pubsub_message).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)

print(f"Sending mock Pub/Sub message to {URL} ...")
try:
    with urllib.request.urlopen(req) as response:
        response_body = response.read().decode('utf-8')
        print(f"Response Status: {response.status}")
        print(f"Response Body: {response_body}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(e.read().decode('utf-8'))
except urllib.error.URLError as e:
    print(f"URL Error: Failed to reach {URL}. Is the FastAPI server running?")
    print(f"Reason: {e.reason}")
