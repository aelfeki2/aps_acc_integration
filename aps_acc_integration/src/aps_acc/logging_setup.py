"""Logging configuration loader.

Uses the YAML config in config/logging.yaml when available, falls back to a
sensible default. Centralizing this means token-masking and request-logging
behave consistently across CLI and library use.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml


def setup_logging(*, level: str = "INFO", config_path: Path | None = None) -> None:
    """Configure the `aps_acc` logger tree."""
    if config_path is None:
        # Look for the bundled config relative to the repo root.
        config_path = Path(__file__).resolve().parents[2] / "config" / "logging.yaml"

    if config_path.is_file():
        with config_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # Override level from caller if provided.
        cfg.setdefault("loggers", {}).setdefault("aps_acc", {})["level"] = level
        logging.config.dictConfig(cfg)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def mask_token(token: str | None) -> str:
    """Mask a bearer token for safe logging.

    Shows the first 8 and last 4 characters; keeps enough detail to correlate
    log lines without ever exposing the full token.
    """
    if not token:
        return "<none>"
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"
