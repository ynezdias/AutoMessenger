"""Configuration loaded from environment variables (and an optional .env file)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / "server" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# --- Ollama ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.6"))
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "300"))
# Must comfortably hold the persona (~6.6k tokens as of Aug 2026) + capped
# history + guardrail retries. Overflow silently truncates the persona away.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
PROMPT_MAX_MESSAGES = int(os.environ.get("PROMPT_MAX_MESSAGES", "12"))
# One SMS plus the JSON wrapper is ~120 tokens. Capping generation stops a
# runaway completion from costing minutes of CPU time on a single reply.
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "220"))

# --- Business ---
UPLOAD_LINK = os.environ.get("UPLOAD_LINK", "")
DEFAULT_FIRST_NAME = os.environ.get("DEFAULT_FIRST_NAME", "there")

# --- AWS ---
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
INBOUND_QUEUE_URL = os.environ.get("INBOUND_QUEUE_URL", "")
OUTBOUND_QUEUE_URL = os.environ.get("OUTBOUND_QUEUE_URL", "")
CONVERSATIONS_TABLE = os.environ.get("CONVERSATIONS_TABLE", "")
ESCALATIONS_TOPIC_ARN = os.environ.get("ESCALATIONS_TOPIC_ARN", "")

# --- Agent behavior ---
MAX_GENERATION_RETRIES = int(os.environ.get("MAX_GENERATION_RETRIES", "3"))
HISTORY_MAX_MESSAGES = int(os.environ.get("HISTORY_MAX_MESSAGES", "40"))

# --- Follow-ups ---
# A merchant who goes quiet gets nudged at most MAX_ATTEMPTS times, each one
# AFTER_HOURS past the last thing Walter said. The hour window is a quiet-hours
# guard so an automated text never lands at 3am; it is the SERVER's local time,
# so set it conservatively when contacts span time zones.
FOLLOWUP_ENABLED = os.environ.get("FOLLOWUP_ENABLED", "1").lower() not in ("0", "false")
FOLLOWUP_AFTER_HOURS = int(os.environ.get("FOLLOWUP_AFTER_HOURS", "24"))
FOLLOWUP_MAX_ATTEMPTS = int(os.environ.get("FOLLOWUP_MAX_ATTEMPTS", "2"))
FOLLOWUP_START_HOUR = int(os.environ.get("FOLLOWUP_START_HOUR", "9"))
FOLLOWUP_END_HOUR = int(os.environ.get("FOLLOWUP_END_HOUR", "19"))
# How often the worker looks for due follow-ups. Cheap for a JSON file, a full
# table scan on DynamoDB, so not every poll.
FOLLOWUP_SWEEP_SECONDS = int(os.environ.get("FOLLOWUP_SWEEP_SECONDS", "300"))

# Local JSON fallback store used when CONVERSATIONS_TABLE is not set (offline testing).
LOCAL_STORE_PATH = ROOT / "server" / ".local_conversations.json"

SYSTEM_PROMPT_PATH = ROOT / "prompts" / "walter_system.txt"
