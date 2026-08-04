"""Run with: python -m server.tests.test_followup"""
import time

from server import config, followup, guardrails

HOUR = 3600
DAY = 24 * HOUR
# Fixed noon so the quiet-hours guard never makes the suite time-of-day dependent.
NOW = time.mktime(time.strptime("2026-08-04 12:00", "%Y-%m-%d %H:%M"))


def convo(role="walter", age=2 * DAY, sent=0, status="active", messages=None):
    if messages is None:
        messages = [{"role": role, "text": "hey", "ts": int(NOW - age)}]
    return {"phone": "+15550001111", "status": status, "merchant_first": "Sam",
            "company": "Acme", "record_id": "", "merchant_interested": False,
            "identity_streak": 0, "last_msg_id": "", "followups_sent": sent,
            "messages": messages}


CASES = [
    # (description, convo, should a nudge go out)
    ("quiet 2 days after Walter's text", convo(), True),
    ("quiet exactly at the threshold", convo(age=24 * HOUR), True),
    ("only 23 hours of silence", convo(age=23 * HOUR), False),
    ("merchant answered last", convo(role="merchant"), False),
    ("opted out", convo(status="stopped"), False),
    ("with a human", convo(status="escalated"), False),
    ("no messages at all", convo(messages=[]), False),
    ("first nudge already sent", convo(sent=1), True),
    ("both nudges already sent", convo(sent=2), False),
    ("somehow over the cap", convo(sent=7), False),
]


def main():
    failures = []

    # Every nudge has to survive the same guardrails as any outgoing text, or it
    # would be silently refused at send time for every quiet merchant at once.
    for i, template in enumerate(followup.NUDGES):
        text = template.format(first="Sam")
        v = guardrails.check(text, config.UPLOAD_LINK)
        if v:
            failures.append(f"nudge {i + 1} fails guardrails: {v} -> {text!r}")
    if len(set(followup.NUDGES)) != len(followup.NUDGES):
        failures.append("the nudges repeat each other")
    if len(followup.NUDGES) < config.FOLLOWUP_MAX_ATTEMPTS:
        failures.append(f"only {len(followup.NUDGES)} nudges for "
                        f"{config.FOLLOWUP_MAX_ATTEMPTS} attempts")

    for label, c, expected in CASES:
        got = bool(followup.due(c, NOW))
        if got != expected:
            failures.append(f"{label}: due={got}, expected {expected}")

    # The cap has to hold across a real sequence, not just a single check.
    c = convo()
    texts = []
    for _ in range(5):
        text = followup.due(c, NOW)
        if not text:
            break
        texts.append(text)
        c["followups_sent"] += 1
        c["messages"].append({"role": "walter", "text": text, "ts": int(NOW - 2 * DAY)})
    if len(texts) != config.FOLLOWUP_MAX_ATTEMPTS:
        failures.append(f"sent {len(texts)} nudges, cap is {config.FOLLOWUP_MAX_ATTEMPTS}")
    if len(set(texts)) != len(texts):
        failures.append(f"sent the same nudge twice: {texts}")

    # A merchant reply between nudges ends the chase.
    c = convo(sent=1)
    c["messages"].append({"role": "merchant", "text": "who is this", "ts": int(NOW - DAY)})
    if followup.due(c, NOW):
        failures.append("nudged a merchant who had replied")

    # Quiet hours.
    for hour, expected in ((3, False), (8, False), (9, True), (12, True),
                           (18, True), (19, False), (23, False)):
        at = time.mktime(time.strptime(f"2026-08-04 {hour:02d}:30", "%Y-%m-%d %H:%M"))
        if followup.within_sending_window(at) != expected:
            failures.append(f"sending window at {hour}:30 should be {expected}")

    # sweep() must record the attempt and hand the text to the sender exactly once.
    sent_calls = []

    class FakeStore:
        def __init__(self, convos):
            self.convos = convos
            self.saves = 0

        def list_all(self):
            return self.convos

        def append(self, c, role, text, origin=""):
            c["messages"].append({"role": role, "text": text, "ts": int(NOW)})

        def save(self, c):
            self.saves += 1

    store = FakeStore([convo(), convo(status="stopped"), convo(role="merchant")])
    fired = followup.sweep(store, lambda p, t, c: sent_calls.append((p, t)), NOW)
    if len(fired) != 1:
        failures.append(f"sweep fired {len(fired)} times, expected 1")
    if len(sent_calls) != 1:
        failures.append(f"sweep sent {len(sent_calls)} texts, expected 1")
    if store.saves != 1:
        failures.append(f"sweep saved {store.saves} conversations, expected 1")
    if store.convos[0]["followups_sent"] != 1:
        failures.append("sweep did not record the attempt, so it would resend")
    if store.convos[1]["followups_sent"] != 0:
        failures.append("sweep nudged an opted-out merchant")

    # Nothing goes out at 3am even when conversations are due.
    at_3am = time.mktime(time.strptime("2026-08-04 03:00", "%Y-%m-%d %H:%M"))
    if followup.sweep(FakeStore([convo()]), lambda p, t, c: None, at_3am):
        failures.append("sweep sent during quiet hours")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    checks = len(CASES) + len(followup.NUDGES) + 14
    print(f"all {checks} follow-up checks passed")


if __name__ == "__main__":
    main()
