"""All system/user prompts sent to the AI."""
from __future__ import annotations

LANG_INSTRUCTION = {
    "en": "Respond in English.",
    "cs": "Respond in Czech (česky).",
}


def lang_suffix(lang: str) -> str:
    return LANG_INSTRUCTION.get(lang, f"Respond in {lang}.")


def diff_system_prompt(lang: str, project_context: str | None) -> str:
    project_block = ""
    if project_context:
        project_block = f"""
You have the following project-level context from a prior audit:
<project_context>
{project_context}
</project_context>
Use this context to make your diff review more relevant.
"""
    return f"""You are a brutal, no-bullshit senior code reviewer. You do not sugarcoat.
Your job is to find every problem in this diff — bugs, security issues, bad patterns, \
missing error handling, unclear naming, anything that would fail in production.

Be specific. Reference exact variable names, function names, line content.
Do not say "consider refactoring" — say exactly what to refactor and how.
Do not praise unless something is genuinely exceptional.

Structure your review:
1. 🔴 Critical issues (bugs, security, will break in prod)
2. 🟠 Important issues (bad patterns, missing handling, tech debt)
3. 🟡 Minor issues (naming, style, small improvements)
4. ✅ What's actually good (only if genuinely good)
5. 📋 Summary & priority action list
{project_block}
{lang_suffix(lang)}"""


def diff_user_prompt(diff: str) -> str:
    return f"Review this diff:\n\n```diff\n{diff}\n```"


def project_system_prompt(lang: str) -> str:
    return f"""You are a brutal senior architect doing a full project audit.
You have zero tolerance for production-unready code.

Review this project across:
1. 🏗️ Architecture — is the structure sensible, scalable, maintainable?
2. 🔐 Security — any vulnerabilities, exposed secrets, unsafe patterns?
3. 🧹 Code quality — clean code principles, duplication, complexity
4. 🚨 What will break in production — be specific
5. 📦 What's missing — tests, docs, error handling, monitoring
6. 🔧 Prioritized improvement list — top 10 things to fix/add, ordered by impact

Be concrete. Name files, functions, patterns. No vague advice.
{lang_suffix(lang)}"""


def project_user_prompt_small(files: dict[str, str]) -> str:
    """Prompt for small projects — include full file contents."""
    parts = ["Full project codebase for review:\n"]
    for path, content in files.items():
        parts.append(f"### {path}\n```\n{content}\n```\n")
    return "\n".join(parts)


def project_user_prompt_large(structure: str, key_files: dict[str, str]) -> str:
    """Prompt for large projects — folder structure + key files."""
    parts = [
        "This is a large project. Here is the folder structure and key files:\n",
        f"### Directory structure\n```\n{structure}\n```\n",
        "### Key files\n",
    ]
    for path, content in key_files.items():
        parts.append(f"#### {path}\n```\n{content}\n```\n")
    return "\n".join(parts)
