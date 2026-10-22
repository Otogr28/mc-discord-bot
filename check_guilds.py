"""Lista los servers (guilds) en los que está el bot.

Uso:
    DISCORD_TOKEN=... .venv/bin/python check_guilds.py
o poniendo DISCORD_TOKEN en un .env local (gitignored).
"""

import os
import urllib.request
import json

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

token = os.environ.get("DISCORD_TOKEN")
if not token:
    raise SystemExit("Falta DISCORD_TOKEN (ponlo en .env o en el entorno)")

req = urllib.request.Request(
    "https://discord.com/api/v10/users/@me/guilds",
    headers={"Authorization": f"Bot {token}", "User-Agent": "check-guilds/1.0"},
)
with urllib.request.urlopen(req) as resp:
    guilds = json.load(resp)

if not guilds:
    print("El bot no está en ningún server.")
for g in guilds:
    print(f"{g['id']}  {g['name']}")
