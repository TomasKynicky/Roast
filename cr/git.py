"""Git operations: diff, file detection, repo hash."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def _run(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command, return stdout. Raise GitError on failure."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError:
        raise GitError("git not found — is it installed and on PATH?")

    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout


def assert_git_repo() -> None:
    """Raise GitError if the cwd is not inside a git repo."""
    try:
        _run(["git", "rev-parse", "--git-dir"])
    except GitError:
        raise GitError("Not inside a git repository.")


def get_repo_root() -> Path:
    root = _run(["git", "rev-parse", "--show-toplevel"]).strip()
    return Path(root)


def get_repo_hash() -> str:
    """Stable identifier for this repo: hash of remote URL or absolute path."""
    root = get_repo_root()
    try:
        remote = _run(["git", "remote", "get-url", "origin"]).strip()
        identifier = remote
    except GitError:
        identifier = str(root)
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


def get_diff() -> str:
    """Return full diff: staged + unstaged changes."""
    # Staged changes
    staged = ""
    unstaged = ""
    try:
        # Check if there are any commits
        _run(["git", "rev-parse", "HEAD"])
        has_commits = True
    except GitError:
        has_commits = False

    if has_commits:
        try:
            staged = _run(["git", "diff", "--cached"])
        except GitError:
            staged = ""
        try:
            unstaged = _run(["git", "diff", "HEAD"])
        except GitError:
            unstaged = ""
    else:
        # No commits yet — diff against empty tree
        try:
            empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            staged = _run(["git", "diff", "--cached", empty_tree])
        except GitError:
            staged = ""

    untracked = get_untracked_content()
    parts = [p for p in [staged, unstaged, untracked] if p.strip()]
    return "\n".join(parts)


def get_untracked_content() -> str:
    """Return content of untracked (new) files as a pseudo-diff."""
    try:
        output = _run(["git", "ls-files", "--others", "--exclude-standard"])
    except GitError:
        return ""

    files = [f.strip() for f in output.splitlines() if f.strip()]
    if not files:
        return ""

    root = get_repo_root()
    parts: list[str] = []
    for rel_path in files:
        full_path = root / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(errors="replace")
        except OSError:
            continue
        # Skip binary-looking files
        if "\x00" in content[:1024]:
            parts.append(f"--- /dev/null\n+++ b/{rel_path}\n[binary file]\n")
            continue
        lines = content.splitlines()
        diff_lines = "\n".join(f"+{line}" for line in lines)
        parts.append(
            f"--- /dev/null\n+++ b/{rel_path}\n@@ -0,0 +1,{len(lines)} @@\n{diff_lines}\n"
        )

    return "\n".join(parts)


def get_project_files() -> list[Path]:
    """Return tracked files in the repo."""
    try:
        output = _run(["git", "ls-files"])
    except GitError:
        return []
    root = get_repo_root()
    return [root / f.strip() for f in output.splitlines() if f.strip()]


def count_project_size() -> tuple[int, int]:
    """Return (file_count, total_lines) for tracked files."""
    files = get_project_files()
    total_lines = 0
    for path in files:
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="replace")
            if "\x00" not in content[:1024]:
                total_lines += content.count("\n")
        except OSError:
            pass
    return len(files), total_lines


def ensure_gitignore_entries() -> None:
    """Add .roast/ and *.roast_context to .gitignore if not already present."""
    root = get_repo_root()
    gitignore = root / ".gitignore"
    entries = [".roast/", "*.roast_context"]

    existing = ""
    if gitignore.exists():
        try:
            existing = gitignore.read_text()
        except OSError:
            return

    missing = [e for e in entries if e not in existing.splitlines()]
    if not missing:
        return

    separator = "\n" if existing and not existing.endswith("\n") else ""
    addition = separator + "\n".join(missing) + "\n"
    try:
        with gitignore.open("a") as f:
            f.write(addition)
    except OSError:
        pass  # Non-fatal — best effort
