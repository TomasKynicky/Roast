"""Read/write ~/.roast/config.json"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CR_DIR = Path.home() / ".roast"
CONFIG_PATH = CR_DIR / "config.json"
CONTEXTS_DIR = CR_DIR / "contexts"

DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_LANG = "en"


def _ensure_dirs() -> None:
    CR_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXTS_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    _ensure_dirs()
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    _ensure_dirs()
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    CONFIG_PATH.chmod(0o600)


def get_api_key() -> str | None:
    return load_config().get("api_key")


def get_model() -> str:
    return load_config().get("model", DEFAULT_MODEL)


def get_lang() -> str:
    return load_config().get("lang", DEFAULT_LANG)
