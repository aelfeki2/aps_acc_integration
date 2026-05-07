"""Configuration loaded from environment variables (with .env fallback).

Keeping this in one place means tests can construct a Settings object directly
without poking at os.environ, and Databricks deployment is a one-line change
(set env vars from secrets, done).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from aps_acc.exceptions import APSError


@dataclass(frozen=True)
class Settings:
    """All runtime configuration for the APS client."""

    client_id: str
    client_secret: str
    account_id: str
    redirect_uri: str
    token_store_path: Path
    token_store_inline: str | None
    log_level: str
    output_dir: Path

    @classmethod
    def from_env(cls, *, dotenv_path: str | Path | None = None) -> Settings:
        """Load settings from environment, with optional .env file loaded first."""
        if dotenv_path is None:
            # Default: look for a .env in the current working directory.
            load_dotenv(override=False)
        else:
            load_dotenv(dotenv_path=str(dotenv_path), override=False)

        client_id = os.environ.get("APS_CLIENT_ID", "").strip()
        client_secret = os.environ.get("APS_CLIENT_SECRET", "").strip()
        account_id = os.environ.get("APS_ACCOUNT_ID", "").strip()

        missing = [
            name
            for name, value in (
                ("APS_CLIENT_ID", client_id),
                ("APS_CLIENT_SECRET", client_secret),
                ("APS_ACCOUNT_ID", account_id),
            )
            if not value
        ]
        if missing:
            raise APSError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in."
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            account_id=account_id,
            redirect_uri=os.environ.get(
                "APS_REDIRECT_URI", "http://localhost:8080/api/auth/callback"
            ).strip(),
            token_store_path=Path(
                os.environ.get("APS_TOKEN_STORE_PATH", "~/.aps_tokens.json")
            ).expanduser(),
            token_store_inline=os.environ.get("APS_TOKEN_STORE_INLINE"),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            output_dir=Path(os.environ.get("OUTPUT_DIR", "./output")).resolve(),
        )
