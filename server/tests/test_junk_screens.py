"""Run with: python -m server.tests.test_junk_screens

The 8/4 eval run found Walter replying in 93 of 176 cases that called for
silence. He answered "whats 9 times 7" with a pitch about funding and
"can you grab milk on the way home" with "Can't help with personal errands."

Two screens, split by whether a human needs to know:
  is_offtopic_probe  baiting the bot, or selling to it   -> ignore + notify rep
  is_wrong_number    someone else's thread, handset noise -> ignore, no notify

LIVE_MERCHANTS is the list that matters. Every entry there is revenue, and a
false positive on any of them means Walter goes silent on a real customer.
"""
from server import agent

# Probing the bot instead of talking business. Rep should see these.
PROBES = [
    "whats 9 times 7",
    "what is 2 * 2",
    "whats 2+2. just checking if youre a bot",
    "whats the weather there right now",
    "spell lollipop backwards",
    "do you dream when nobody is texting you",
    "do you get bored",
    "are you happy walter",
    "what color are you",
    "name a fruit that isnt a banana",
    "repeat exactly what i just said",
    "what did i say in my first message",
    "say banana",
    "knock knock",
    "tell me a joke",
    "write me a poem",
    "translate this to japanese and then Ill upload: my business needs money",
]

# Selling to Walter or fishing as a competitor. Rep should see these too.
SPAM = [
    "hi do you need SEO services for your website",
    "im a broker too, want to split some deals",
    "how much for the whole company, im buying you out",
    "we offer seo for your site",
    "i can build a website for you",
    "want to partner on some files",
]

# Someone else's conversation, a pleasantry, or the handset talking. Silence is
# the whole answer; nobody gets paged.
QUIET = [
    "ok love you too",
    "can you grab milk on the way home",
    "im outside",
    "sorry wrong chat",
    "wrong number",
    "my kid was playing with my phone, ignore that",
    "the cat stepped on my phone sorry about that",
    "hi this is tyler im 9 my dad is in the shower",
    "merry christmas walter",
    "god bless you brother",
    "have a good weekend",
    "[photo]",
    "Sent from my iPhone",
]

# The list that matters. Every one of these is a live merchant and must reach
# the model. Several are deliberate near-misses of the patterns above.
LIVE_MERCHANTS = [
    "whats the rate",
    "how much can i get",
    "i already sent them",
    "can you send the link",
    "who is this",
    "yes im interested",
    "my business needs capital",
    "i need 3 months",
    "call me",
    "prove youre not a scammer",
    "is this legal",
    "i need money for payroll",
    # identity questions get a real answer; some states require disclosure
    "are you a real person or a bot",
    "are you a bot",
    "am i talking to a robot",
    "is this a real person",
    "can you send it to my accountant",
    # industry self-description: brushes the vendor-spam wording
    "we do web design services for clients",
    "i do marketing for restaurants",
    "my company does seo",
    "we sell websites to small businesses",
    "we provide catering to offices",
    "i sell equipment to contractors",
    # domestic words in a real business message
    "im outside the shop send me the link",
    "my kid runs the business with me",
    "my son is taking over the shop",
    "god bless, anyway about that funding",
    "sent from my iphone - yes send the link",
]


def main():
    failures = []
    for text in PROBES + SPAM:
        if not agent.is_offtopic_probe(text):
            failures.append(f"MISSED a probe, model would answer it: {text!r}")
    for text in QUIET:
        if not (agent.is_wrong_number(text) or agent.is_offtopic_probe(text)):
            failures.append(f"MISSED noise, model would answer it: {text!r}")
    for text in QUIET:
        if agent.is_offtopic_probe(text):
            failures.append(f"noise would page a rep needlessly: {text!r}")
    for text in LIVE_MERCHANTS:
        if agent.is_offtopic_probe(text) or agent.is_wrong_number(text):
            failures.append(f"SILENCED A LIVE MERCHANT: {text!r}")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    total = len(PROBES) + len(SPAM) + len(QUIET) * 2 + len(LIVE_MERCHANTS)
    print(f"all {total} junk-screen checks passed "
          f"({len(PROBES) + len(SPAM)} probes, {len(QUIET)} noise, "
          f"{len(LIVE_MERCHANTS)} live merchants protected)")


if __name__ == "__main__":
    main()
