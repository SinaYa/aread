# aread — full guide

This is the detailed documentation. For the short pitch and the copy-paste
instructions for an AI agent, see the [README](README.md).

## How it saves tokens

When an AI coding assistant (like Claude Code) needs to know something from a
file, it normally reads the whole file into its own context window — burning
tokens on content it mostly doesn't need. `aread` does the reading *for* it: you
dispatch `aread` with a file and one or more tasks, a **local** model (via LM
Studio) reads the file, and only the answers come back.

- The big file is fed to a **local** model, not to the calling assistant.
- Only the concise answers cross back into the assistant's context.
- **Read once, answer many.** Pass several `-t/--task` flags and the file is
  prefilled into LM Studio's KV/prefill cache a single time. Each task is then
  answered as its own completion that reuses that cache — so two separate
  true/false queries stay independent (no cross-contamination) while the file
  is only "read" once.

## Requirements

- [LM Studio](https://lmstudio.ai/) with its local server running
  (LM Studio → Developer → **Start Server**), default `http://127.0.0.1:1234`.
- A loaded model. Default: `unsloth/gemma-4-12b-it-qat-text`.
- Python 3.11+ is needed only to **build** the exe (and to run from source);
  the built `aread.exe` runs with no Python installed.

## Install (Windows)

```bat
install.bat
```

This builds the standalone `aread.exe` (if not already built) and installs it
into `%LOCALAPPDATA%\Microsoft\WindowsApps` (on your PATH), along with a
`config.toml` next to it. Open a new terminal, then:

```bat
aread help
```

`install.bat uninstall` removes it; `install.bat status` shows install state.

### Why a standalone `.exe` (and not a `.cmd` shim)

The command must work from **whichever shell an AI agent reaches for** — and
agents very often use **Git Bash**. That rules out a `.cmd` shim:

- A `.cmd`/`.bat` shim is found by cmd.exe and PowerShell (they honor
  `PATHEXT`), but **Git Bash does not resolve a bare `aread` to `aread.cmd`** —
  it only auto-appends `.exe`. So `command -v aread` returns nothing in Bash and
  an agent concludes (wrongly) that the tool isn't installed. This actually
  happened.
- A real **`aread.exe`** is resolved by a bare `aread` in **all three** shells
  (cmd, PowerShell, Git Bash). One artifact, no shell-specific quirks.

So Aread ships as a single self-contained `aread.exe` built with
[PyInstaller](https://pyinstaller.org/) — it also needs **no Python installed**
to run, which makes it trivial to hand to any machine or attach to a GitHub
Release.

### Building the exe

`install.bat` builds it automatically, or run it directly:

```bat
build-exe.bat
```

This produces `dist\aread.exe` (a single ~8 MB file) plus a `dist\config.toml`.
`dist/` and `build/` are git-ignored — the binary is **not** committed to the
repo. For distribution, upload `dist\aread.exe` to a **GitHub Release** (the
conventional home for binaries) rather than checking it in. A frozen `aread.exe`
reads its `config.toml` from **beside the executable**, so users customize the
model/endpoint by editing the `config.toml` next to `aread.exe`.

### Automated builds (GitHub Actions)

[`.github/workflows/build-exe.yml`](.github/workflows/build-exe.yml) builds the
exe on every push to `main` and on pull requests (uploaded as a workflow
artifact), and **publishes it to a GitHub Release when you push a version tag**:

```bash
git tag v0.1.0
git push origin v0.1.0     # CI builds aread.exe and attaches it to the v0.1.0 release
```

The workflow uses only GitHub's first-party actions plus the preinstalled `gh`
CLI, so the whole pipeline is plain, auditable YAML in this repo.

> Running from source (no exe): you can still run `py -3 -m ai_assistant_reader.cli ...`
> from the repo with `src` on `PYTHONPATH`. The exe is for a clean, cross-shell,
> Python-free command.

## Usage

```bash
# One question about a file
aread read app.py -t "What does main() return?"

# Two independent true/false queries — file read/prefilled only ONCE
aread read config.yaml \
  -t "True or False: TLS is enabled. Answer with just the word." \
  -t "True or False: there is a hardcoded password. Answer with just the word."

# Restrict to a line range, get JSON back
aread read big.log --lines 2000-2200 --json -t "Summarize the errors."

# Many tasks from a file (one per line), combinable with -t
aread read schema.sql --tasks-file questions.txt

# Multiple files in one call — reason across them, shared cache
aread read old.py new.py -t "What changed between these two files?"

# Inline text (named) instead of / alongside files
aread read --text "auth.py:40-120" "def login(...): ..." \
  -t "Does this validate the password before issuing a token?"

# Override confusing/similar filenames with temporary identifiers
aread read --file "PROD config" prod/config.json --file "STAGING config" stg/config.json \
  -t "Do PROD config and STAGING config use the same port? yes/no."

# Inspect / utility
aread status     # loaded model, context limit, and how much text fits at once
aread models     # list models LM Studio currently reports
aread config     # show resolved configuration
```

### Checking capacity: `aread status`

Run `aread status` to see which model is loaded, its **context limit** (the
actual loaded value, e.g. 51,200), and a plain-English estimate of how much text
you can hand Aread in one call:

```
  Loaded model      : unsloth/gemma-4-12b-it-qat-text
  Context limit     : 51,200 tokens (model max: 262,144)
  Approx. capacity  : ~205 KB of text at once
```

The KB figure uses a deliberately safe heuristic of **~250 tokens per KB**, so
`capacity ≈ context_limit / 250` KB — one large file or several smaller
files/texts combined. Staying under it avoids truncation (and Aread fails rather
than answering on a partial read if you exceed it).

`aread status` makes a live call to LM Studio, so allow up to ~5 seconds for it
to respond. As good practice (and as `aread help` notes), run it once before
sending large inputs so you know how much you can hand Aread.

### Inputs: files and/or inline text

An input is either a **file** (a path) or **inline text** (`--text NAME
CONTENT`). You can mix and repeat both. Every input carries a **name**, and
Aread's answers refer to inputs by that name, so name things descriptively:

- A bare file path is named after its filename automatically.
- `--file NAME PATH` reads `PATH` but presents it under `NAME` instead — use it
  when filenames are confusing or too similar (e.g. two `config.json` in
  different dirs) so the model can reference each by a clear temporary id. The
  override is optional.
- `--text NAME CONTENT` names an inline chunk (e.g. `"auth.py:40-120"`).
- `--text-stdin NAME` / `--task-stdin` read from **piped stdin** — see below.

#### Piping big/multi-line input (stdin)

Quoting a large multi-line chunk or query as a command-line argument is awkward.
Pipe it instead. stdin is a single stream, so one `read` call can feed exactly
**one** of these (they're mutually exclusive):

```bash
# a piped chunk becomes a named text input
sed -n '40,300p' big.py | aread read --text-stdin "big.py:40-300" \
  -t "Summarize what this section does."

# a long generated/multi-line question becomes the task
cat question.txt | aread read app.py --task-stdin
```

Both still combine with regular file args, `--text`, and `-t` flags.

Inline text exists so the calling AI can hand Aread a chunk it already has —
a large section of a file, or several — **without spending its own context** on
that chunk and without Aread having to open a file. **The caller decides what to
send; Aread does no chunking, slicing, or file lookup for `--text`** — it reads
exactly the bytes passed.

### Multiple inputs

Pass several inputs (files, texts, or a mix) to one `read` call to ask questions
that span them (compare, diff, "what do these have in common?"). All inputs go
into the **same shared prefix**, so they're prefilled into the cache once and
every task reuses it — the read-once/answer-many benefit, across inputs. This
works only if all the inputs *together* fit the model's context (see below).
`--lines` applies to a single file with no `--text` inputs.

## Configuration

Edit `config.toml` (at the repo root when running from source, or next to
`aread.exe` when installed):

```toml
model          = "unsloth/gemma-4-12b-it-qat-text"  # or "auto" for whatever is loaded
base_url       = "http://127.0.0.1:1234/v1"
timeout        = 120
temperature    = 0.1
context_tokens = 32768   # approx model context; used only for large-file warnings
```

- Set `model = "auto"` to just use **whichever model you've mounted in the
  LM Studio UI** (the first model the API reports) — no config edits needed when
  you switch models.
- Everything is overridable per-run via flags (`--model`, `--base-url`,
  `--timeout`) or env vars (`AREAD_MODEL`, `AREAD_BASE_URL`, `AREAD_TIMEOUT`,
  `AREAD_TEMPERATURE`, `AREAD_CONTEXT_TOKENS`, `AREAD_CONFIG`).

## Large files

`aread` prints a warning to **stderr** (so `--json` stdout stays clean) when a
file's estimated token count exceeds the model's context window — a heads-up
that the model may silently truncate it and return incomplete answers.

It detects the window automatically: it asks LM Studio's native API for the
model's **actual loaded context length**, which respects a context size you
lowered in the UI to fit VRAM (e.g. a 262k-max model loaded at 51,200). The
`context_tokens` config value is only a fallback for when that auto-detection
isn't available. Use `--lines A-B` to focus on a region of a file that's too
big to fit, or reload the model with a larger context in LM Studio.

`aread models` prints the currently loaded model's context length.

### When the input really is too big

The `chars/4` estimate above is only a pre-flight heads-up. The authoritative
check happens after the first task runs: `aread` reads the **exact** input token
count LM Studio reports (`usage.prompt_tokens`) and, if the input was truncated
to fit the window — or if the model rejected it outright as too large — it
**fails with a non-zero exit and a clear message** telling the calling AI to
split the input. So a too-big read never returns quietly-incomplete answers; it
errors. (Token counting only exists via LM Studio's SDK tokenizer, not the REST
API, so the exact count is taken from the first response's `usage` rather than a
separate pre-count call.)

## How it's wired

- `src/ai_assistant_reader/cli.py` — argument parsing and the `read`/`status`/
  `models`/`config` commands.
- `src/ai_assistant_reader/lmstudio.py` — stdlib-only OpenAI-compatible client
  for LM Studio (`/v1/models`, `/v1/chat/completions`, native `/api/v0/models`).
- `src/ai_assistant_reader/config.py` — config resolution (flags → env →
  `config.toml` → defaults; finds `config.toml` beside the exe when frozen).
- `aread_entry.py` — the script PyInstaller freezes into `aread.exe`.
- `build-exe.bat` — builds `dist\aread.exe`; `install.bat` installs it.

The app itself has **no third-party runtime dependencies** — pure standard
library. PyInstaller is a build-time-only tool for producing the exe.
