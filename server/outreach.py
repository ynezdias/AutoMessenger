"""Send the opening outreach text to contacts from a CSV.

Usage:
  python -m server.outreach --csv testing.csv --only ynez --dry-run
  python -m server.outreach --csv testing.csv --only ynez

Contacts who already have a conversation on file, or who opted out, are skipped.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from . import config, guardrails, history

OPENER = (
    "Hi {first}, Walter with Pinnacle Point Financial. someone at your business "
    "asked about funding a while back. still looking for working capital?"
)


def load_contacts(csv_path: str, only: str | None) -> list[dict]:
    contacts = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            if not row.get("phone") or not row.get("first_name"):
                continue
            if only and row["first_name"].lower() != only.lower():
                continue
            contacts.append(row)
    return contacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--only", help="only message this first name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    contacts = load_contacts(args.csv, args.only)
    if not contacts:
        sys.exit(f"no matching contacts in {args.csv}")

    dry = args.dry_run or not config.OUTBOUND_QUEUE_URL
    store = history.ConversationStore()
    sqs = None
    if not dry:
        import boto3

        sqs = boto3.client("sqs", region_name=config.AWS_REGION)

    for contact in contacts:
        phone = contact["phone"].replace(" ", "")
        first = contact["first_name"]
        opener = OPENER.format(first=first)

        violations = guardrails.check(opener, config.UPLOAD_LINK)
        if violations:
            sys.exit(f"opener fails guardrails, not sending: {violations}")

        convo = store.get(phone)
        if convo["status"] == "stopped":
            print(f"SKIP {first} {phone}: opted out")
            continue
        if convo["messages"]:
            print(f"SKIP {first} {phone}: conversation already exists "
                  f"({len(convo['messages'])} messages)")
            continue

        if dry:
            print(f"DRY RUN {first} {phone}: {opener!r} [{len(opener)} chars]")
            continue

        convo["merchant_first"] = first
        convo["company"] = contact.get("company", "")
        store.append(convo, "walter", opener)
        store.save(convo)
        sqs.send_message(
            QueueUrl=config.OUTBOUND_QUEUE_URL,
            MessageBody=json.dumps({"phone": phone, "message": opener, "recordId": ""}),
        )
        print(f"QUEUED {first} {phone}: {opener!r}")


if __name__ == "__main__":
    main()
