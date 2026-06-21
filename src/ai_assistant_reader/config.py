"""Configuration loading for ai-assistant-reader.

Resolution order (highest priority first):
  1. Explicit CLI flags (handled in cli.py)
  2. Environment variables: AREAD_MODEL, AREAD_BASE_URL, AREAD_TIMEOUT,
     AREAD_TEMPERATURE
  3. config.toml sitting next to the project (or pointed at by AREAD_CONFIG)
  4. Hard-coded defaults below
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "unsloth/gemma-4-12b-it-qat-text"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_TIMEOUT = 120.0
DEFAULT_TEMPERATURE = 0.1
# Roughly the model's usable context window, in tokens. Used only to warn when
# a file likely won't fit (and may be silently truncated by LM Studio).
DEFAULT_CONTEXT_TOKENS = 32768

# Where to look for config.toml by default:
#  - Frozen (PyInstaller .exe): next to the executable, so users drop a
#    config.toml beside aread.exe to customize it.
#  - From source: the repo root (<repo>/src/ai_assistant_reader/config.py ->
#    up two levels to <repo>/config.toml).
if getattr(sys, "frozen", False):
    _DEFAULT_CONFIG_PATH = Path(sys.executable).resolve().parent / "config.toml"
else:
    _DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    temperature: float = DEFAULT_TEMPERATURE
    context_tokens: int = DEFAULT_CONTEXT_TOKENS

    @property
    def use_loaded_model(self) -> bool:
        """True when the user wants whatever model is currently loaded."""
        return self.model.strip().lower() in {"", "auto", "loaded", "current"}


def _config_path() -> Path:
    override = os.environ.get("AREAD_CONFIG")
    return Path(override) if override else _DEFAULT_CONFIG_PATH


def load_config() -> Config:
    cfg = Config()

    path = _config_path()
    if path.is_file():
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        if "model" in data:
            cfg.model = str(data["model"])
        if "base_url" in data:
            cfg.base_url = str(data["base_url"])
        if "timeout" in data:
            cfg.timeout = float(data["timeout"])
        if "temperature" in data:
            cfg.temperature = float(data["temperature"])
        if "context_tokens" in data:
            cfg.context_tokens = int(data["context_tokens"])

    # Environment overrides.
    if os.environ.get("AREAD_MODEL"):
        cfg.model = os.environ["AREAD_MODEL"]
    if os.environ.get("AREAD_BASE_URL"):
        cfg.base_url = os.environ["AREAD_BASE_URL"]
    if os.environ.get("AREAD_TIMEOUT"):
        cfg.timeout = float(os.environ["AREAD_TIMEOUT"])
    if os.environ.get("AREAD_TEMPERATURE"):
        cfg.temperature = float(os.environ["AREAD_TEMPERATURE"])
    if os.environ.get("AREAD_CONTEXT_TOKENS"):
        cfg.context_tokens = int(os.environ["AREAD_CONTEXT_TOKENS"])

    return cfg
