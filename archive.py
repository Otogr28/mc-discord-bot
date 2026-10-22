"""Archiva CMD Club: mueve los canales viejos a una categoría 'old' solo-Admin
y borra las categorías que quedan vacías.

  - Los canales de 'Admin Only' no se tocan (ni ellos ni su categoría).
  - 'welcome-and-rules' se queda fuera, visible para @everyone.
  - Los canales movidos pierden TODOS sus overwrites propios y pasan a heredar
    de 'old' (@everyone denegado, Admin permitido). Esto es lo que impide que
    Student/Senior/Professor/etc. los sigan viendo: tenían allow explícito.

Dry-run por defecto; --apply para ejecutar.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
VIEW_CHANNEL = 0x400

GUILD_ID = "1139268564608630977"
ADMIN_ROLE_ID = "1139269086463938683"
ADMIN_CATEGORY_ID = "1139366192491016232"     # 'Admin Only' — intocable
KEEP_OUT = {"1139375951088726106"}            # 'welcome-and-rules' se queda fuera
OLD_CATEGORY_NAME = "old"

CATEGORY = 4


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
            API + path, data=data, method=method,
            headers={"Authorization": f"Bot {self.token}",
                     "Content-Type": "application/json",
                     "User-Agent": "archive/1.0"},
        )
        while True:
            try:
                with urllib.request.urlopen(req) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(json.load(e).get("retry_after", 1) + 0.1)
                    continue
                raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:200]}")

    def get(self, p):
        return self._call("GET", p)

    def post(self, p, b):
        return self._call("POST", p, b)

    def patch(self, p, b):
        return self._call("PATCH", p, b)

    def delete(self, p):
        return self._call("DELETE", p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dc = Discord(load_token())
    apply = args.apply

    print(f"CMD Club — {'APLICANDO' if apply else 'DRY-RUN (no toca nada)'}")

    channels = dc.get(f"/guilds/{GUILD_ID}/channels")
    by_id = {c["id"]: c for c in channels}

    def is_admin_side(c):
        return c["id"] == ADMIN_CATEGORY_ID or c.get("parent_id") == ADMIN_CATEGORY_ID

    to_move = [c for c in channels
               if c["type"] != CATEGORY and not is_admin_side(c) and c["id"] not in KEEP_OUT]
    cats_to_delete = [c for c in channels
                      if c["type"] == CATEGORY and c["id"] != ADMIN_CATEGORY_ID]

    print(f"\n1) crear categoría {OLD_CATEGORY_NAME!r} (solo Admin)")
    old_id = None
    if apply:
        old = dc.post(f"/guilds/{GUILD_ID}/channels", {
            "name": OLD_CATEGORY_NAME, "type": CATEGORY,
            "permission_overwrites": [
                {"id": GUILD_ID, "type": 0, "allow": "0", "deny": str(VIEW_CHANNEL)},
                {"id": ADMIN_ROLE_ID, "type": 0, "allow": str(VIEW_CHANNEL), "deny": "0"},
            ],
        })
        old_id = old["id"]
        print(f"   creada id={old_id}")

    print(f"\n2) mover {len(to_move)} canales a {OLD_CATEGORY_NAME!r} y limpiar sus overwrites")
    for c in to_move:
        par = by_id.get(c.get("parent_id"))
        n_ov = len(c.get("permission_overwrites", []))
        print(f"   → {c['name']!r:26} (de {par['name'] if par else '—'}) "
              f"borra {n_ov} overwrite(s) propios")
        if apply:
            dc.patch(f"/channels/{c['id']}",
                     {"parent_id": old_id, "permission_overwrites": []})
            time.sleep(0.4)

    print(f"\n3) borrar {len(cats_to_delete)} categorías vacías")
    for c in cats_to_delete:
        print(f"   ✗ {c['name']!r}")
        if apply:
            dc.delete(f"/channels/{c['id']}")
            time.sleep(0.4)

    keep = [c for c in channels if is_admin_side(c)] + [by_id[i] for i in KEEP_OUT if i in by_id]
    print(f"\nintactos ({len(keep)}): {[c['name'] for c in keep]}")


if __name__ == "__main__":
    main()
