"""Run with: python -m server.tests.test_optout

Opt-out detection runs before the model, so whatever it misses gets answered
with a sales pitch. The 8/4 eval run caught these phrases being matched only as
a WHOLE message, which let "stop texting me and whats the rate" through.
"""
from server import agent

# Must always stop. A miss here is a TCPA violation.
OPT_OUTS = [
    # carrier keywords, bare
    "stop", "STOP", "Stop.", "stop all", "stopall", "unsubscribe", "quit",
    "cancel", "end", "alto", "parar",
    # the demand buried in a longer message, which is how people actually write
    "stop texting me", "stop texting me and whats the rate", "STOP TEXTING ME",
    "stop texting me!!", "please stop texting me", "stop contacting me",
    "quit calling me", "do not contact me", "dont text me again please",
    "don't text me again", "never text me again",
    "take me off", "please take me off your list", "take me off this list",
    "get me off your list", "remove me", "remove me from your list",
    "leave me alone", "just leave me alone", "i said stop",
    "lose my number", "forget my number", "no longer wish to be contacted",
    # done, only in the conversation-ending sense
    "i am done with you", "i'm done with this", "im done talking",
    "i am done with all this",
    # spanish
    "no me escribas", "no me escriban mas", "no me contactes",
    "dejame en paz", "déjame en paz", "bórrame de la lista",
]

# Must always reach the model. A false positive here silences a live lead.
NOT_OPT_OUTS = [
    # "done" in the upload flow is a merchant finishing a task, not leaving
    "i'm done with the upload", "i'm done with the statements",
    "im done with uploading them", "done", "ok done", "i am done sending them",
    # ordinary words that happen to be carrier keywords
    "stop by my shop tomorrow", "i want to cancel my other advance",
    "end of the month works", "i need to quit my job",
    "can you cancel the other application",
    # normal sales traffic
    "whats the rate", "how much can i get", "call me", "who is this",
    "yes im interested", "i already sent them", "no thanks",
    "send me the link", "my accountant said no",
]


def main():
    failures = []
    for text in OPT_OUTS:
        if not agent.is_hard_opt_out(text):
            failures.append(f"MISSED an opt-out: {text!r}")
    for text in NOT_OPT_OUTS:
        if agent.is_hard_opt_out(text):
            failures.append(f"false positive, would silence a live lead: {text!r}")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print(f"all {len(OPT_OUTS) + len(NOT_OPT_OUTS)} opt-out checks passed "
          f"({len(OPT_OUTS)} stop, {len(NOT_OPT_OUTS)} pass through)")


if __name__ == "__main__":
    main()
