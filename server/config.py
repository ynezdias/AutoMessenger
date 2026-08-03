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
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
PROMPT_MAX_MESSAGES = int(os.environ.get("PROMPT_MAX_MESSAGES", "12"))

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

# Local JSON fallback store used when CONVERSATIONS_TABLE is not set (offline testing).
LOCAL_STORE_PATH = ROOT / "server" / ".local_conversations.json"

SYSTEM_PROMPT_PATH = ROOT / "prompts" / "walter_system.txt"
