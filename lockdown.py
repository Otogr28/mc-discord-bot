"""Lockdown de un servidor de Discord.

Dos fases independientes:

  channels  -> @everyone pierde "Ver canal" en TODO menos en los canales de VISIBLE.
  roles     -> a cada miembro que NO tenga el rol admin se le quitan todos sus roles.

Por defecto es DRY-RUN: imprime lo que haría y no toca nada.
Para aplicar de verdad hay que pasar --apply.

    .venv/bin/python lockdown.py --phase channels
    .venv/bin/python lockdown.py --phase channels --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
VIEW_CHANNEL = 0x400

# --- CMD Club -----------------------------------------------------------
GUILD_ID = "1139268564608630977"
ADMIN_ROLE_ID = "1139269086463938683"          # 'Admin'
VISIBLE = {"1139375951088726106"}              # '📜welcome-and-rules'
# ------------------------------------------------------------------------


def load_token() -> str:
    for line in open(".env"):
        if line.startswith("DISCORD_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("No encontré DISCORD_TOKEN en .env")


class Discord:
    def __init__(self, token: str):
        self.token = token

    def _call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bot {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "lockdown/1.0",
            },
        )
        while True:
            try:
                with urllib.request.urlopen(req) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 429:  # rate limit: esperar lo que diga Discord
                    retry = json.load(e).get("retry_after", 1)
                    time.sleep(retry + 0.1)
                    continue
                raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:200]}")

    def get(self, path):
        return self._call("GET", path)

    def put(self, path, body):
        return self._call("PUT", path, body)

    def delete(self, path):
        return self._call("DELETE", path)


def phase_channels(dc: Discord, apply: bool) -> None:
    """@everyone: denegar VIEW en todo, permitirlo solo en VISIBLE.

    Dos cuidados que costaron caro la primera vez:

    1. Los canales de VISIBLE se procesan ANTES que los denegados. Si primero se
       oculta la categoría, un canal hijo que heredaba queda oculto también y el
       bot pierde el acceso necesario para arreglarlo después (403 Missing Access).
    2. Antes de denegar nada, el bot se da a sí mismo un override explícito de
       VIEW. Sin eso se cierra la puerta desde dentro y no puede deshacer.
    """
    channels = dc.get(f"/guilds/{GUILD_ID}/channels")
    me = dc.get("/users/@me")
    my_member = dc.get(f"/guilds/{GUILD_ID}/members/{me['id']}")
    my_roles = my_member["roles"]

    print(f"\n=== FASE CANALES ({len(channels)} canales/categorías) ===")

    # VISIBLE primero, denegados después (ver cuidado 1).
    ordered = sorted(channels, key=lambda c: (c["id"] not in VISIBLE, c["position"]))

    for ch in ordered:
        should_see = ch["id"] in VISIBLE
        overwrites = ch.get("permission_overwrites", [])
        existing = next((o for o in overwrites if o["id"] == GUILD_ID),
                        {"allow": "0", "deny": "0"})
        allow, deny = int(existing["allow"]), int(existing["deny"])

        new_allow = (allow & ~VIEW_CHANNEL) | (VIEW_CHANNEL if should_see else 0)
        new_deny = (deny & ~VIEW_CHANNEL) | (0 if should_see else VIEW_CHANNEL)

        if (new_allow, new_deny) == (allow, deny):
            print(f"  = {ch['name']!r} ya está como debe")
            continue

        # cuidado 2: asegurar mi propio acceso antes de tocar @everyone.
        if not should_see and apply:
            for rid in my_roles:
                mine = next((o for o in overwrites if o["id"] == rid), {"allow": "0", "deny": "0"})
                m_allow, m_deny = int(mine["allow"]), int(mine["deny"])
                if not m_allow & VIEW_CHANNEL:
                    dc.put(f"/channels/{ch['id']}/permissions/{rid}",
                           {"type": 0, "allow": str(m_allow | VIEW_CHANNEL),
                            "deny": str(m_deny & ~VIEW_CHANNEL)})

        verb = "VER" if should_see else "ocultar"
        print(f"  → {ch['name']!r}: {verb} para @everyone")
        if apply:
            dc.put(
                f"/channels/{ch['id']}/permissions/{GUILD_ID}",
                {"type": 0, "allow": str(new_allow), "deny": str(new_deny)},
            )


def iter_members(dc: Discord):
    after = "0"
    while True:
        batch = dc.get(f"/guilds/{GUILD_ID}/members?limit=1000&after={after}")
        if not batch:
            return
        yield from batch
        after = batch[-1]["user"]["id"]
        if len(batch) < 1000:
            return


def phase_roles(dc: Discord, apply: bool, include_bots: bool) -> None:
    """Quitar todos los roles a quien no tenga ADMIN_ROLE_ID."""
    roles = {r["id"]: r for r in dc.get(f"/guilds/{GUILD_ID}/roles")}
    me = dc.get("/users/@me")
    my_member = dc.get(f"/guilds/{GUILD_ID}/members/{me['id']}")
    my_top = max((roles[r]["position"] for r in my_member["roles"] if r in roles), default=0)

    # solo se puede quitar un rol estrictamente por debajo del rol más alto del bot,
    # y nunca uno 'managed' (los que pertenecen a una integración/bot).
    removable = {
        rid for rid, r in roles.items()
        if rid != GUILD_ID and not r["managed"] and r["position"] < my_top
    }
    print(f"\n=== FASE ROLES (mi rol más alto: position {my_top}) ===")
    print(f"  roles que puedo quitar: {sorted(roles[r]['name'] for r in removable) or 'NINGUNO'}")
    blocked = [r["name"] for rid, r in roles.items()
               if rid != GUILD_ID and rid not in removable and not r["managed"]]
    if blocked:
        print(f"  ⚠️  fuera de mi alcance (suben mi rol en Ajustes → Roles): {sorted(blocked)}")

    for m in iter_members(dc):
        user = m["user"]
        name = user.get("global_name") or user["username"]
        if ADMIN_ROLE_ID in m["roles"]:
            print(f"  · {name}: es Admin, no se toca")
            continue
        if user.get("bot") and not include_bots:
            print(f"  · {name}: es un bot, se salta")
            continue
        to_remove = [r for r in m["roles"] if r in removable]
        if not to_remove:
            continue
        print(f"  → {name}: quitar {[roles[r]['name'] for r in to_remove]}")
        if apply:
            for rid in to_remove:
                dc.delete(f"/guilds/{GUILD_ID}/members/{user['id']}/roles/{rid}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["channels", "roles", "both"], required=True)
    p.add_argument("--apply", action="store_true", help="aplicar de verdad (si no, dry-run)")
    p.add_argument("--include-bots", action="store_true", help="también quitar roles a bots")
    args = p.parse_args()

    dc = Discord(load_token())
    guild = dc.get(f"/guilds/{GUILD_ID}")
    mode = "APLICANDO CAMBIOS" if args.apply else "DRY-RUN (no toca nada)"
    print(f"Guild: {guild['name']} ({GUILD_ID})  —  {mode}")

    if args.phase in ("channels", "both"):
        phase_channels(dc, args.apply)
    if args.phase in ("roles", "both"):
        try:
            phase_roles(dc, args.apply, args.include_bots)
        except RuntimeError as e:
            print(f"\n  ❌ {e}", file=sys.stderr)
            print("  → falta activar SERVER MEMBERS INTENT en el Developer Portal.", file=sys.stderr)


if __name__ == "__main__":
    main()
