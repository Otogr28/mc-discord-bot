"""Cliente mínimo para la API de Crafty Controller (v2).

Solo lo necesario para leer el estado del server. La API de Crafty usa un
certificado autofirmado, así que desactivamos la verificación TLS (el panel
escucha en localhost del VPS, no es tráfico expuesto a internet).
"""

from __future__ import annotations

import ast
import ssl
from dataclasses import dataclass

import aiohttp


@dataclass
class ServerStatus:
    """Estado normalizado del server de Minecraft."""

    running: bool
    online: int
    max_players: int
    players: list[str]
    cpu: float
    mem: str
    mem_percent: float
    world_size: str
    version: str
    motd: str

    @property
    def is_up(self) -> bool:
        return self.running


def _parse_players(raw) -> list[str]:
    """El campo `players` viene como repr de lista ("['a','b']") cuando hay
    gente, o como "False"/False cuando el server está apagado."""
    if not raw or raw == "False":
        return []
    if isinstance(raw, list):
        return [str(p) for p in raw]
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, (list, tuple)):
            return [str(p) for p in value]
    except (ValueError, SyntaxError):
        pass
    return []


def _clean(value, default: str = "—") -> str:
    """Crafty devuelve la cadena "False" para campos vacíos cuando el server
    está apagado; lo convertimos en algo presentable."""
    if value in (None, "False", False, "", 0, 0.0):
        return default
    return str(value)


class CraftyClient:
    def __init__(self, panel: str, token: str, server_id: str):
        self._panel = panel.rstrip("/")
        self._server_id = server_id
        self._headers = {"Authorization": f"Bearer {token}"}
        # Cert autofirmado -> no verificar.
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE

    async def get_status(self) -> ServerStatus:
        url = f"{self._panel}/api/v2/servers/{self._server_id}/stats"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=self._headers, ssl=self._ssl) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        data = payload.get("data", {})
        return ServerStatus(
            running=bool(data.get("running", False)),
            online=int(data.get("online", 0) or 0),
            max_players=int(data.get("max", 0) or 0),
            players=_parse_players(data.get("players")),
            cpu=float(data.get("cpu", 0.0) or 0.0),
            mem=_clean(data.get("mem"), "0"),
            mem_percent=float(data.get("mem_percent", 0.0) or 0.0),
            world_size=_clean(data.get("world_size")),
            version=_clean(data.get("version")),
            motd=_clean(data.get("desc")),
        )
