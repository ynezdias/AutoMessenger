"""The Walter agent: builds the prompt, calls Ollama, enforces guardrails."""
import json
import logging
import urllib.request

from . import config, guardrails, history

log = logging.getLogger("agent")

ACTIONS = (
    "reply", "stop", "ignore", "escalate_frustrated", "escalate_hesitant",
    "escalate_application", "escalate_sent_info", "escalate_call",
    "escalate_compliance",
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "reply": {"type": "string"},
        "notify_rep": {"type": "boolean"},
        "merchant_interested": {"type": "boolean"},
    },
    "required": ["action", "reply", "notify_rep", "merchant_interested"],
}

# Deterministic opt-out keywords handled without the model (carrier compliance).
OPT_OUT_KEYWORDS = {"stop", "stopall", "stop all", "unsubscribe", "cancel", "end", "quit"}


def load_system_prompt(merchant_first: str, company: str) -> str:
    prompt = config.SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        prompt.replace("{merchantFirst}", merchant_first or config.DEFAULT_FIRST_NAME)
        .replace("{Company}", company or "their business")
        .replace("{uploadLink}", config.UPLOAD_LINK or "(upload link not configured)")
    )


def is_hard_opt_out(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in OPT_OUT_KEYWORDS


def _call_ollama(messages: list[dict]) -> dict:
    body = json.dumps(
        {
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": config.OLLAMA_TEMPERATURE},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{config.OLLAMA_HOST}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=config.OLLAMA_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return json.loads(payload["message"]["content"])


def respond(convo: dict, incoming_text: str) -> dict:
    """Run one turn. Returns {action, reply, notify_rep, merchant_interested}.

    The reply has passed guardrails when action == "reply"; if the model cannot
    produce a clean reply, the turn degrades to escalate_hesitant so a human
    picks it up instead of a rule-breaking text going out.
    """
    system = load_system_prompt(convo.get("merchant_first", ""), convo.get("company", ""))
    messages = [{"role": "system", "content": system}]
    messages += history.render_transcript(convo)
    messages.append({"role": "user", "content": incoming_text})

    last_violations: list[str] = []
    for attempt in range(config.MAX_GENERATION_RETRIES):
        try:
            result = _call_ollama(messages)
        except Exception:
            log.exception("ollama call failed (attempt %d)", attempt + 1)
            continue

        action = result.get("action")
        if action not in ACTIONS:
            continue
        if action != "reply":
            result["reply"] = ""
            return result

        reply = guardrails.sanitize(result.get("reply", ""))
        last_violations = guardrails.check(reply, config.UPLOAD_LINK)
        if not last_violations:
            result["reply"] = reply
            return result

        log.warning("guardrail violations, regenerating: %s", last_violations)
        messages.append({"role": "assistant", "content": json.dumps(result)})
        messages.append(
            {
                "role": "user",
                "content": (
                    "SYSTEM CHECK: your draft broke these rules: "
                    + "; ".join(last_violations)
                    + ". Rewrite the same idea as one short clean text that follows "
                    "every rule. Respond with the JSON object only."
                ),
            }
        )

    log.error("no clean reply after retries (%s), escalating", last_violations)
    return {
        "action": "escalate_hesitant",
        "reply": "",
        "notify_rep": True,
        "merchant_interested": False,
    }
