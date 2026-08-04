"""Run with: python -m server.tests.test_hostility

Threats and abuse are decided before the model. Left to it, the 8/4 eval run
showed it answering "i know where you people work" with a pitch about funding
and "my cousin is a cop and hes looking into you" with "I'd appreciate knowing
what's going on" — defending itself and probing feelings, which is exactly what
Walter must never do.

The hard part is the bottom list: doubting Walter is a fair question from a
cold-texted stranger and must still get a real answer.
"""
from server import agent

# Intimidation. Thread ends, human told.
THREATS = [
    "i know where you people work",
    "i know where you live",
    "we know where to find you",
    "my cousin is a cop and hes looking into you",
    "the police are looking into you",
    "watch your back",
    "youll regret this",
    "im coming for you",
    "ill ruin you",
    "ill shut you down",
]

# Personal abuse. Human takes over, Walter says nothing.
ABUSE = [
    "youre a scumbag but i still need the money",
    "ill leave a one star review everywhere",
    "fuck you",
    "stfu",
    "youre a liar",
    "youre an idiot",
    "youre a piece of shit",
    "go to hell",
    "ill report you to the bbb",
    "im reporting you to the attorney general",
]

# Must still reach the model and get a real answer. Doubting a cold texter is
# reasonable, and frustration is not abuse.
LEGITIMATE = [
    "prove youre not a scammer",
    "is this a scam",
    "how do i know youre legit",
    "is this legit",
    "youre wasting my time",
    "this is ridiculous",
    "i dont believe you",
    "third time asking",
    "whats the rate",
    "i know where the bank is",
    "my cousin runs a shop",
    "my brother is a cop",
    "i work from home",
    "can you find out for me",
    "who is this",
    "stop calling me a name i dont use",
]


def main():
    failures = []
    for text in THREATS:
        if not agent.is_threat(text):
            failures.append(f"MISSED a threat, model would answer it: {text!r}")
    for text in ABUSE:
        # an opt-out inside the insult may legitimately claim it first
        if not (agent.is_abusive(text) or agent.is_hard_opt_out(text)):
            failures.append(f"MISSED abuse, model would answer it: {text!r}")
    for text in LEGITIMATE:
        if agent.is_threat(text):
            failures.append(f"false positive (threat), kills a live lead: {text!r}")
        if agent.is_abusive(text):
            failures.append(f"false positive (abuse), kills a live lead: {text!r}")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print(f"all {len(THREATS) + len(ABUSE) + len(LEGITIMATE)} hostility checks passed "
          f"({len(THREATS)} threats, {len(ABUSE)} abuse, "
          f"{len(LEGITIMATE)} pass through)")


if __name__ == "__main__":
    main()
