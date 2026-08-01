"""Conversation storage keyed by phone number.

Uses DynamoDB when CONVERSATIONS_TABLE is set; otherwise falls back to a local
JSON file so the agent can be tested before AWS is wired up.
"""
import json
import time

from . import config


class ConversationStore:
    def __init__(self):
        self._table = None
        if config.CONVERSATIONS_TABLE:
            import boto3

            self._table = boto3.resource(
                "dynamodb", region_name=config.AWS_REGION
            ).Table(config.CONVERSATIONS_TABLE)

    # --- public API ---

    def get(self, phone: str) -> dict:
        convo = self._load(phone)
        if convo is None:
            convo = {
                "phone": phone,
                "status": "active",  # active | stopped | escalated
                "merchant_first": "",
                "company": "",
                "record_id": "",
                "merchant_interested": False,
                "identity_streak": 0,
                "last_msg_id": "",
                "messages": [],
            }
        return convo

    def append(self, convo: dict, role: str, text: str) -> None:
        convo["messages"].append({"role": role, "text": text, "ts": int(time.time())})
        convo["messages"] = convo["messages"][-config.HISTORY_MAX_MESSAGES:]

    def save(self, convo: dict) -> None:
        if self._table is not None:
            self._table.put_item(Item=_to_dynamo(convo))
        else:
            data = self._read_local()
            data[convo["phone"]] = convo
            config.LOCAL_STORE_PATH.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )

    # --- internals ---

    def _load(self, phone: str):
        if self._table is not None:
            item = self._table.get_item(Key={"phone": phone}).get("Item")
            return _from_dynamo(item) if item else None
        return self._read_local().get(phone)

    def _read_local(self) -> dict:
        if config.LOCAL_STORE_PATH.exists():
            return json.loads(config.LOCAL_STORE_PATH.read_text(encoding="utf-8"))
        return {}


def render_transcript(convo: dict) -> list[dict]:
    """History as chat messages, with '(N days later)' gap markers the persona expects."""
    rendered = []
    prev_ts = None
    for msg in convo["messages"]:
        text = msg["text"]
        if prev_ts is not None:
            gap_days = int((msg["ts"] - prev_ts) / 86400)
            if gap_days >= 1:
                text = f"({gap_days} day{'s' if gap_days > 1 else ''} later) {text}"
        prev_ts = msg["ts"]
        role = "assistant" if msg["role"] == "walter" else "user"
        rendered.append({"role": role, "content": text})
    return rendered


def _to_dynamo(convo: dict) -> dict:
    item = dict(convo)
    for msg in item["messages"]:
        msg["ts"] = int(msg["ts"])
    return item


def _from_dynamo(item: dict) -> dict:
    convo = dict(item)
    convo["identity_streak"] = int(convo.get("identity_streak", 0))
    convo["messages"] = [
        {"role": m["role"], "text": m["text"], "ts": int(m["ts"])}
        for m in convo.get("messages", [])
    ]
    return convo
