"""Provider defaults and the shared, persisted usage-level contract."""

DEFAULT_MODELS = {
    "openai": "gpt-6-luna",
    "google": "gemini-3.8-flash",
    "anthropic": "claude-sonnet-5-5",
}
USAGE_LEVELS = ("low", "medium", "high")
# Minimum room for reasoning plus a useful answer; task-specific larger limits win.
OUTPUT_TOKEN_FLOORS = {"low": 4096, "medium": 8192, "high": 16384}


def normalize_usage_level(value=None):
    level = str(value or "medium").strip().lower()
    if level not in USAGE_LEVELS:
        raise ValueError("Usage level must be low, medium, or high")
    return level
