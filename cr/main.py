"""roast — brutal AI code reviewer. Click entry point and all commands."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.spinner import Spinner
from rich.table import Table

from cr import __version__
from cr.ai import AIError, chat, list_models
from cr.config import (
    DEFAULT_LANG,
    DEFAULT_MODEL,
    get_api_key,
    get_lang,
    get_model,
    load_config,
    save_config,
)
from cr.context import load_history, load_project_context, save_project_context, save_review
from cr.git import (
    GitError,
    assert_git_repo,
    count_project_size,
    ensure_gitignore_entries,
    get_diff,
    get_project_files,
    get_repo_hash,
    get_repo_root,
)
from cr.prompts import (
    diff_system_prompt,
    diff_user_prompt,
    project_system_prompt,
    project_user_prompt_large,
    project_user_prompt_small,
)

console = Console()

SMALL_FILE_LIMIT = 50
SMALL_LINE_LIMIT = 5000

# Files always included for large-project review
KEY_FILE_PATTERNS = {
    "readme": ["README.md", "README.rst", "README.txt", "readme.md"],
    "config": [
        "pyproject.toml", "setup.py", "setup.cfg", "package.json",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
        "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "requirements.txt", "requirements-dev.txt",
    ],
    "entry": [
        "main.py", "app.py", "server.py", "index.py", "__main__.py",
        "main.go", "main.ts", "index.ts", "index.js", "app.js",
        "src/main.py", "src/app.py", "src/main.go",
    ],
}


# ---------------------------------------------------------------------------
# Shared flags via click decorators
# ---------------------------------------------------------------------------

_common_options = [
    click.option("--model", "model_override", default=None, help="Override model for this run"),
    click.option("--lang", "lang_override", default=None, help="Override language (en, cs, ...)"),
    click.option("--no-context", "no_context", is_flag=True, help="Skip loading/saving context"),
    click.option("--out", "out_file", default=None, help="Save review to a markdown file"),
]


def common_options(f: Any) -> Any:
    for option in reversed(_common_options):
        f = option(f)
    return f


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_model(model_override: str | None) -> str:
    return model_override or get_model()


def _resolve_lang(lang_override: str | None) -> str:
    return lang_override or get_lang()


def _require_api_key() -> str:
    key = get_api_key()
    if not key:
        console.print(
            "[bold red]No API key configured.[/bold red]\n"
            "Run [bold]roast config[/bold] to set your OpenRouter API key."
        )
        sys.exit(1)
    return key


def _save_output(out_file: str, content: str) -> None:
    path = Path(out_file)
    try:
        path.write_text(content)
        console.print(f"[dim]Review saved to [bold]{path}[/bold][/dim]")
    except OSError as e:
        console.print(f"[yellow]Warning: could not save to {out_file}: {e}[/yellow]")


def _render_review(review: str) -> None:
    console.print()
    console.print(Panel(Markdown(review), title="[bold cyan]Code Review[/bold cyan]", border_style="cyan"))


def _guard_git() -> None:
    """Check we're in a git repo and set up .gitignore protection."""
    try:
        assert_git_repo()
        ensure_gitignore_entries()
    except GitError as e:
        console.print(f"[bold red]Git error:[/bold red] {e}")
        sys.exit(1)


def _get_large_project_data() -> tuple[str, dict[str, str]]:
    """Build directory tree string and collect content of key files."""
    root = get_repo_root()
    all_files = get_project_files()

    # Build tree
    tree_lines: list[str] = []
    for f in sorted(all_files):
        rel = f.relative_to(root)
        tree_lines.append(str(rel))
    structure = "\n".join(tree_lines)

    # Collect key files
    key_files: dict[str, str] = {}
    all_names = {str(f.relative_to(root)): f for f in all_files}

    candidates: list[str] = []
    for names in KEY_FILE_PATTERNS.values():
        candidates.extend(names)

    for candidate in candidates:
        if candidate in all_names:
            path = all_names[candidate]
            if not path.is_file():
                continue
            try:
                content = path.read_text(errors="replace")
                if "\x00" not in content[:1024]:
                    key_files[candidate] = content
            except OSError:
                pass

    # Also include __init__.py and main module files (up to 5 more)
    extra_count = 0
    for rel_str, path in sorted(all_names.items()):
        if extra_count >= 5:
            break
        if rel_str in key_files:
            continue
        name = Path(rel_str).name
        if name in ("__init__.py", "main.py", "app.py") or rel_str.endswith("/__init__.py"):
            try:
                content = path.read_text(errors="replace")
                if "\x00" not in content[:1024]:
                    key_files[rel_str] = content
                    extra_count += 1
            except OSError:
                pass

    return structure, key_files


def _get_small_project_data() -> dict[str, str]:
    """Read full content of all tracked files."""
    root = get_repo_root()
    files = get_project_files()
    result: dict[str, str] = {}
    for path in files:
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="replace")
            if "\x00" not in content[:1024]:  # skip binaries
                result[str(path.relative_to(root))] = content
        except OSError:
            pass
    return result


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="roast")
@click.pass_context
@common_options
def cli(
    ctx: click.Context,
    model_override: str | None,
    lang_override: str | None,
    no_context: bool,
    out_file: str | None,
) -> None:
    """roast — brutal, honest AI code reviewer.\n
    Run without a subcommand to review your current diff.
    """
    if ctx.invoked_subcommand is None:
        # Default: run diff review
        ctx.invoke(
            review,
            model_override=model_override,
            lang_override=lang_override,
            no_context=no_context,
            out_file=out_file,
        )


# ---------------------------------------------------------------------------
# roast  (diff review — default command)
# ---------------------------------------------------------------------------

@cli.command(name="review", hidden=True)
@common_options
def review(
    model_override: str | None,
    lang_override: str | None,
    no_context: bool,
    out_file: str | None,
) -> None:
    """Review current diff (staged + unstaged + new files)."""
    _guard_git()
    api_key = _require_api_key()
    model = _resolve_model(model_override)
    lang = _resolve_lang(lang_override)

    # Get diff
    with console.status("[bold cyan]Collecting changes...[/bold cyan]"):
        try:
            diff = get_diff()
        except GitError as e:
            console.print(f"[bold red]Git error:[/bold red] {e}")
            sys.exit(1)

    if not diff.strip():
        console.print(
            Panel(
                "[yellow]No changes detected.[/yellow]\n\n"
                "Stage some files, make some edits, or add new files — then run [bold]roast[/bold] again.",
                title="Nothing to review",
                border_style="yellow",
            )
        )
        sys.exit(0)

    # Load context
    repo_hash = get_repo_hash()
    history: list[dict[str, str]] = []
    project_ctx: str | None = None

    if not no_context:
        history = load_history(repo_hash)
        project_ctx = load_project_context(repo_hash)

    # Build messages
    system = diff_system_prompt(lang, project_ctx)
    user_msg = diff_user_prompt(diff)
    messages = [*history, {"role": "user", "content": user_msg}]

    # Call API
    console.print(f"[dim]Model: {model} | Lang: {lang}[/dim]")
    with console.status("[bold cyan]Sending to AI...[/bold cyan]", spinner="dots"):
        try:
            review_text = chat(api_key, model, messages, system)
        except AIError as e:
            console.print(f"[bold red]AI error:[/bold red] {e}")
            sys.exit(1)

    _render_review(review_text)

    if out_file:
        _save_output(out_file, review_text)

    if not no_context:
        save_review(repo_hash, user_msg, review_text)


# ---------------------------------------------------------------------------
# roast project
# ---------------------------------------------------------------------------

@cli.command()
@common_options
def project(
    model_override: str | None,
    lang_override: str | None,
    no_context: bool,
    out_file: str | None,
) -> None:
    """Full project architecture and quality audit."""
    _guard_git()
    api_key = _require_api_key()
    model = _resolve_model(model_override)
    lang = _resolve_lang(lang_override)

    with console.status("[bold cyan]Scanning project...[/bold cyan]"):
        try:
            file_count, total_lines = count_project_size()
        except GitError as e:
            console.print(f"[bold red]Git error:[/bold red] {e}")
            sys.exit(1)

    is_small = file_count < SMALL_FILE_LIMIT and total_lines < SMALL_LINE_LIMIT

    console.print(
        f"[dim]Project size: {file_count} files, ~{total_lines:,} lines — "
        f"{'[green]small[/green]' if is_small else '[yellow]large[/yellow]'} mode[/dim]"
    )
    console.print(f"[dim]Model: {model} | Lang: {lang}[/dim]")

    system = project_system_prompt(lang)

    with console.status("[bold cyan]Reading project files...[/bold cyan]"):
        try:
            if is_small:
                files = _get_small_project_data()
                user_msg = project_user_prompt_small(files)
            else:
                structure, key_files = _get_large_project_data()
                user_msg = project_user_prompt_large(structure, key_files)
        except GitError as e:
            console.print(f"[bold red]Git error:[/bold red] {e}")
            sys.exit(1)

    with console.status("[bold cyan]Sending to AI...[/bold cyan]", spinner="dots"):
        try:
            review_text = chat(api_key, model, [{"role": "user", "content": user_msg}], system)
        except AIError as e:
            console.print(f"[bold red]AI error:[/bold red] {e}")
            sys.exit(1)

    _render_review(review_text)

    if out_file:
        _save_output(out_file, review_text)

    if not no_context:
        repo_hash = get_repo_hash()
        save_project_context(repo_hash, review_text)


# ---------------------------------------------------------------------------
# roast config
# ---------------------------------------------------------------------------

@cli.command()
def config() -> None:
    """Interactive configuration: API key, model, language."""
    current = load_config()

    console.print(
        Panel(
            "[bold cyan]roast configuration[/bold cyan]\n"
            f"Config file: [dim]{Path.home() / '.roast' / 'config.json'}[/dim]",
            border_style="cyan",
        )
    )

    # Show current config (never print the actual key)
    if current:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")
        if current.get("api_key"):
            masked = current["api_key"][:8] + "..." + current["api_key"][-4:]
            table.add_row("api_key", f"[dim]{masked}[/dim]")
        table.add_row("model", current.get("model", DEFAULT_MODEL))
        table.add_row("lang", current.get("lang", DEFAULT_LANG))
        console.print(table)
        console.print()

    # API key
    key_prompt = "OpenRouter API key" + (" (press Enter to keep current)" if current.get("api_key") else "")
    new_key = Prompt.ask(key_prompt, default="", password=True)
    if new_key.strip():
        current["api_key"] = new_key.strip()
    elif not current.get("api_key"):
        console.print(
            "[yellow]No API key set. Get one at https://openrouter.ai/keys[/yellow]"
        )

    # Model selection
    if current.get("api_key") or new_key.strip():
        api_key = current.get("api_key", "")
        if Confirm.ask("Fetch available models from OpenRouter?", default=True):
            with console.status("[cyan]Fetching models...[/cyan]"):
                try:
                    models = list_models(api_key)
                except AIError as e:
                    console.print(f"[yellow]Could not fetch models: {e}[/yellow]")
                    models = []

            if models:
                _display_models(models)
                console.print(
                    f"\n[dim]Current model: {current.get('model', DEFAULT_MODEL)}[/dim]"
                )

    new_model = Prompt.ask(
        "Model ID (press Enter to keep current)",
        default=current.get("model", DEFAULT_MODEL),
    )
    if new_model.strip():
        current["model"] = new_model.strip()

    # Language
    console.print("\n[dim]Language options: en (English), cs (Czech), or any language name[/dim]")
    new_lang = Prompt.ask(
        "Review language",
        default=current.get("lang", DEFAULT_LANG),
    )
    if new_lang.strip():
        current["lang"] = new_lang.strip()

    save_config(current)
    console.print("\n[bold green]Configuration saved.[/bold green]")


def _display_models(models: list[dict]) -> None:
    table = Table(
        title="Available Models",
        show_lines=False,
        border_style="dim",
    )
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Context", justify="right", style="dim")
    table.add_column("$/1M in", justify="right", style="green")
    table.add_column("$/1M out", justify="right", style="yellow")

    # Sort by prompt price ascending, then show top 30
    def sort_key(m: dict) -> float:
        try:
            return float(m.get("pricing", {}).get("prompt", 9999) or 9999)
        except (TypeError, ValueError):
            return 9999.0

    for m in sorted(models, key=sort_key)[:30]:
        pricing = m.get("pricing", {})
        try:
            price_in = f"${float(pricing.get('prompt', 0) or 0) * 1_000_000:.2f}"
        except (TypeError, ValueError):
            price_in = "—"
        try:
            price_out = f"${float(pricing.get('completion', 0) or 0) * 1_000_000:.2f}"
        except (TypeError, ValueError):
            price_out = "—"

        ctx = m.get("context_length", 0)
        ctx_str = f"{ctx // 1000}k" if ctx else "—"

        table.add_row(
            m.get("id", ""),
            m.get("name", "")[:40],
            ctx_str,
            price_in,
            price_out,
        )

    console.print(table)


if __name__ == "__main__":
    cli()
