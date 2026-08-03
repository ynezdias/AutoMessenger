"""Deterministic output guardrails.

Small local models will occasionally violate the persona's hard rules, so every
outgoing reply passes through here. A reply that cannot be auto-fixed is rejected
and regenerated; if it still fails after retries the message is escalated to a
human instead of being sent.
"""
import re

# Openers the persona says are stripped before sending.
_ACK_OPENERS = (
    "cool", "nice", "great", "awesome", "perfect", "ok", "okay",
    "got it", "sounds good", "alright", "all right", "sure",
)

# Banned anywhere, case-insensitive, matched on word boundaries.
_BANNED_WORDS = (
    "shoot", "shoots", "shooting", "shop", "shops", "shopping", "shopped",
    "nah", "naw", "nope", "yep", "yup", "ya", "u", "ur",
    "gonna", "wanna", "gotta", "kinda", "sup", "lol", "lmao", "omg",
)

_BANNED_PHRASES = (
    "circle back", "at your earliest convenience", "i'd be happy to",
    "i would be happy to", "factor rate", "not a factor", "traditional rate",
    "like i said", "as i mentioned",
)

# Words that characterize deal size / pricing even without digits.
_AMOUNT_WORDS = (
    "thousand", "thousands", "million", "millions", "hundred", "hundreds",
    "grand", "figures", "percent", "percentage", "apr",
)

# The standard funding range is the ONE amount Walter may state, and only in
# its canonical "20k"/"50k" spelling; "$50,000" style stays blocked so the
# model is pushed back to the canonical form on regenerate.
_ALLOWED_RANGE = re.compile(r"\$?\s?\b(?:20|50)k\b", re.IGNORECASE)

_DASHES = "-‐‑‒–—―"

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF←-⇿⬀-⯿️]"
)

_SPANISH_MARKERS = re.compile(
    r"[¿¡ñÑ]|\b(que|para|por|los|las|una|usted|meses|estados|banco|cuenta|enviar|aquí|sí)\b",
    re.IGNORECASE,
)


def _looks_spanish(text: str) -> bool:
    return bool(_SPANISH_MARKERS.search(text))


def strip_ack_opener(text: str) -> str:
    """Remove a leading acknowledgment opener ("perfect, ..." -> "...")."""
    stripped = text.lstrip()
    lowered = stripped.lower()
    for opener in sorted(_ACK_OPENERS, key=len, reverse=True):
        if lowered.startswith(opener):
            rest = stripped[len(opener):]
            if rest[:1] in (",", ".", "!", " ") or rest == "":
                rest = rest.lstrip(" ,.!")
                if rest:
                    return rest[0].upper() + rest[1:] if stripped[0].isupper() else rest
                return rest
    return stripped


def check(reply: str, upload_link: str) -> list[str]:
    """Return a list of rule violations (empty list means the reply is sendable)."""
    violations: list[str] = []
    text = reply.strip()

    if not text:
        return ["empty reply"]
    if len(text) > 320:
        violations.append("longer than 320 characters, keep it to one short text")

    # The upload link is exempt from the dash and digit rules.
    scrubbed = text.replace(upload_link, " ") if upload_link else text

    if any(ch in scrubbed for ch in _DASHES) or ";" in scrubbed:
        violations.append("contains a dash or semicolon")

    if _EMOJI_RE.search(scrubbed):
        violations.append("contains an emoji")

    if re.search(r"https?://|www\.", scrubbed, re.IGNORECASE):
        violations.append("contains a link other than the upload link")

    if "upload link not configured" in scrubbed.lower():
        violations.append(
            "the upload link is not configured, do not mention or promise a link"
        )

    if "@" in scrubbed:
        violations.append("contains an email address or @ symbol")

    # The 20k to 50k funding range is allowed; scrub it before the digit check.
    scrubbed_amounts = _ALLOWED_RANGE.sub(" ", scrubbed)

    # Digits: only 3 and 4 are ever legitimate ("3 or 4 months").
    stray_digits = set(re.findall(r"\d", scrubbed_amounts)) - {"3", "4"}
    if stray_digits or "$" in scrubbed_amounts or "%" in scrubbed_amounts:
        violations.append("contains a number, dollar sign, or percent about the deal")

    lowered = scrubbed.lower()
    spanish = _looks_spanish(scrubbed)
    for phrase in _BANNED_PHRASES:
        if phrase in lowered:
            violations.append(f'banned phrase "{phrase}"')
    for word in _BANNED_WORDS:
        if spanish and word in ("ya", "u"):  # legitimate Spanish words ("ya", "u" = "or")
            continue
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            violations.append(f'banned word "{word}"')
    for word in _AMOUNT_WORDS:
        if re.search(rf"\b{word}\b", lowered):
            violations.append(f'characterizes an amount ("{word}")')

    return violations


def sanitize(reply: str) -> str:
    """Light cleanup applied to every reply before sending."""
    text = strip_ack_opener(reply.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text
