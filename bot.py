"""Bot de Discord para el server de Minecraft summerBuddies.

Por ahora solo reporta el estado del server (online/offline, jugadores,
RAM/CPU) leyendo de la API de Crafty Controller. Más funciones (whitelist,
consola, etc.) se añadirán después.

Comandos:
  /estado    -> embed con el estado actual del server.

Además, el bot actualiza su "presencia" (el texto bajo su nombre) cada
STATUS_REFRESH_SECONDS para mostrar jugadores conectados de un vistazo.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import tasks

from config import Config
from crafty import CraftyClient, ServerStatus
from sync import SyncReport, sync_vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("mc-discord-bot")

COLOR_UP = 0x57F287      # verde
COLOR_DOWN = 0xED4245    # rojo
COLOR_ERROR = 0xFEE75C   # amarillo


def build_status_embed(cfg: Config, status: ServerStatus) -> discord.Embed:
    if status.is_up:
        embed = discord.Embed(
            title=f"🟢 {cfg.server_name} — Online",
            color=COLOR_UP,
        )
        players = ", ".join(status.players) if status.players else "nobody online"
        embed.add_field(
            name="Players",
            value=f"**{status.online}/{status.max_players}** — {players}",
            inline=False,
        )
        embed.add_field(name="CPU", value=f"{status.cpu:.1f}%", inline=True)
        embed.add_field(
            name="RAM",
            value=f"{status.mem} ({status.mem_percent:.0f}%)",
            inline=True,
        )
        embed.add_field(name="World", value=status.world_size, inline=True)
        if status.version != "—":
            embed.add_field(name="Version", value=status.version, inline=True)
    else:
        embed = discord.Embed(
            title=f"🔴 {cfg.server_name} — Offline",
            description="The server isn't running right now.",
            color=COLOR_DOWN,
        )

    embed.set_footer(text=f"IP: {cfg.server_address}")
    return embed


def build_sync_embed(report: SyncReport) -> discord.Embed:
    if report.errors:
        color = COLOR_ERROR
    elif report.channels_created or report.channels_updated:
        color = COLOR_UP
    else:
        color = COLOR_ERROR
    embed = discord.Embed(title="🔄 Vault sync", color=color)

    channels = []
    if report.channels_created:
        channels.append(f"created: {', '.join('#' + c for c in report.channels_created)}")
    if report.channels_updated:
        channels.append(f"updated: {', '.join('#' + c for c in report.channels_updated)}")
    embed.add_field(
        name="Channels",
        value="\n".join(channels) if channels else "none",
        inline=False,
    )
    embed.add_field(
        name="Messages",
        value=(
            f"sent: {report.messages_sent} · "
            f"edited: {report.messages_edited} · "
            f"blanked: {report.messages_blanked}"
        ),
        inline=False,
    )
    if report.missing_roles:
        embed.add_field(
            name="⚠️ Roles not found",
            value=", ".join(sorted(report.missing_roles)),
            inline=False,
        )
    if report.errors:
        embed.add_field(
            name="❌ Errors",
            value="\n".join(report.errors)[:1024],
            inline=False,
        )
    return embed


class MCBot(discord.Client):
    def __init__(self, cfg: Config):
        intents = discord.Intents.default()  # no necesitamos intents privilegiados
        super().__init__(intents=intents)
        self.cfg = cfg
        self.crafty = CraftyClient(
            cfg.crafty_panel, cfg.crafty_token, cfg.crafty_server_id
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.refresh_presence.change_interval(seconds=self.cfg.refresh_seconds)
        self.refresh_presence.start()
        # Sincronizar slash commands. Con guild_id es instantáneo (recomendado).
        # Si falla (p.ej. el bot fue invitado sin el scope applications.commands)
        # NO tumbamos el bot: la presencia sigue funcionando y los comandos se
        # registran tras re-invitar + reiniciar el servicio.
        try:
            if self.cfg.guild_id:
                guild = discord.Object(id=self.cfg.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Comandos sincronizados en guild %s", self.cfg.guild_id)
            else:
                await self.tree.sync()
                log.info("Comandos sincronizados globalmente (puede tardar ~1h)")
        except discord.Forbidden:
            log.error(
                "No pude registrar slash commands (403 Missing Access). "
                "Re-invita el bot con el scope 'applications.commands' y "
                "reinicia el servicio. El bot sigue activo (presencia)."
            )

    async def on_ready(self) -> None:
        log.info("Conectado como %s (id %s)", self.user, self.user and self.user.id)

    @tasks.loop(seconds=60)
    async def refresh_presence(self) -> None:
        try:
            status = await self.crafty.get_status()
        except Exception as exc:  # noqa: BLE001 - presencia best-effort
            log.warning("No pude leer estado para la presencia: %s", exc)
            await self.change_presence(
                status=discord.Status.idle,
                activity=discord.Game(name="status unknown"),
            )
            return

        if status.is_up:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{status.online}/{status.max_players} players",
                ),
            )
        else:
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Game(name="server offline"),
            )

    @refresh_presence.before_loop
    async def _before_presence(self) -> None:
        await self.wait_until_ready()


def main() -> None:
    cfg = Config.from_env()
    client = MCBot(cfg)

    @client.tree.command(name="status", description="Show the Minecraft server status")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        try:
            status = await client.crafty.get_status()
        except Exception as exc:  # noqa: BLE001
            log.error("Error consultando Crafty: %s", exc)
            embed = discord.Embed(
                title="⚠️ Couldn't reach the server",
                description="The Crafty API didn't respond. Try again in a moment.",
                color=COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return
        await interaction.followup.send(embed=build_status_embed(cfg, status))

    @client.tree.command(
        name="sync",
        description="Sync channels/messages from the Obsidian vault",
    )
    async def sync(interaction: discord.Interaction) -> None:
        # Solo administradores: crea/edita canales, mensajes y permisos.
        perms = getattr(interaction.user, "guild_permissions", None)
        if interaction.guild is None or perms is None or not perms.administrator:
            await interaction.response.send_message(
                "Only an administrator can use /sync.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            report = await sync_vault(
                interaction.guild, cfg.channels_dir, cfg.state_file
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Error en /sync: %s", exc)
            embed = discord.Embed(
                title="⚠️ Sync failed",
                description=str(exc)[:2000],
                color=COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return
        await interaction.followup.send(embed=build_sync_embed(report))

    client.run(cfg.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
