# roast — brutal AI code reviews in your terminal

```
██████╗  ██████╗  █████╗ ███████╗████████╗
██╔══██╗██╔═══██╗██╔══██╗██╔════╝╚══██╔══╝
██████╔╝██║   ██║███████║███████╗   ██║
██╔══██╗██║   ██║██╔══██║╚════██║   ██║
██║  ██║╚██████╔╝██║  ██║███████║   ██║
╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝
```

**The code reviewer that tells you the truth.**

No sugarcoating. No "consider refactoring." Just brutal, specific, line-level feedback — bugs, security holes, bad patterns, what's missing, and what to do about it.

---

## What it does

- **`roast`** — reviews your current diff (staged + unstaged + new files) with AI
- **`roast project`** — full architecture audit of your entire codebase
- **`roast config`** — interactive setup

Powered by [OpenRouter](https://openrouter.ai) — use Claude, GPT-4, Gemini, Mistral, or any model you want.

Remembers context per-repo so each review builds on the last.

---

## Install

```bash
brew install pipx
git clone https://github.com/TomasKynicky/Roast
cd Roast
pipx install -e .
```

Then verify:

```bash
roast --version
```

**Requirements:** Python 3.10+, git installed and on PATH.

---

## Setup

```bash
roast config
```

You'll be prompted for:
1. **OpenRouter API key** — get one at [openrouter.ai/keys](https://openrouter.ai/keys) (free tier available)
2. **Model** — picks from a live list of available models with pricing
3. **Language** — English, Czech, or any language

Config is stored in `~/.roast/config.json` (chmod 600, never committed).

---

## Usage

### Review your current changes

```bash
# Make some changes, then:
roast
```

**Example output:**

```
╭─────────────────────────── Code Review ───────────────────────────╮
│                                                                     │
│ ## 🔴 Critical Issues                                               │
│                                                                     │
│ **`auth.py:47` — SQL injection via f-string interpolation**         │
│ `query = f"SELECT * FROM users WHERE id = {user_id}"` is directly   │
│ interpolating user input. Use parameterized queries:                │
│ `cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`    │
│                                                                     │
│ **`config.py:12` — Hardcoded secret**                               │
│ `SECRET_KEY = "my-secret-key-123"` will end up in git history.      │
│ Move to env var: `SECRET_KEY = os.environ["SECRET_KEY"]`            │
│                                                                     │
│ ## 🟠 Important Issues                                              │
│                                                                     │
│ **`api.py:89` — No timeout on external HTTP call**                  │
│ `requests.get(url)` will hang indefinitely. Add `timeout=30`.       │
│                                                                     │
│ ## 🟡 Minor Issues                                                  │
│                                                                     │
│ **`utils.py:23` — `data` is a terrible variable name**              │
│ Rename to `user_records` or whatever it actually holds.             │
│                                                                     │
│ ## 📋 Priority Action List                                          │
│ 1. Fix SQL injection in auth.py immediately                         │
│ 2. Move SECRET_KEY to environment variable                          │
│ 3. Add timeout to all HTTP calls                                    │
╰─────────────────────────────────────────────────────────────────────╯
```

### Full project audit

```bash
roast project
```

Auto-detects project size:
- **Small** (< 50 files / < 5,000 lines): reads full codebase
- **Large** (≥ 50 files or ≥ 5,000 lines): reads structure + key files

Covers architecture, security, code quality, what will break in prod, and a prioritized fix list.

### Global flags

```bash
roast --model anthropic/claude-opus-4        # Override model
roast --lang cs                              # Review in Czech
roast --no-context                           # Skip history (fresh review)
roast --out review.md                        # Also save to markdown file

roast project --model google/gemini-pro --out audit.md
```

---

## Models

`roast` uses OpenRouter, which gives you access to every major model:

| Provider  | Example models                                          |
|-----------|---------------------------------------------------------|
| Anthropic | `anthropic/claude-3.5-sonnet`, `anthropic/claude-opus-4`|
| OpenAI    | `openai/gpt-4o`, `openai/o3-mini`                       |
| Google    | `google/gemini-pro-1.5`, `google/gemini-flash-1.5`      |
| Mistral   | `mistralai/mistral-large`, `mistralai/codestral-mamba`  |
| Meta      | `meta-llama/llama-3.1-405b-instruct`                    |

Default: `anthropic/claude-3.5-sonnet`

Run `roast config` to browse models with live pricing.

---

## Context & memory

Each repo gets a unique ID (based on git remote URL or path). Reviews are saved to `~/.roast/contexts/<repo-id>.json`.

The last 10 reviews are sent as conversation history with each new `roast` run — so the AI knows what it already told you and can track whether issues were fixed.

Project audits are saved separately and used as background context for diff reviews.

Use `--no-context` to get a clean review without history.

---

## .gitignore protection

On first run in any repo, `roast` automatically adds `.roast/` and `*.roast_context` to your `.gitignore`. Your API key lives in `~/.roast/config.json` (not in any repo), and your review history stays in `~/.roast/contexts/` (also outside any repo).

Your secrets will not end up on GitHub. This is handled automatically.

---

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Make changes and run `roast` on your own diff (dogfooding encouraged)
4. Open a PR

---

## License

MIT
