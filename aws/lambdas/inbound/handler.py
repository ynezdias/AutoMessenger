"""Receives the Salesforce/Text Torrent webhook and queues the text for the local agent.

Expected POST body (JSON):
  {"phone": "+15551234567", "message": "text body",
   "merchantFirst": "Sam", "company": "Acme LLC", "recordId": "003..."}
Auth: header X-Auth-Token must equal the WEBHOOK_SECRET environment variable.
"""
import hmac
import json
import os

import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["INBOUND_QUEUE_URL"]
SECRET = os.environ["WEBHOOK_SECRET"]


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    token = headers.get("x-auth-token", "")
    if not hmac.compare_digest(token, SECRET):
        return _resp(401, {"error": "unauthorized"})

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON"})

    phone = str(payload.get("phone", "")).strip()
    message = str(payload.get("message", "")).strip()
    if not phone or not message:
        return _resp(400, {"error": "phone and message are required"})

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(
            {
                "phone": phone,
                "message": message,
                "merchantFirst": str(payload.get("merchantFirst", "")).strip(),
                "company": str(payload.get("company", "")).strip(),
                "recordId": str(payload.get("recordId", "")).strip(),
            }
        ),
    )
    return _resp(200, {"queued": True})
