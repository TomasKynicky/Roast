"""Read/write per-repo context from ~/.roast/contexts/<hash>.json"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cr.config import CONTEXTS_DIR

MAX_HISTORY = 10


def _context_path(repo_hash: str) -> Path:
    return CONTEXTS_DIR / f"{repo_hash}.json"


def _project_context_path(repo_hash: str) -> Path:
    return CONTEXTS_DIR / f"{repo_hash}-project.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    CONTEXTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_history(repo_hash: str) -> list[dict[str, str]]:
    """Load prior review messages for context (last MAX_HISTORY exchanges)."""
    data = _load(_context_path(repo_hash))
    return data.get("history", [])


def save_review(repo_hash: str, user_message: str, assistant_message: str) -> None:
    """Append a diff+review pair to history, capping at MAX_HISTORY."""
    path = _context_path(repo_hash)
    data = _load(path)
    history: list[dict[str, str]] = data.get("history", [])
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})
    # Keep last MAX_HISTORY*2 messages (each exchange is 2 messages)
    history = history[-(MAX_HISTORY * 2):]
    data["history"] = history
    _save(path, data)


def load_project_context(repo_hash: str) -> str | None:
    """Load saved project review summary."""
    data = _load(_project_context_path(repo_hash))
    return data.get("review")


def save_project_context(repo_hash: str, review: str) -> None:
    """Save project review for future use as system context."""
    _save(_project_context_path(repo_hash), {"review": review})
