"""Command-line interface for ai-assistant-reader (`aread`).

The point of this tool: instead of an AI assistant spending its own context
window reading a whole file, it dispatches `aread` to read the file with a
local model and return only the answers to specific tasks/questions.

Read once, answer many: pass several --task flags and the file is prefilled
into LM Studio's cache a single time, with each task answered independently.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_config
from .lmstudio import (
    ContextOverflowError,
    LMStudioError,
    chat_completion,
    get_loaded_context_length,
    get_loaded_models,
    list_models,
    resolve_model,
)

# Safe-side heuristic: ~250 tokens per KB of text. Translates a context window
# (tokens) into an at-a-glance "how much text fits" figure in KB.
TOKENS_PER_KB = 250

HELP_TEXT = """\
aread - an AI assistant that reads files for other AI assistants.

Dispatch this tool to read a file with a local LM Studio model and return only
the answers you care about, instead of spending your own context on the file.

USAGE
  aread read [<file> ...] [--file NAME PATH ...] [--text NAME CONTENT ...]
             [--text-stdin NAME | --task-stdin] -t "<task>" [-t ...] [options]
  aread status
  aread models
  aread config
  aread help

GOOD PRACTICE: CHECK STATUS FIRST
  Before sending large inputs, run `aread status` once. It reports the loaded
  model, its context limit, and roughly how many KB of text fit in one call --
  so you know how much you can hand Aread before it would be too large. This
  makes a live call to LM Studio, so allow up to ~5 seconds for it to respond.

HOW TO ASK GOOD QUESTIONS  (read this before using `read`)
  The file is read & prefilled into the model's cache ONCE per `aread read`
  call. Every additional -t/--task after the first reuses that cache, so extra
  questions are nearly free. Take advantage of that:

  * Prefer MANY SEPARATE -t questions over one big combined question.
    Each -t is answered independently, so answers stay focused and one question
    can't bleed into another. This is the right default.

      GOOD (two independent questions, each its own -t):
        aread read config.yaml \\
          -t "True or False: is TLS enabled? Answer with just the word." \\
          -t "True or False: is there a hardcoded password? Just the word."

      AVOID (cramming unrelated questions into one item):
        aread read config.yaml \\
          -t "Is TLS enabled and is there a hardcoded password?"

  * Only combine things into ONE -t when the parts genuinely cannot be answered
    without each other -- i.e. the question only makes sense as a whole.

      OK to combine (the comparison needs both halves at once):
        -t "Does the retry limit in connect() match the one in reconnect()?
            Answer yes/no and give both numbers."

  Rule of thumb: if two questions could each stand alone, make them two -t flags.
  If splitting them would make either half meaningless, keep them together.

INPUTS: FILES AND/OR TEXT
  An input can be a FILE (a path) or inline TEXT (--text NAME CONTENT). You can
  mix and repeat both. Every input is given a name, and answers refer to inputs
  by that name -- so name things descriptively.

  Naming:
  * A bare file path is named after its filename automatically.
  * --file NAME PATH overrides that name. Use this when filenames are confusing
    or too similar (e.g. two files both called config.json in different dirs) --
    give each a clear temporary identifier the model can reference.
  * --text NAME CONTENT names an inline chunk you pass directly.

  Inline text is for when you already have a chunk in hand and want to avoid
  spending context on it: paste a large section (or several) directly instead of
  pointing at a file. YOU decide what to send -- aread does no chunking, slicing,
  or file lookup for --text; it reads exactly the bytes you pass.

  PIPING (stdin): for a big multi-line chunk or query that's awkward to quote on
  the command line, pipe it instead. stdin is a single stream, so per call it
  can feed exactly ONE of:
    --text-stdin NAME   all of stdin becomes a named text input
    --task-stdin        all of stdin becomes one (possibly multi-line) task
  You can't use both in one call. Each still combines with regular files,
  --text, and -t flags.

      # pipe a chunk as a named text input
      sed -n '40,300p' big.py | aread read --text-stdin "big.py:40-300" \\
        -t "Summarize what this section does."

      # pipe a long generated question as the task
      cat question.txt | aread read app.py --task-stdin

      # one inline text
      aread read --text "auth.py:40-120" "def login(...): ..." \\
        -t "Does this function validate the password before issuing a token?"

      # several texts (e.g. chunks you pulled from different places)
      aread read \\
        --text "config block" "tls: true ..." \\
        --text "handler" "def handle(): ..." \\
        -t "Do these two refer to the same port number?"

MULTIPLE INPUTS AND THE CACHE
  Pass several inputs (files, texts, or a mix) in one `read` call to reason
  across them, e.g. compare or find what they have in common. All inputs are
  concatenated into the SAME shared prefix, so they're prefilled into the cache
  once and every task reuses that cache -- just like multi-question.

      aread read a.py b.py -t "What do these two files have in common?"

  This only works if all the inputs TOGETHER fit the model's context window. If
  they don't, `aread` fails with a clear message and a non-zero exit rather than
  answering on a truncated input. --lines only applies to a single file (no
  --text inputs).

TIMEOUTS
  Longer files take longer to read. The FIRST question on a big file pays the
  full prefill cost (a multi-thousand-line file can take 30-60+ seconds before
  the first answer); later questions in the same call are fast.

  Do NOT set short timeouts -- a too-short --timeout will kill the very first
  question mid-prefill. The default is 120s (a generous ~2 min) precisely so the
  first read on a large file has room to finish. Leave it alone unless a file is
  unusually huge, in which case RAISE it (e.g. --timeout 240), never lower it.

EXAMPLES
  # One question about a file
  aread read app.py -t "What does the main() function return?"

  # Two independent questions; the file is read/prefilled only ONCE
  aread read config.yaml \\
    -t "True or False: TLS is enabled. Answer with just the word." \\
    -t "True or False: there is a hardcoded password. Answer with just the word."

  # Restrict to a line range, get machine-readable JSON back
  aread read big.log --lines 2000-2200 --json -t "Summarize the errors."

  # Multiple files in one call (shared cache across all of them)
  aread read old.py new.py -t "What changed between these two files?"

  # Inline text with a name (no file needed)
  aread read --text "snippet" "$(some command)" -t "What does this do?"

OPTIONS for `read`
  <file>...            Zero or more file paths to read (named after the filename).
      --file NAME PATH Read PATH but present it to the model under NAME instead
                       of its filename. Repeat for several. Optional override.
      --text NAME CONTENT
                       Inline text input with a name. Repeat for several. Can be
                       mixed with file args. The caller supplies the exact text;
                       aread does no chunking or file lookup for it.
      --text-stdin NAME
                       Read a named text input's content from piped stdin.
                       Use for big/multi-line chunks awkward to quote.
      --task-stdin     Read one task from piped stdin (preserves multi-line).
                       Mutually exclusive with --text-stdin (single stream).
  -t, --task TEXT      A task/question about the input(s). Repeat for multiple.
      --tasks-file F   Read tasks from a file, one per line (combinable with -t).
      --lines A-B      Only feed lines A through B (1-based). Single file, no --text.
      --model NAME     Override the configured model ('auto' = currently loaded).
      --base-url URL   Override the LM Studio base URL.
      --timeout SECS   Override the per-request timeout. Default 120s. Only ever
                       RAISE this for very large files; never set it short.
      --json           Emit results as JSON instead of formatted text.
      --timings        Report how long each task's response took (seconds).

Configuration lives in config.toml at the project root. See `aread config`.
"""


def _read_file_slice(path: Path, lines: tuple[int, int] | None) -> str:
    try:
        # utf-8-sig strips a leading BOM if present; errors='replace' means any
        # text-convertible file (html, csv, logs, odd encodings) reads without
        # crashing. Aread does not parse/convert -- it sends the raw text.
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise SystemExit(f"aread: cannot read {path}: {exc}")
    if lines is None:
        return text
    start, end = lines
    selected = text.splitlines()[start - 1 : end]
    return "\n".join(selected)


def _parse_lines(spec: str | None) -> tuple[int, int] | None:
    if not spec:
        return None
    try:
        if "-" in spec:
            a, b = spec.split("-", 1)
            return (int(a), int(b))
        n = int(spec)
        return (n, n)
    except ValueError:
        raise SystemExit(f"aread: invalid --lines value '{spec}' (use A-B or N)")


def _build_system_prompt(sources: list[tuple[str, str, str]]) -> str:
    """Shared prefix across all tasks -> prefilled into LM Studio's cache once.

    `sources` is a list of (name, content, kind) where kind is "file" or
    "text". Each input is wrapped in a clearly delimited, named block so tasks
    can reason across all of them and reference each one by name (e.g. "what do
    these inputs have in common?").
    """
    plural = "inputs" if len(sources) > 1 else "input"
    intro = (
        "You are a precise reading assistant working on behalf of another AI "
        f"assistant. You are given the full contents of {len(sources)} named {plural} "
        "and a single task. Answer the task using ONLY the provided contents. Be "
        "accurate and concise, and return exactly what the task asks for and nothing "
        "else. If the task is a true/false or yes/no question, answer with just that "
        "word unless told otherwise. If the answer is not present, say so plainly. "
        "When referring to a specific input, use its name as shown in its header."
    )
    blocks = [
        f"=== {kind.upper()}: {name} ===\n{content}\n=== END {kind.upper()}: {name} ==="
        for name, content, kind in sources
    ]
    return intro + "\n\n" + "\n\n".join(blocks)


def _gather_tasks(args: argparse.Namespace) -> list[str]:
    tasks: list[str] = list(args.task or [])
    if args.tasks_file:
        tf = Path(args.tasks_file)
        if not tf.is_file():
            raise SystemExit(f"aread: --tasks-file not found: {tf}")
        for line in tf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                tasks.append(line)
    return tasks


def _cmd_read(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.model:
        cfg.model = args.model
    if args.base_url:
        cfg.base_url = args.base_url
    if args.timeout:
        cfg.timeout = float(args.timeout)

    # Files come in two forms: bare paths (name defaults to the filename) and
    # --file NAME PATH (explicit name override, for when filenames are confusing
    # or too similar). Both are validated the same way.
    file_entries: list[tuple[str | None, Path]] = []
    for p in (args.file or []):
        file_entries.append((None, Path(p)))
    for name, p in (args.named_file or []):
        if not name.strip():
            raise SystemExit("aread: --file requires a non-empty NAME.")
        file_entries.append((name, Path(p)))
    for _, path in file_entries:
        if not path.is_file():
            raise SystemExit(f"aread: file not found: {path}")

    texts = [list(pair) for pair in (args.text or [])]  # [name, content] pairs

    # stdin is a single stream, so it can feed exactly one thing per call:
    # either a named text (--text-stdin NAME) or a task (--task-stdin).
    if args.text_stdin is not None and args.task_stdin:
        raise SystemExit(
            "aread: use only one of --text-stdin / --task-stdin per call "
            "(stdin is a single stream)."
        )
    stdin_data: str | None = None
    if args.text_stdin is not None or args.task_stdin:
        if sys.stdin is None or sys.stdin.isatty():
            raise SystemExit(
                "aread: --text-stdin/--task-stdin require input piped on stdin "
                "(e.g. `some-command | aread read ...`)."
            )
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            raise SystemExit("aread: stdin was empty.")
    if args.text_stdin is not None:
        if not args.text_stdin.strip():
            raise SystemExit("aread: --text-stdin requires a non-empty NAME.")
        texts.append([args.text_stdin, stdin_data])

    if not file_entries and not texts:
        raise SystemExit(
            "aread: no input given. Pass files, --file NAME PATH, "
            "--text NAME CONTENT, and/or --text-stdin NAME."
        )

    line_range = _parse_lines(args.lines)
    if line_range and (len(file_entries) != 1 or texts):
        raise SystemExit(
            "aread: --lines can only be used with a single file and no text inputs."
        )

    tasks = _gather_tasks(args)
    if args.task_stdin:
        tasks.append(stdin_data.strip())
    if not tasks:
        raise SystemExit(
            "aread: no tasks given. Use -t/--task, --tasks-file, or --task-stdin."
        )

    # Unify files and inline texts into named (name, content, kind) sources.
    # A file's name is the override if given, else its filename.
    sources: list[tuple[str, str, str]] = []
    for name, path in file_entries:
        display = name if name else path.name
        sources.append((display, _read_file_slice(path, line_range), "file"))
    for name, content in texts:
        if not name.strip():
            raise SystemExit("aread: --text requires a non-empty NAME.")
        sources.append((name, content, "text"))

    system = _build_system_prompt(sources)
    total_content = sum(len(content) for _, content, _ in sources)

    try:
        model = resolve_model(cfg.model, cfg.use_loaded_model, cfg.base_url, cfg.timeout)
    except LMStudioError as exc:
        raise SystemExit(f"aread: {exc}")

    # Heads-up if the input likely won't fit the model's context window. Prefer
    # the model's ACTUAL loaded context (LM Studio reports this, and the user
    # may have loaded it smaller than max to fit VRAM); fall back to the
    # configured guess only if the native API can't tell us. ~4 chars/token is
    # crude but serviceable. Printed to stderr so it never pollutes --json.
    loaded_ctx = get_loaded_context_length(cfg.base_url, cfg.timeout, model)
    ctx_budget = loaded_ctx if loaded_ctx else cfg.context_tokens
    ctx_source = (
        "the model's loaded context"
        if loaded_ctx
        else "the configured context_tokens"
    )
    label = sources[0][0] if len(sources) == 1 else f"{len(sources)} inputs"
    est_tokens = total_content // 4
    if est_tokens > ctx_budget:
        print(
            f"aread: warning: {label} is ~{est_tokens:,} tokens, which exceeds "
            f"{ctx_source} (~{ctx_budget:,} tokens). The model may silently truncate "
            f"the input and answers could be incomplete. Consider fewer/smaller inputs "
            f"or --lines A-B (single file), or load the model with a larger context.",
            file=sys.stderr,
        )

    results = []
    for idx, task in enumerate(tasks):
        started = time.perf_counter()
        try:
            completion = chat_completion(
                base_url=cfg.base_url,
                model=model,
                system=system,
                user=task,
                temperature=cfg.temperature,
                timeout=cfg.timeout,
            )
            answer = completion["text"]
            prompt_tokens = completion.get("prompt_tokens")
        except ContextOverflowError:
            # The model rejected the input outright as too big for its context.
            # No task can succeed, so fail loudly (non-zero exit) right away.
            budget = f"{loaded_ctx:,}-token " if loaded_ctx else ""
            raise SystemExit(
                f"aread: input too large -- {label} does not fit the model's "
                f"{budget}context window, so it was rejected without answering. "
                f"Split the input (fewer/smaller inputs, or --lines A-B for one file) "
                f"or load the model with a larger context in LM Studio."
            )
        except LMStudioError as exc:
            answer = f"[error] {exc}"
            prompt_tokens = None
        elapsed = time.perf_counter() - started

        # AUTHORITATIVE truncation check for models that SILENTLY truncate (and
        # still answer) instead of erroring: use the real input size LM Studio
        # prefilled. If the input filled the context window (within a 20-token
        # margin), the file(s) were truncated and any answer is unreliable --
        # fail loudly so the calling AI knows to split the input. Checked after
        # the first task (which paid the real prefill / TTFT).
        if idx == 0 and prompt_tokens and loaded_ctx and prompt_tokens >= loaded_ctx - 20:
            raise SystemExit(
                f"aread: input too large. LM Studio prefilled {prompt_tokens:,} tokens, "
                f"which fills the model's loaded context ({loaded_ctx:,} tokens) -- the "
                f"{label} was truncated to fit and answers would be unreliable. "
                f"Split the input (fewer/smaller inputs, or --lines A-B for one file) "
                f"or load the model with a larger context in LM Studio."
            )

        results.append(
            {
                "task": task,
                "answer": answer,
                "seconds": round(elapsed, 2),
                "prompt_tokens": prompt_tokens,
            }
        )

    if args.json:
        out = {
            "sources": [{"name": name, "kind": kind} for name, _, kind in sources],
            "model": model,
            "results": results,
        }
        if not args.timings:
            for item in out["results"]:
                item.pop("seconds", None)
        print(json.dumps(out, indent=2))
        return 0

    print(f"# Read {label} with {model} ({len(tasks)} task(s))\n")
    for i, item in enumerate(results, 1):
        suffix = f"  [{item['seconds']}s]" if args.timings else ""
        print(f"## Task {i}: {item['task']}{suffix}")
        # Wrap each answer in a 5-backtick fence (on their own lines) so the
        # answer can never be confused with the file's own content/markdown.
        print("`````")
        print(item["answer"])
        print("`````")
        print()
    if args.timings:
        total = round(sum(r["seconds"] for r in results), 2)
        print(f"-- timings: total {total}s across {len(results)} task(s) --")
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.base_url:
        cfg.base_url = args.base_url
    try:
        models = list_models(cfg.base_url, cfg.timeout)
    except LMStudioError as exc:
        raise SystemExit(f"aread: {exc}")
    if not models:
        print("No models currently loaded in LM Studio.")
        return 0
    loaded_ctx = get_loaded_context_length(cfg.base_url, cfg.timeout)
    print("Models reported by LM Studio:")
    for m in models:
        print(f"  - {m}")
    if loaded_ctx:
        print(f"\nLoaded model context length: {loaded_ctx:,} tokens")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.base_url:
        cfg.base_url = args.base_url

    loaded = get_loaded_models(cfg.base_url, cfg.timeout)
    if not loaded:
        print(
            "aread status: no model is currently loaded in LM Studio (or the "
            "server is unreachable).\n"
            f"  base_url: {cfg.base_url}\n"
            "Load a model in the LM Studio UI and start its server, then retry."
        )
        return 0

    print("aread status")
    print(f"  base_url: {cfg.base_url}")
    for m in loaded:
        ctx = m.get("loaded_context_length")
        max_ctx = m.get("max_context_length")
        print()
        print(f"  Loaded model      : {m.get('id')}")
        if ctx:
            kb = round(ctx / TOKENS_PER_KB)
            max_note = f" (model max: {max_ctx:,})" if max_ctx else ""
            print(f"  Context limit     : {ctx:,} tokens{max_note}")
            print(f"  Approx. capacity  : ~{kb:,} KB of text at once")
            print()
            print(
                f"  Heuristic: at ~{TOKENS_PER_KB} tokens per KB of text, this context\n"
                f"  window fits about  context / {TOKENS_PER_KB}  KB of input in a single\n"
                f"  `aread read` call:\n"
                f"      {ctx:,} / {TOKENS_PER_KB} = ~{kb:,} KB\n"
                f"  That can be one large file or several smaller files/texts combined.\n"
                f"  Stay under it: if the input doesn't fit, aread fails rather than\n"
                f"  answering on a truncated (partial) read."
            )
        else:
            print("  Context limit     : unknown (LM Studio did not report it)")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    cfg = load_config()
    print("Resolved configuration:")
    print(f"  model       : {cfg.model}" + ("  (uses currently-loaded model)" if cfg.use_loaded_model else ""))
    print(f"  base_url    : {cfg.base_url}")
    print(f"  timeout     : {cfg.timeout}s")
    print(f"  temperature : {cfg.temperature}")
    print(f"  context_tokens : {cfg.context_tokens:,}")
    return 0


def _force_utf8_io() -> None:
    """Make stdout/stderr UTF-8 so model answers with chars like ≥, —, → don't
    crash with UnicodeEncodeError on Windows (default console/pipe is cp1252).
    errors='replace' guarantees we never raise while printing an answer.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _force_utf8_io()
    parser = argparse.ArgumentParser(prog="aread", add_help=False)
    parser.add_argument("--version", action="version", version=f"aread {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("help", add_help=False)

    read_p = sub.add_parser("read", add_help=False)
    read_p.add_argument("file", nargs="*")
    read_p.add_argument(
        "--file",
        dest="named_file",
        action="append",
        nargs=2,
        metavar=("NAME", "PATH"),
        default=[],
    )
    read_p.add_argument(
        "--text",
        action="append",
        nargs=2,
        metavar=("NAME", "CONTENT"),
        default=[],
    )
    read_p.add_argument("--text-stdin", metavar="NAME", default=None)
    read_p.add_argument("--task-stdin", action="store_true")
    read_p.add_argument("-t", "--task", action="append", default=[])
    read_p.add_argument("--tasks-file")
    read_p.add_argument("--lines")
    read_p.add_argument("--model")
    read_p.add_argument("--base-url")
    read_p.add_argument("--timeout")
    read_p.add_argument("--json", action="store_true")
    read_p.add_argument("--timings", action="store_true")

    models_p = sub.add_parser("models", add_help=False)
    models_p.add_argument("--base-url")

    status_p = sub.add_parser("status", add_help=False)
    status_p.add_argument("--base-url")

    sub.add_parser("config", add_help=False)

    args, _unknown = parser.parse_known_args()

    if args.command == "read":
        raise SystemExit(_cmd_read(args))
    if args.command == "models":
        raise SystemExit(_cmd_models(args))
    if args.command == "status":
        raise SystemExit(_cmd_status(args))
    if args.command == "config":
        raise SystemExit(_cmd_config(args))

    # help / no command
    print(HELP_TEXT)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
