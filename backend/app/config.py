"""Runtime configuration, read from environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "continuityos.db"))
SEED_DATA_DIR = BASE_DIR / "seed_data"
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))

# Optional LLM extraction. Any OpenAI-compatible chat-completions endpoint works.
# Groq is the default because it has a free tier.
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or ""
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
# rules | llm | auto  (auto = LLM when a key is present, rules otherwise)
EXTRACTOR = os.getenv("EXTRACTOR", "auto").lower()

SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))
RESEED_ON_START = os.getenv("RESEED_ON_START", "0") == "1"


def extractor_mode() -> str:
    if EXTRACTOR == "rules":
        return "rules"
    if EXTRACTOR == "llm":
        return "llm" if LLM_API_KEY else "rules"
    return "llm" if LLM_API_KEY else "rules"
