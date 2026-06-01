"""Motor de sincronización vault -> Discord.

Reconcilia cada `ChannelDoc` con un canal de Discord y sus mensajes:
crea/actualiza el canal (categoría, topic, permisos) y mantiene un mensaje por
bloque, **editando in-place** en vez de reenviar. Los mensajes sobrantes (un
bloque que se borró) NO se eliminan: se editan a un carácter invisible para
conservar el mensaje y su ID.

El mapping archivo -> canal/mensajes vive en un JSON sidecar (`state_file`).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import discord

from permissions import build_overwrites
from vault import ChannelDoc, load_docs

log = logging.getLogger("mc-discord-bot")

BLANK = "​"          # zero-width space: mensaje "vacío" sin borrarlo
MAX_LEN = 2000            # límite de caracteres de un mensaje de Discord


@dataclass
class SyncReport:
    channels_created: list[str] = field(default_factory=list)
    channels_updated: list[str] = field(default_factory=list)
    messages_sent: int = 0
    messages_edited: int = 0
    messages_blanked: int = 0
    missing_roles: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def _slug(name: str) -> str:
    """Normaliza un nombre al formato de canal de Discord (lower, guiones)."""
    return re.sub(r"[^a-z0-9-]", "", name.strip().lower().replace(" ", "-"))


def _clip(text: str) -> str:
    if not text:
        return BLANK
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 1] + "…"


def _load_state(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("No pude leer el estado %s: %s (empiezo vacío)", path, exc)
        return {}


def _save_state(path: str | Path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


async def _ensure_category(
    guild: discord.Guild, name: str | None
) -> discord.CategoryChannel | None:
    if not name:
        return None
    wanted = _slug(name)
    for cat in guild.categories:
        if _slug(cat.name) == wanted:
            return cat
    return await guild.create_category(name)


async def _ensure_channel(
    guild: discord.Guild,
    doc: ChannelDoc,
    entry: dict,
    report: SyncReport,
) -> discord.TextChannel | None:
    """Resuelve (o crea) el canal del doc y aplica categoría/topic/permisos."""
    overwrites, missing = build_overwrites(guild, doc.access, doc.permissions)
    report.missing_roles.update(missing)
    category = await _ensure_category(guild, doc.category)
    wanted = _slug(doc.name)

    # 1) Por channel_id guardado.
    channel = guild.get_channel(entry.get("channel_id")) if entry.get("channel_id") else None
    # 2) Por nombre.
    if channel is None:
        channel = discord.utils.find(
            lambda c: _slug(c.name) == wanted, guild.text_channels
        )
    # 3) Crear.
    if channel is None:
        channel = await guild.create_text_channel(
            doc.name,
            category=category,
            topic=doc.topic,
            overwrites=overwrites or discord.utils.MISSING,
        )
        report.channels_created.append(channel.name)
    else:
        await channel.edit(
            category=category,
            topic=doc.topic,
            overwrites=overwrites or discord.utils.MISSING,
        )
        report.channels_updated.append(channel.name)

    entry["channel_id"] = channel.id
    return channel


async def _reconcile_messages(
    channel: discord.TextChannel,
    doc: ChannelDoc,
    entry: dict,
    report: SyncReport,
) -> None:
    ids: list[int] = list(entry.get("messages", []))

    # Un mensaje por bloque, en orden.
    for i, block in enumerate(doc.blocks):
        content = _clip(block)
        if i < len(ids):
            try:
                msg = await channel.fetch_message(ids[i])
            except discord.NotFound:
                msg = await channel.send(content)
                ids[i] = msg.id
                report.messages_sent += 1
                continue
            if msg.content != content:
                await msg.edit(content=content)
                report.messages_edited += 1
        else:
            msg = await channel.send(content)
            ids.append(msg.id)
            report.messages_sent += 1

    # Mensajes sobrantes -> blanquear (nunca borrar).
    for j in range(len(doc.blocks), len(ids)):
        try:
            msg = await channel.fetch_message(ids[j])
        except discord.NotFound:
            continue
        if msg.content != BLANK:
            await msg.edit(content=BLANK)
            report.messages_blanked += 1

    entry["messages"] = ids


async def sync_vault(
    guild: discord.Guild,
    channels_dir: str,
    state_file: str,
) -> SyncReport:
    """Sincroniza todos los `.md` del vault con el guild dado."""
    report = SyncReport()
    state = _load_state(state_file)
    docs = load_docs(channels_dir)

    for doc in docs:
        entry = state.get(doc.key, {})
        try:
            channel = await _ensure_channel(guild, doc, entry, report)
            if channel is not None:
                await _reconcile_messages(channel, doc, entry, report)
            state[doc.key] = entry
        except discord.DiscordException as exc:
            log.error("Error sincronizando %s: %s", doc.key, exc)
            report.errors.append(f"{doc.key}: {exc}")
        finally:
            # Persistimos tras cada archivo para no perder IDs si algo falla.
            _save_state(state_file, state)

    return report
