# aread — an AI assistant for AI assistants

`aread` reads files for your AI coding assistant, so it spends its context on
answers instead of on the file.

## Get started

Paste this to your AI assistant (Codex, Claude, etc.) to get started:

```
use this tool (https://github.com/SinaYa/aread) to read files with less mistakes. read its readme
```

## What it is

A small CLI. You (or your AI) point `aread` at a file — or pasted text — and ask
questions; a **local** model (via [LM Studio](https://lmstudio.ai/)) reads it and
returns only the answers, saving the assistant's tokens. The file is read once
and many questions reuse that single read.

## Install (Windows)

Two ways:

1. **Download the prebuilt exe** (no Python needed) — grab `aread.exe` from the
   [latest release](https://github.com/SinaYa/aread/releases/latest). Put it
   somewhere on your `PATH` (or run it in place), and drop a `config.toml` next
   to it to customize the model/endpoint.
2. **From source** — clone this repo and run `install.bat`. It builds and
   installs a standalone `aread.exe` that works in cmd, PowerShell, and Git Bash.

Either way, open a new terminal and run:

```bat
aread help
```

Full documentation — all flags, stdin piping, capacity/limits, config, and how
the exe is built — is in **[GUIDE.md](GUIDE.md)**.

## Roadmap

Aread currently targets [LM Studio](https://lmstudio.ai/)'s local server. Planned:

- **vLLM support** — talk to a [vLLM](https://github.com/vllm-project/vllm)
  backend so the same read-once/answer-many workflow runs on higher-throughput
  local/served models.
- **OpenAI-compatible completions endpoints** — generalize the backend so Aread
  can point at any OpenAI-compatible `/v1` server (not just LM Studio), making
  the model/endpoint fully pluggable via `config.toml`.

## License

[MIT](LICENSE) © Sina Yaqubi

## The name

> My primary construction was just **`a` + `read`** — a short, typeable command
> for "read" (and a nod to **AI-read**: an AI that reads for AIs). The happy
> accident: **`aread` is also a genuine archaic English word** (from Old English
> *arǣdan*, used by Spenser as *areed/aread*) meaning **"to interpret, discern,
> declare, or divine the meaning of something."** So "aread this file" literally
> meant "make out / interpret this" centuries ago — which is exactly what the
> tool does. I'd love to claim I planned that, but it was `a`+`read` first and
> the archaic meaning is a perfect bonus.
>
> — AI Co-Author

---

## For the AI using this tool

If you are a **human**, paste the block below into your AI agent's system
prompt, project rules, or CLAUDE.md. If you are an **AI**, follow these
instructions to get the most out of this tool. (If `aread` isn't installed yet,
see **Install** above — download the release exe or build from this repo.)

```
When you need information from a file but do not need to edit it, do NOT
read the file directly. Instead dispatch the `aread` CLI tool: a local
model reads the file and returns only the answers you ask for, so the
file never enters your own context window and you save tokens.

Usage:
  aread read [<file> ...] [--file NAME PATH ...] [--text NAME CONTENT ...]
             -t "<question>" [-t ...]

Conventions:
- Ask several INDEPENDENT questions as separate -t flags in a single
  call. The input is read and prefilled only ONCE per call, so every
  extra -t question after the first is nearly free and answered
  independently.
- An input is a FILE (a path) or inline TEXT (--text NAME CONTENT). Use
  --text to hand over a chunk you already have WITHOUT reading it into
  your own context -- e.g. a large section of a file, or several. Give
  each text a descriptive NAME; answers reference inputs by name. YOU do
  any chunking; aread reads exactly what you pass.
- Every input has a name. A bare file path is named by its filename; use
  --file NAME PATH to override that name when filenames are confusing or
  too similar, so answers can reference each by a clear identifier.
- For a big or multi-line chunk/query that's awkward to quote on the
  command line, PIPE it via stdin. Per call, stdin can feed exactly one:
  `--text-stdin NAME` (stdin becomes a named text input) OR `--task-stdin`
  (stdin becomes one task). They are mutually exclusive; each still
  combines with normal files, --text, and -t flags.
- You can pass MULTIPLE inputs (files, texts, or a mix) in one call to
  ask questions that span them (compare, diff, "what do these have in
  common?"). They share one cache, as long as they all fit the model's
  context together. If the input is too large, aread fails with a
  non-zero exit and tells you to split it -- it never returns
  quietly-truncated answers.
- Only put multiple things in one -t when they genuinely cannot be
  answered without each other (e.g. a comparison that needs both halves
  at once). Otherwise, split them into separate -t flags.
- Do NOT lower --timeout. The first question on a large file can take
  30-60+ seconds because the whole file is prefilled before the first
  answer. The default (120s) is intentionally generous. Only RAISE it
  for unusually huge files; never set it short.
- Run `aread help` once to learn the full conventions.
- Good practice: run `aread status` once before sending large inputs. It
  shows the loaded model, its context limit, and roughly how many KB of
  text you can load in one call (~250 tokens/KB, so capacity ~=
  context_limit / 250 KB). It calls LM Studio live, so allow up to ~5s.

Example:
  aread read "C:\reports\report.md" \
    -t "What is this document about?" \
    -t "True or False: does it mention a budget? Answer with just the word." \
    -t "List the top-level section headings."
```

Alternatively, for a one-off on a specific file (without changing the agent's
standing rules), paste this:

```
Use the `aread` CLI to answer questions about "<path-to-file>" instead
of reading the file yourself. Run `aread help` first to learn how to
ask questions, then ask each separate question as its own -t flag in a
single `aread read` call. Don't lower the timeout -- the first question
on a big file can take 30-60 seconds.
```
