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
    "i would be happy to", "i'm happy to", "im happy to", "factor rate",
    "not a factor", "traditional rate", "like i said", "as i mentioned",
    # invented policy claims (fees are never discussed, only escalated)
    "no fee", "no fees", "don't charge", "dont charge", "we don't collect",
    "nothing upfront", "free to apply", "no cost",
    # assistant-speak: reads like a machine, never like Walter
    "i'm here to help", "im here to help", "here to help with",
    "happy to help", "happy to answer", "how can i assist", "assist you",
    "assistance", "funding needs", "funding options",
    "can you tell me more", "what's on your mind", "whats on your mind",
    "i understand your concern", "understand your concern",
    "i completely understand", "are you experiencing", "feel free",
    "don't hesitate", "dont hesitate", "as an ai", "language model",
    "my purpose is",
)

# Values the model leaks into the reply slot instead of writing a text. Under
# JSON-schema decoding it will emit the boolean it means for notify_rep as the
# string "false", which breaks no other rule and would otherwise be sent as-is.
_LEAKED_JSON_VALUE = re.compile(
    r"(true|false|null|none|undefined|nan|n/?a)[.!]?", re.IGNORECASE
)

# Words that characterize deal size / pricing even without digits.
_AMOUNT_WORDS = (
    "thousand", "thousands", "million", "millions", "hundred", "hundreds",
    "grand", "figures", "percent", "percentage", "apr",
    # approval promises and structure claims are never allowed in a reply
    "guarantee", "guaranteed", "guarantees",
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
            # Only strip when the opener is set off by punctuation ("perfect, ...").
            # A bare space means the word starts a real sentence ("great to hear
            # that ..."), and stripping it leaves a broken fragment.
            if rest[:1] in (",", ".", "!") or rest == "":
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
    if _LEAKED_JSON_VALUE.fullmatch(text):
        return ["is a bare JSON value, not a text message"]
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


# Contentless assistant-speak. Dropping the sentence is free; rejecting the
# draft costs a full regeneration, which on CPU is another minute of silence.
_FILLER_MARKERS = (
    "i'm here to help", "im here to help", "here to help with", "happy to help",
    "happy to answer", "how can i assist", "assist you", "feel free",
    "don't hesitate", "dont hesitate", "can you tell me more",
    "what's on your mind", "whats on your mind", "i understand your concern",
    "understand your concern", "i completely understand", "are you experiencing",
)


def drop_filler(text: str) -> str:
    """Drop filler sentences, but only when real content survives them."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences
            if not any(marker in s.lower() for marker in _FILLER_MARKERS)]
    remaining = " ".join(kept).strip()
    # Too little left means the filler WAS the message: let check() reject it
    # so the model writes something with substance instead.
    return remaining if len(remaining) >= 25 else text


def sanitize(reply: str) -> str:
    """Light cleanup applied to every reply before sending."""
    if not isinstance(reply, str):
        return ""
    text = strip_ack_opener(reply.strip())
    text = drop_filler(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --- repetition (soft violations) ---
#
# The persona tells Walter to vary his wording, and a small model ignores it:
# it will send "please send your last 3 or 4 months of bank statements" turn
# after turn. These checks are SOFT — they trigger a rewrite, but a draft that
# breaks only these is still sendable, because a repetitive text is a quality
# problem while a human handoff over phrasing is a worse one.

# A shared run this long is a reused sentence, not the unavoidable overlap of
# "your last 3 or 4 months" appearing in two different sentences.
REPEAT_RUN_WORDS = 8
REPEAT_OVERLAP = 0.75


def _norm_words(text: str, upload_link: str = "") -> list[str]:
    lowered = text.lower()
    if upload_link:
        lowered = lowered.replace(upload_link.lower(), " ")
    return re.sub(r"[^0-9a-záéíóúñü]+", " ", lowered).split()


def _longest_shared_run(a: list[str], b: list[str]) -> list[str]:
    best_len = best_end = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], i
        prev = cur
    return a[best_end - best_len:best_end]


def check_repetition(reply: str, previous_replies, upload_link: str = "") -> list[str]:
    """Return reasons this draft parrots one of Walter's own earlier texts."""
    found: list[str] = []
    words = _norm_words(reply, upload_link)
    if not words:
        return found

    for previous in previous_replies:
        prior = _norm_words(previous, upload_link)
        if not prior:
            continue
        if words == prior:
            found.append("this is word for word a text you already sent")
            continue
        run = _longest_shared_run(words, prior)
        if len(run) >= REPEAT_RUN_WORDS:
            found.append(f'reuses the phrase "{" ".join(run)}" from an earlier text')
            continue
        overlap = len(set(words) & set(prior)) / len(set(words) | set(prior))
        if overlap >= REPEAT_OVERLAP:
            found.append("says the same thing as an earlier text with words swapped")

    unique: list[str] = []
    for reason in found:
        if reason not in unique:
            unique.append(reason)
    return unique[:3]
