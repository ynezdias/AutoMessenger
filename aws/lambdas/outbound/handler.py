"""Sends agent replies back into Salesforce so Text Torrent delivers the SMS.

Triggered by the outbound SQS queue. Two delivery modes, chosen by SF_MODE:

  SF_MODE=sobject  create a record on SF_SOBJECT using SF_FIELD_MAP, e.g.
                   SF_SOBJECT=TextTorrent__Outbound_SMS__c
                   SF_FIELD_MAP={"TextTorrent__Phone__c": "{phone}",
                                 "TextTorrent__Body__c": "{message}"}
                   (check the exact object/field API names in your Text Torrent
                   install under Setup -> Object Manager)

  SF_MODE=flow     invoke an autolaunched flow named SF_FLOW_API_NAME with
                   inputs phone / message / recordId; the flow calls Text
                   Torrent's own send action.

Auth (SF_GRANT_TYPE):
  client_credentials  Connected App client-credentials flow (SF_CLIENT_ID,
                      SF_CLIENT_SECRET)
  refresh_token       long-lived refresh token (SF_REFRESH_TOKEN, SF_CLIENT_ID;
                      e.g. the Salesforce CLI's PlatformCLI client)
"""
import json
import os
import time
import urllib.parse
import urllib.request

SF_TOKEN_URL = os.environ["SF_TOKEN_URL"]  # https://yourdomain.my.salesforce.com/services/oauth2/token
SF_GRANT_TYPE = os.environ.get("SF_GRANT_TYPE", "client_credentials")
SF_CLIENT_ID = os.environ["SF_CLIENT_ID"]
SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET", "")
SF_REFRESH_TOKEN = os.environ.get("SF_REFRESH_TOKEN", "")
SF_MODE = os.environ.get("SF_MODE", "sobject")
SF_SOBJECT = os.environ.get("SF_SOBJECT", "")
SF_FIELD_MAP = json.loads(os.environ.get("SF_FIELD_MAP", "{}"))
SF_FLOW_API_NAME = os.environ.get("SF_FLOW_API_NAME", "")
SF_API_VERSION = os.environ.get("SF_API_VERSION", "v61.0")

_token_cache = {"access_token": "", "instance_url": "", "expires_at": 0.0}


def _get_token():
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache
    if SF_CLIENT_ID.startswith("REPLACE"):
        raise RuntimeError(
            "Salesforce is not configured yet. Update the stack parameters "
            "SfTokenUrl / SfClientId / SfClientSecret after creating the Connected App."
        )
    if SF_GRANT_TYPE == "refresh_token":
        fields = {
            "grant_type": "refresh_token",
            "client_id": SF_CLIENT_ID,
            "refresh_token": SF_REFRESH_TOKEN,
        }
        if SF_CLIENT_SECRET:
            fields["client_secret"] = SF_CLIENT_SECRET
    else:
        fields = {
            "grant_type": "client_credentials",
            "client_id": SF_CLIENT_ID,
            "client_secret": SF_CLIENT_SECRET,
        }
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(SF_TOKEN_URL, data=body)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    _token_cache.update(
        access_token=data["access_token"],
        instance_url=data["instance_url"],
        expires_at=time.time() + 600,
    )
    return _token_cache


def _sf_post(path, payload):
    token = _get_token()
    req = urllib.request.Request(
        token["instance_url"] + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def _send(phone, message, record_id):
    if SF_MODE == "flow":
        return _sf_post(
            f"/services/data/{SF_API_VERSION}/actions/custom/flow/{SF_FLOW_API_NAME}",
            {"inputs": [{"phone": phone, "message": message, "recordId": record_id}]},
        )
    fields = {
        key: template.format(phone=phone, message=message, recordId=record_id)
        for key, template in SF_FIELD_MAP.items()
    }
    return _sf_post(f"/services/data/{SF_API_VERSION}/sobjects/{SF_SOBJECT}/", fields)


def lambda_handler(event, context):
    # Raise on failure so SQS retries and eventually parks the message in the DLQ.
    for record in event["Records"]:
        body = json.loads(record["body"])
        result = _send(body["phone"], body["message"], body.get("recordId", ""))
        print(json.dumps({"sent": body["phone"], "salesforce": result}))
    return {"ok": True}
