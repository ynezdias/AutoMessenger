"""AutoMessenger local agent server.

Modes:
  python -m server.main            poll SQS for inbound texts (production)
  python -m server.main --chat     interactive console test, no AWS needed
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from . import agent, config, followup, guardrails, history

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("main")

IDENTITY_HINTS = ("who is this", "who's this", "who are you", "how did you get my number")


def handle_inbound(store: history.ConversationStore, payload: dict, sqs=None,
                   message_id: str | None = None) -> dict:
    """Process one inbound SMS payload and carry out the resulting action."""
    phone = str(payload["phone"]).strip()
    text = str(payload["message"]).strip()

    convo = store.get(phone)
    if message_id and convo.get("last_msg_id") == message_id:
        # SQS delivered this message a second time; never double-text a merchant.
        log.info("%s duplicate delivery of %s, skipping", phone, message_id)
        return {"action": "ignore", "reply": "", "notify_rep": False,
                "merchant_interested": False}
    convo["last_msg_id"] = message_id or ""
    convo["merchant_first"] = payload.get("merchantFirst") or convo.get("merchant_first", "")
    convo["company"] = payload.get("company") or convo.get("company", "")
    convo["record_id"] = payload.get("recordId") or convo.get("record_id", "")

    if convo["status"] == "stopped":
        log.info("%s is opted out, ignoring", phone)
        return {"action": "ignore", "reply": "", "notify_rep": False,
                "merchant_interested": False}

    store.append(convo, "merchant", text, origin=payload.get("origin") or "")

    # Carrier-style opt-out keywords never reach the model.
    if agent.is_hard_opt_out(text):
        convo["status"] = "stopped"
        store.save(convo)
        log.info("%s sent an opt-out keyword, conversation stopped", phone)
        return {"action": "stop", "reply": "", "notify_rep": False,
                "merchant_interested": False}

    # Track repeated identity questions so the model's trolling rule has signal.
    if any(h in text.lower() for h in IDENTITY_HINTS):
        convo["identity_streak"] = int(convo.get("identity_streak", 0)) + 1
    else:
        convo["identity_streak"] = 0

    result = agent.respond(convo, text)
    action = result["action"]

    if result.get("merchant_interested"):
        convo["merchant_interested"] = True

    reply = result.get("reply")
    if action == "reply" and reply and isinstance(reply, str):
        store.append(convo, "walter", reply)
        _send_outbound(sqs, phone, result["reply"], convo)
    elif action == "stop":
        convo["status"] = "stopped"
    elif action.startswith("escalate_"):
        convo["status"] = "escalated"

    if action.startswith("escalate_") or result.get("notify_rep"):
        _notify_rep(phone, action, text, convo)

    store.save(convo)
    return result


def _send_outbound(sqs, phone: str, message: str, convo: dict) -> None:
    # Last line of defense: whatever upstream does, this function never emits
    # an empty or rule-breaking text. Refusing is always safer than sending.
    if not message or not message.strip():
        log.error("REFUSED empty outbound to %s", phone)
        return
    violations = guardrails.check(message, config.UPLOAD_LINK)
    if violations:
        log.error("REFUSED outbound to %s, guardrail violations: %s", phone, violations)
        return
    if sqs is None or not config.OUTBOUND_QUEUE_URL:
        log.info("[dry run] would send to %s: %s", phone, message)
        return
    sqs.send_message(
        QueueUrl=config.OUTBOUND_QUEUE_URL,
        MessageBody=json.dumps(
            {"phone": phone, "message": message, "recordId": convo.get("record_id", "")}
        ),
    )
    log.info("queued outbound to %s", phone)


def _notify_rep(phone: str, action: str, last_text: str, convo: dict) -> None:
    log.info("REP NOTIFICATION %s %s: %s", action, phone, last_text)
    if not config.ESCALATIONS_TOPIC_ARN:
        return
    import boto3

    boto3.client("sns", region_name=config.AWS_REGION).publish(
        TopicArn=config.ESCALATIONS_TOPIC_ARN,
        Subject=f"AutoMessenger {action}: {phone}",
        Message=(
            f"Action: {action}\nPhone: {phone}\n"
            f"Name: {convo.get('merchant_first', '')}\n"
            f"Salesforce record: {convo.get('record_id', '')}\n"
            f"Interested: {convo.get('merchant_interested', False)}\n"
            f"Their last message: {last_text}"
        ),
    )


def run_worker() -> None:
    if not config.INBOUND_QUEUE_URL:
        sys.exit("INBOUND_QUEUE_URL is not set. Copy server/.env.example to "
                 "server/.env and fill in the stack outputs first.")
    import socket

    # Single-instance lock: two workers polling the same queue would race each
    # other. The socket stays bound for the life of the process.
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 8766))
    except OSError:
        sys.exit("another AutoMessenger worker is already running, exiting")

    import boto3

    sqs = boto3.client("sqs", region_name=config.AWS_REGION)
    store = history.ConversationStore()
    log.info("polling %s with model %s", config.INBOUND_QUEUE_URL, config.OLLAMA_MODEL)
    if config.FOLLOWUP_ENABLED:
        log.info("follow-ups on: up to %d, %dh apart, between %d:00 and %d:00 local",
                 config.FOLLOWUP_MAX_ATTEMPTS, config.FOLLOWUP_AFTER_HOURS,
                 config.FOLLOWUP_START_HOUR, config.FOLLOWUP_END_HOUR)

    last_sweep = 0.0
    while True:
        # Quiet merchants are chased here rather than on a separate schedule:
        # the worker is the one always-on process, and being single-instance it
        # cannot race itself into sending a merchant two nudges.
        if (config.FOLLOWUP_ENABLED
                and time.time() - last_sweep >= config.FOLLOWUP_SWEEP_SECONDS):
            last_sweep = time.time()
            try:
                followup.sweep(
                    store,
                    lambda phone, text, convo: _send_outbound(sqs, phone, text, convo),
                )
            except followup.NotPermitted as exc:
                # Expected until the stack is redeployed; one clear line beats a
                # traceback every sweep.
                log.error("follow-ups are off: %s", exc)
            except Exception:
                # A bad sweep must never stop the worker answering live texts.
                log.exception("follow-up sweep failed, continuing to poll")

        try:
            resp = sqs.receive_message(
                QueueUrl=config.INBOUND_QUEUE_URL,
                MaxNumberOfMessages=5,
                WaitTimeSeconds=20,
            )
        except Exception:
            # Network blips must not kill the worker; back off and re-poll.
            log.exception("poll failed, retrying in 15s")
            time.sleep(15)
            continue
        for raw in resp.get("Messages", []):
            try:
                # Generation can take several minutes across retries; keep the
                # message invisible so a second worker/redelivery can't race us.
                sqs.change_message_visibility(
                    QueueUrl=config.INBOUND_QUEUE_URL,
                    ReceiptHandle=raw["ReceiptHandle"],
                    VisibilityTimeout=1800,
                )
            except Exception:
                log.warning("could not extend visibility for %s", raw.get("MessageId"))
            try:
                payload = json.loads(raw["Body"])
                result = handle_inbound(store, payload, sqs, raw.get("MessageId"))
                log.info("handled %s -> %s", payload.get("phone"), result["action"])
                sqs.delete_message(
                    QueueUrl=config.INBOUND_QUEUE_URL,
                    ReceiptHandle=raw["ReceiptHandle"],
                )
            except Exception:
                log.exception("failed to handle message; leaving on queue for retry")


def run_chat() -> None:
    store = history.ConversationStore()
    phone = "+15550000000"
    print("Local test chat as the merchant. Ctrl+C or 'exit' to quit.")
    first = input("Merchant first name [Sam]: ").strip() or "Sam"
    while True:
        try:
            text = input("merchant> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not text or text.lower() == "exit":
            break
        result = handle_inbound(
            store, {"phone": phone, "message": text, "merchantFirst": first}
        )
        print(f"[action={result['action']} notify_rep={result['notify_rep']} "
              f"interested={result['merchant_interested']}]")
        if result["reply"]:
            print(f"walter> {result['reply']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat", action="store_true", help="interactive local test")
    args = parser.parse_args()
    run_chat() if args.chat else run_worker()
