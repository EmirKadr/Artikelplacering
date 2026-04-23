"""Global constants for Artikelplacering.

No PyQt6 imports here — this module must be importable without Qt installed.
The STYLE stylesheet and Qt-only helpers live in desktop/style.py.
"""
import re as _re

from core.paths import resource_path, user_log_dir

# ── paths ───────────────────────────────────────────────────────────────────
DATA_DIR = resource_path("data")
LOG_DIR = user_log_dir()

# ── image handling ──────────────────────────────────────────────────────────
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

# ── UI colours (one per category column) ───────────────────────────────────
CATEGORY_COLORS = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
    "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FF5722",
]

# ── data parsing ────────────────────────────────────────────────────────────
_EMPTY = {"", "0", "0,00000", "0.00000", "0,0", "0.0"}

# ── AI / LLM defaults ───────────────────────────────────────────────────────
DEFAULT_MODEL       = "qwen2.5-vl-72b-instruct"
DEFAULT_AI_URL      = "http://localhost:1234/v1"

# ── classification tuning ───────────────────────────────────────────────────
MAX_EXAMPLES_PER_CAT = 10   # manually classified articles used per category in step 1
MAX_OVRIGT_EXAMPLES  = 50   # Övrigt gets more examples since it's more diverse
EXT_IMAGES_PER_CAT   = 10   # max images per category in external step 1
EXT_BATCH_SIZE       = 1    # articles per API call in external step 2
AI_JOB_MIN_PER_CAT   = 0    # minimum examples per category to unlock AI job button
AI_PARALLEL_WORKERS  = 3    # number of parallel classification requests in step 2

DEFAULT_SYFTE = (
    "Kategorisera artiklar för att stödja pallbyggnation. "
    "Klassificeringen ska bygga främst på fysisk form och förpackningstyp, "
    "så att artiklar med liknande hantering, stabilitet och staplingssätt "
    "hamnar i samma kategori."
)

# ── external AI providers ───────────────────────────────────────────────────
DEFAULT_EXTERNAL_PROVIDERS = {
    "Gemini (Google)": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
    },
    "MiniMax": {
        "url": "https://api.minimax.io/v1/chat/completions",
        "model": "MiniMax-M2.5",
    },
    "OpenAI": {
        "url": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "Anthropic (via OpenRouter)": {
        "url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-sonnet-4",
    },
}

# ── filename sanitization ───────────────────────────────────────────────────
_WIN_INVALID = _re.compile(r'[\\/:*?"<>|]')


def safe_name(name: str) -> str:
    """Replace Windows-invalid filename characters with readable alternatives."""
    name = name.replace(">=", "gte").replace("<=", "lte")
    name = name.replace(">", "gt").replace("<", "lt")
    return _WIN_INVALID.sub("_", name).strip()


# Keep the leading-underscore alias used throughout GamlaAppen.py
_safe_name = safe_name
