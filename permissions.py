"""Lenguaje de permisos del frontmatter -> overwrites de Discord.

Cada `.md` puede declarar un **preset** (`access:`) que siembra los permisos
base, y un `permissions:` (lista de textos) con overrides finos por rol:

    access: read-only
    permissions:
      - "@everyone: view -send"
      - "Moderator: view send manage threads"

Donde `action` = permitir, `-action` = denegar, y lo ausente se hereda.
"""

from __future__ import annotations

import logging

import discord

log = logging.getLogger("mc-discord-bot")

# Acción (en inglés, del frontmatter) -> campo(s) de discord.PermissionOverwrite.
ACTIONS: dict[str, tuple[str, ...]] = {
    "view": ("view_channel",),
    "send": ("send_messages",),
    "threads": ("create_public_threads", "send_messages_in_threads"),
    "reactions": ("add_reactions",),
    "attach": ("attach_files",),
    "links": ("embed_links",),
    "history": ("read_message_history",),
    "manage": ("manage_messages",),
    "mention": ("mention_everyone",),
}

# Presets -> permisos para @everyone (allow/deny por acción).
# True = permitir, False = denegar.
PRESETS: dict[str, dict[str, bool]] = {
    "public": {"view": True, "send": True},
    "read-only": {"view": True, "send": False},
    "staff": {"view": False},
    "hidden": {"view": False},
}


def _apply_actions(overwrite: discord.PermissionOverwrite, actions: dict[str, bool]) -> None:
    """Aplica un dict {accion: allow?} sobre un PermissionOverwrite."""
    for action, allow in actions.items():
        fields = ACTIONS.get(action)
        if not fields:
            log.warning("Acción de permiso desconocida: %r (ignorada)", action)
            continue
        for fld in fields:
            setattr(overwrite, fld, allow)


def _parse_action_list(actions: list[str]) -> dict[str, bool]:
    """`['ver', '-escribir']` -> `{'ver': True, 'escribir': False}`."""
    parsed: dict[str, bool] = {}
    for token in actions:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-"):
            parsed[token[1:].strip()] = False
        else:
            parsed[token] = True
    return parsed


def _find_role(guild: discord.Guild, name: str) -> discord.Role | None:
    """Resuelve un rol por nombre; `@everyone` -> rol por defecto del guild."""
    if name.strip() in ("@everyone", "everyone"):
        return guild.default_role
    lowered = name.strip().lower()
    for role in guild.roles:
        if role.name.lower() == lowered:
            return role
    return None


def build_overwrites(
    guild: discord.Guild,
    access: str | None,
    permissions: dict[str, list[str]],
) -> tuple[dict[discord.Role, discord.PermissionOverwrite], list[str]]:
    """Construye los overwrites del canal a partir del preset + overrides.

    Devuelve `(overwrites, roles_no_encontrados)`.
    """
    overwrites: dict[discord.Role, discord.PermissionOverwrite] = {}
    missing: list[str] = []

    # 1) Preset -> siembra @everyone.
    if access:
        preset = PRESETS.get(access.strip().lower())
        if preset is None:
            log.warning("Preset de acceso desconocido: %r (ignorado)", access)
        else:
            ow = discord.PermissionOverwrite()
            _apply_actions(ow, preset)
            overwrites[guild.default_role] = ow

    # 2) Overrides finos por rol (se aplican encima del preset).
    for role_name, actions in permissions.items():
        role = _find_role(guild, role_name)
        if role is None:
            missing.append(role_name)
            continue
        ow = overwrites.get(role) or discord.PermissionOverwrite()
        _apply_actions(ow, _parse_action_list(actions))
        overwrites[role] = ow

    return overwrites, missing
