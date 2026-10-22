"""Aplica un vault de canales a un guild sin levantar el bot entero.

Usa el mismo motor que `/sync` (`sync.sync_vault`), pero desde la terminal: se conecta,
sincroniza y sale. No registra slash commands ni necesita Crafty. Lee `DISCORD_TOKEN` de
`.env` (UrFavoriteHost: necesita Manage Channels + Manage Roles en el guild).

    .venv/bin/python apply_sync.py GUILD_ID CHANNELS_DIR --dry-run
    .venv/bin/python apply_sync.py GUILD_ID CHANNELS_DIR \\
        --rename "Canales de texto=General" --rename "Canales de voz=Voice" \\
        --order "Info,General,CS,Data,Math,Voice,Officers"

- `--rename VIEJO=NUEVO`: renombra una categoría existente antes del sync (p. ej. las que
  Discord crea en español al armar el server), así el sync la reutiliza en vez de duplicarla.
- `--rename-channel VIEJO=NUEVO`: lo mismo para un canal de texto (el sync no cambia nombres:
  sin esto crearía un canal nuevo con el nombre del vault).
- `--order`: deja las categorías en ese orden al final (las no nombradas quedan abajo).
- El estado (archivo → canal/mensajes) va a `.sync-state-GUILD_ID.json` (gitignored).
- Nunca borra canales ni mensajes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import discord

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from sync import sync_vault
from vault import load_docs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("mc-discord-bot")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("guild_id", type=int)
    p.add_argument("channels_dir")
    p.add_argument("--rename", action="append", default=[], metavar="VIEJO=NUEVO")
    p.add_argument("--rename-channel", action="append", default=[], metavar="VIEJO=NUEVO")
    p.add_argument("--order", default="", help="categorías separadas por coma, de arriba a abajo")
    p.add_argument("--state", default=None, help="archivo de estado (default .sync-state-GUILD.json)")
    p.add_argument("--dry-run", action="store_true", help="solo muestra qué canales hay en el vault")
    return p.parse_args()


def dry_run(channels_dir: str) -> None:
    docs = load_docs(channels_dir)
    if not docs:
        sys.exit(f"no hay canales en {channels_dir}")
    current = None
    for d in docs:
        if d.category != current:
            current = d.category
            print(f"\n[{current or '(sin categoría)'}]")
        roles = ", ".join(f"{r}: {' '.join(a)}" for r, a in d.permissions.items())
        print(f"  #{d.name:<26} access={d.access or '-':<9} msgs={len(d.blocks):<2} {roles}")
    print(f"\n{len(docs)} canales")


async def apply(args: argparse.Namespace, token: str) -> int:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    result = {"code": 1}

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(args.guild_id)
            if guild is None:
                log.error("el bot no está en el guild %s", args.guild_id)
                return
            log.info("guild: %s", guild.name)

            for pair in args.rename:
                old, _, new = pair.partition("=")
                cat = discord.utils.get(guild.categories, name=old.strip())
                if cat is None:
                    log.info("rename: no hay categoría %r (ok si ya se renombró)", old)
                elif not discord.utils.get(guild.categories, name=new.strip()):
                    await cat.edit(name=new.strip())
                    log.info("rename: %r → %r", old, new)

            for pair in args.rename_channel:
                old, _, new = pair.partition("=")
                ch = discord.utils.get(guild.text_channels, name=old.strip())
                if ch is None:
                    log.info("rename-channel: no hay #%s (ok si ya se renombró)", old)
                elif not discord.utils.get(guild.text_channels, name=new.strip()):
                    await ch.edit(name=new.strip())
                    log.info("rename-channel: #%s → #%s", old, new)

            state = args.state or f".sync-state-{guild.id}.json"
            report = await sync_vault(guild, args.channels_dir, state)
            log.info("creados: %s", ", ".join(report.channels_created) or "-")
            log.info("actualizados: %s", ", ".join(report.channels_updated) or "-")
            log.info("mensajes: %d nuevos, %d editados, %d blanqueados",
                     report.messages_sent, report.messages_edited, report.messages_blanked)
            if report.missing_roles:
                log.warning("roles que no existen en el server: %s", ", ".join(sorted(report.missing_roles)))
            for err in report.errors:
                log.error(err)

            if args.order:
                wanted = [n.strip().lower() for n in args.order.split(",") if n.strip()]
                cats = sorted(guild.categories, key=lambda c: (wanted.index(c.name.lower()) if c.name.lower() in wanted else len(wanted), c.position))
                for i, cat in enumerate(cats):
                    if cat.position != i:
                        await cat.edit(position=i)
                log.info("orden: %s", ", ".join(c.name for c in cats))
            result["code"] = 1 if report.errors else 0
        finally:
            await client.close()

    await client.start(token)
    return result["code"]


def main() -> None:
    args = parse_args()
    if args.dry_run:
        dry_run(args.channels_dir)
        return
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        sys.exit("falta DISCORD_TOKEN (en .env)")
    sys.exit(asyncio.run(apply(args, token)))


if __name__ == "__main__":
    main()
