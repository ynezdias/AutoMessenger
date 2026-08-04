"""Run with: python -m server.tests.test_guardrails"""
from server import guardrails

LINK = "https://secure.example.com/upload-abc123"

CLEAN = [
    "all I need is your last 3 months of bank statements and I can get you real numbers",
    "no rush, whenever you can send those over i'll take a look same day",
    f"just upload your last 3 or 4 months right here: {LINK}",
    "still Walter at Pinnacle Point Financial, we talked a while back",
    "totally secure, the page is encrypted and only used for your statements",
    "claro, envíe sus estados de cuenta de los últimos 3 o 4 meses y le doy una respuesta hoy",
    # the leaked-value rule is exact-match, so these words inside a real text stay fine
    "that is not true, we spoke about your business last month",
    "none of that changes what I need from you",
]

DIRTY = {
    "we can get you $50,000 by friday": "dollar amount",
    "rates start at 8%": "percent",
    "send your last 3-4 months": "dash",
    "usually a few thousand depending on deposits": "amount word",
    "I'd be happy to circle back tomorrow": "corporate phrase",
    "yep just shoot them over": "banned words",
    "u can send them whenever": "text speak",
    "great, sounds good \U0001F44D": "emoji",
    "check out www.pinnaclepoint.com for details": "foreign link",
    "email me at walter@ppf.com": "email",
    "it works like a factor rate deal": "structure term",
    "": "empty",
    # the model leaks the boolean it means for notify_rep into the reply slot
    "false": "leaked JSON value",
    "true": "leaked JSON value",
    "False.": "leaked JSON value, capitalized with punctuation",
    "null": "leaked JSON value",
}

STRIP_CASES = {
    "perfect, just upload them here": "just upload them here",
    "got it, i'll take a look same day": "i'll take a look same day",
    "sounds good. send them over when ready": "send them over when ready",
    "no problem at all": "no problem at all",  # "no" is not an ack opener
}


def main():
    failures = []
    for text in CLEAN:
        v = guardrails.check(text, LINK)
        if v:
            failures.append(f"false positive: {text!r} -> {v}")
    for text, label in DIRTY.items():
        if not guardrails.check(text, LINK):
            failures.append(f"missed violation ({label}): {text!r}")
    for raw, expected in STRIP_CASES.items():
        got = guardrails.sanitize(raw)
        if got.lower() != expected.lower():
            failures.append(f"strip: {raw!r} -> {got!r}, expected {expected!r}")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print(f"all {len(CLEAN) + len(DIRTY) + len(STRIP_CASES)} guardrail checks passed")


if __name__ == "__main__":
    main()
