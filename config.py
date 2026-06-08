"""Carga de configuración desde variables de entorno (.env o el entorno del
servicio systemd)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # En el VPS las vars vienen del EnvironmentFile de systemd; python-dotenv
    # es opcional (solo cómodo en local).
    pass


@dataclass(frozen=True)
class Config:
    discord_token: str
    crafty_panel: str
    crafty_token: str
    crafty_server_id: str
    guild_id: int | None
    refresh_seconds: int
    server_name: str
    server_address: str
    channels_dir: str
    state_file: str

    @classmethod
    def from_env(cls) -> "Config":
        def required(key: str) -> str:
            value = os.environ.get(key)
            if not value:
                raise SystemExit(f"Falta la variable de entorno obligatoria: {key}")
            return value

        guild = os.environ.get("DISCORD_GUILD_ID")
        return cls(
            discord_token=required("DISCORD_TOKEN"),
            crafty_panel=os.environ.get("CRAFTY_PANEL", "https://127.0.0.1:8443"),
            crafty_token=required("CRAFTY_TOKEN"),
            crafty_server_id=required("CRAFTY_SERVER_ID"),
            guild_id=int(guild) if guild else None,
            refresh_seconds=int(os.environ.get("STATUS_REFRESH_SECONDS", "60")),
            server_name=os.environ.get("MC_SERVER_NAME", "Realm Gates"),
            server_address=os.environ.get("MC_SERVER_ADDRESS", "5.78.204.157"),
            channels_dir=os.environ.get("CHANNELS_DIR", "Channels"),
            state_file=os.environ.get("SYNC_STATE_FILE", ".sync-state.json"),
        )
