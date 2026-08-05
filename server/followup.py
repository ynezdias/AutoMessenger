"""Nudge conversations that went quiet.

A merchant who stops answering gets at most FOLLOWUP_MAX_ATTEMPTS follow-ups,
each one FOLLOWUP_AFTER_HOURS after the last thing Walter said, and never once
they opt out or the thread reaches a human.

The nudges are fixed text rather than model-written. A nudge is formulaic, so
there is nothing for the model to add, and a canned line cannot invent a policy,
drift off persona, or leak a JSON value the way a generated one can. They still
pass through guardrails before sending, exactly like the opener does.

The worker sweeps on a timer; this module is also runnable on its own to see
what would go out without sending anything:

    python -m server.followup --dry-run
"""
from __future__ import annotations

import logging
import time

from . import config, guardrails, history

log = logging.getLogger("followup")

# One per attempt, so the second nudge never repeats the first. Walter's rules
# apply: no dashes, no digits, no amounts, one short text.
NUDGES = (
    "Hey {first}, Walter again with Pinnacle Point Financial. did you still "
    "want to look at funding for the business?",
    "Hey {first}, last note from me. if funding is ever something you want to "
    "look at, just text me back and I'll pick it up from there.",
)


class NotPermitted(RuntimeError):
    """The store cannot be enumerated, so no follow-up can be found."""


def _conversations(store: history.ConversationStore) -> list[dict]:
    """Every conversation, with a readable error when Scan is not granted.

    The worker's IAM user only needs GetItem/PutItem to answer texts, so a stack
    deployed before follow-ups existed will refuse the sweep's Scan.
    """
    try:
        return store.list_all()
    except Exception as exc:
        detail = repr(exc)
        if "AccessDenied" in detail and "Scan" in detail:
            raise NotPermitted(
                "the worker's IAM user is not allowed to run dynamodb:Scan, "
                "which the follow-up sweep needs to find quiet conversations. "
                "aws/template.yaml already grants it, so deploy the stack "
                "(sam deploy) and restart the worker."
            ) from exc
        raise


def within_sending_window(now: float) -> bool:
    """Quiet-hours guard, in the server's local time."""
    hour = time.localtime(now).tm_hour
    return config.FOLLOWUP_START_HOUR <= hour < config.FOLLOWUP_END_HOUR


def due(convo: dict, now: float) -> str:
    """The nudge this conversation has earned, or "" when it is not due one."""
    # Opted out or already with a human: never chase.
    if convo.get("status") != "active":
        return ""

    sent = int(convo.get("followups_sent", 0))
    if sent >= config.FOLLOWUP_MAX_ATTEMPTS or sent >= len(NUDGES):
        return ""

    messages = convo.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    # They answered. Nothing to chase, and the agent owns the reply.
    if last.get("role") != "walter":
        return ""
    if now - int(last["ts"]) < config.FOLLOWUP_AFTER_HOURS * 3600:
        return ""

    first = convo.get("merchant_first") or config.DEFAULT_FIRST_NAME
    return NUDGES[sent].format(first=first)


def sweep(store: history.ConversationStore, send, now: float | None = None) -> list[dict]:
    """Send every follow-up that is due. Returns what went out.

    send(phone, text, convo) does the actual delivery, so the caller's hardened
    outbound path (and its guardrail check) is reused rather than duplicated.
    """
    now = time.time() if now is None else now
    if not within_sending_window(now):
        return []

    fired = []
    for convo in _conversations(store):
        text = due(convo, now)
        if not text:
            continue
        violations = guardrails.check(text, config.UPLOAD_LINK)
        if violations:
            # A bad template would otherwise go to every quiet merchant at once.
            log.error("follow-up template fails guardrails, not sending: %s", violations)
            continue

        # Record before sending: a crash mid-send costs one missed nudge, while
        # the other order costs a merchant a duplicate text.
        attempt = int(convo.get("followups_sent", 0)) + 1
        store.append(convo, "walter", text)
        convo["followups_sent"] = attempt
        store.save(convo)

        log.info("follow-up %d/%d to %s", attempt, config.FOLLOWUP_MAX_ATTEMPTS,
                 convo["phone"])
        send(convo["phone"], text, convo)
        fired.append({"phone": convo["phone"], "attempt": attempt, "text": text})

    return fired


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="list what is due without sending or recording it")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    store = history.ConversationStore()
    now = time.time()
    if args.dry_run:
        if not within_sending_window(now):
            print(f"outside the sending window "
                  f"({config.FOLLOWUP_START_HOUR}:00 to {config.FOLLOWUP_END_HOUR}:00 "
                  f"local), nothing would send right now")
        try:
            convos = _conversations(store)
        except NotPermitted as exc:
            raise SystemExit(f"cannot check follow-ups: {exc}")
        due_now = [c for c in convos if due(c, now)]
        for convo in due_now:
            print(f"DUE {convo['phone']} "
                  f"(attempt {int(convo.get('followups_sent', 0)) + 1}): "
                  f"{due(convo, now)!r}")
        print(f"{len(due_now)} of {len(convos)} conversations are due a follow-up")
        return

    import json

    sqs = None
    if config.OUTBOUND_QUEUE_URL:
        import boto3

        sqs = boto3.client("sqs", region_name=config.AWS_REGION)

    def send(phone: str, text: str, convo: dict) -> None:
        if sqs is None:
            log.info("[dry run] would send to %s: %s", phone, text)
            return
        sqs.send_message(
            QueueUrl=config.OUTBOUND_QUEUE_URL,
            MessageBody=json.dumps({"phone": phone, "message": text,
                                    "recordId": convo.get("record_id", "")}),
        )

    for row in sweep(store, send, now):
        print(f"SENT {row['phone']} (attempt {row['attempt']}): {row['text']!r}")


if __name__ == "__main__":
    main()
