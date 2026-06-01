# mc-discord-bot

Bot de Discord para el server de Minecraft **summerBuddies** (Forge 1.20.1,
gestionado por Crafty Controller en el VPS).

Por ahora solo reporta **estado del server** leyendo de la API de Crafty.
Más adelante: whitelist desde Discord, consola/comandos, puente de chat, etc.

> ⚠️ Este repo es **aparte** del modpack público (`MCserver`) a propósito: los
> jugadores no necesitan el bot, y así no se les descarga al clonar el modpack.

## Qué hace

- **`/estado`** — slash command con un embed: online/offline, jugadores
  conectados, CPU, RAM, tamaño del mundo, versión.
- **Presencia automática** — el texto bajo el nombre del bot muestra
  `X/Y jugadores` (o "server offline"), refrescado cada `STATUS_REFRESH_SECONDS`.
- **`/sync`** — sincroniza canales/mensajes desde un **vault de Obsidian**
  (`Channels/`): cada `.md` describe un canal y su contenido. Ver más abajo.

## Canales desde Obsidian (`/sync`)

Cada archivo `.md` en `Channels/` describe un canal de Discord. El **frontmatter**
(properties de Obsidian) define el canal y sus permisos; el **cuerpo**, separado en
bloques por líneas `---`, se publica como mensajes que el bot **mantiene editados**
(no reenvía). Un bloque que borras no elimina el mensaje: lo deja en blanco.

```markdown
---
channel: reglas              # nombre del canal (si falta, usa el del archivo)
category: información         # categoría (se crea si no existe)
topic: Lee antes de jugar     # topic del canal
access: solo-lectura          # preset de permisos
permissions:                  # overrides finos rol -> acciones
  "@everyone": [ver, -escribir]
  Moderador: [ver, escribir, gestionar, hilos]
---

Primer mensaje. Una URL de imagen se auto-embebe: ![](https://i.imgur.com/x.png)

---

Segundo mensaje (otro bloque).
```

- **Presets** (`access:`): `publico`, `solo-lectura`, `staff`, `oculto`.
- **Acciones** (en `permissions:`): `ver`, `escribir`, `hilos`, `reacciones`,
  `adjuntar`, `enlaces`, `historial`, `gestionar`, `mencionar`.
  Prefijo `-` = denegar (`-escribir`); sin prefijo = permitir; ausente = heredar.
- **Roles** se resuelven por nombre; `@everyone` = todos. Rol inexistente → aviso, no rompe.
- `/sync` es **solo para administradores**. El bot **nunca borra** canales ni mensajes.

> El bot necesita los permisos **Gestionar canales** y **Gestionar roles**. Si
> invitaste el bot antes de tener `/sync`, re-invítalo con el link de abajo y
> reinicia el servicio.

## 1. Crear la app/bot en Discord

1. Ve a https://discord.com/developers/applications → **New Application**.
2. Pestaña **Bot** → **Reset Token** → copia el token (va en `DISCORD_TOKEN`).
   No actives intents privilegiados (no hacen falta).
3. Pestaña **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`;
   permisos `Send Messages`, `Embed Links`, `Use Slash Commands`, y para `/sync`
   también `Manage Channels` + `Manage Roles`. Abre la URL e invita el bot.
4. Activa **Modo Desarrollador** en Discord (Ajustes → Avanzado), click derecho
   a tu server → **Copiar ID del servidor** → va en `DISCORD_GUILD_ID`.

## 2. Probar en local (opcional)

El panel de Crafty solo escucha en `127.0.0.1:8443` del VPS, así que para
probar desde la laptop necesitas un túnel SSH al panel (igual que `mc-panel`):

```bash
ssh -N -L 8443:127.0.0.1:8443 mcserver &   # túnel al panel
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # rellena DISCORD_TOKEN, CRAFTY_TOKEN, DISCORD_GUILD_ID
python bot.py
```

`CRAFTY_TOKEN` es la misma API key que usan los helpers; en el VPS está en
`/etc/mcserver/crafty.env` (variable `TOKEN`).

## 3. Desplegar en el VPS

El bot corre como servicio systemd en `/opt/mc-discord-bot`, junto a Crafty. El código
se mueve **por git** (la laptop hace `git push`, el VPS hace `git pull`), no por rsync.
El VPS clona el repo privado con una **deploy key de solo-lectura**.

```bash
# --- en el VPS (ssh mcserver): clonar con la deploy key ---
# 1) Generar la deploy key y registrarla en el repo (read-only) una sola vez:
ssh-keygen -t ed25519 -N '' -f /root/.ssh/mc-discord-bot-deploy
#    -> añade /root/.ssh/mc-discord-bot-deploy.pub como Deploy Key (read-only) en GitHub.
# 2) Clonar usando esa clave:
GIT_SSH_COMMAND='ssh -i /root/.ssh/mc-discord-bot-deploy -o IdentitiesOnly=yes' \
  git clone git@github.com:Otogr28/mc-discord-bot.git /opt/mc-discord-bot
cd /opt/mc-discord-bot
git config core.sshCommand 'ssh -i /root/.ssh/mc-discord-bot-deploy -o IdentitiesOnly=yes'

# 3) venv + dependencias.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Archivo de secretos para systemd (root, 600).
# Reusa TOKEN/SERVER_ID de /etc/mcserver/crafty.env y añade el token de Discord.
cat > /etc/mcserver/discord-bot.env <<'EOF'
DISCORD_TOKEN=pega_aqui_el_token_del_bot
DISCORD_GUILD_ID=pega_aqui_el_id_del_server
CRAFTY_PANEL=https://127.0.0.1:8443
CRAFTY_TOKEN=pega_aqui_el_TOKEN_de_crafty.env
CRAFTY_SERVER_ID=19aa7f07-e3bd-481d-b029-1f3f6eac5f28
MC_SERVER_NAME=summerBuddies
MC_SERVER_ADDRESS=5.78.204.157
STATUS_REFRESH_SECONDS=60
EOF
chmod 600 /etc/mcserver/discord-bot.env

# Instalar y arrancar el servicio.
cp deploy/mc-discord-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mc-discord-bot
systemctl status mc-discord-bot
journalctl -u mc-discord-bot -f      # ver logs en vivo
```

### Re-desplegar tras editar el código

```bash
# laptop: subir cambios
git add -A && git commit -m "..." && git push
# VPS: jalar y reiniciar
ssh mcserver 'cd /opt/mc-discord-bot && git pull'
# si cambió requirements: ssh mcserver '/opt/mc-discord-bot/.venv/bin/pip install -r /opt/mc-discord-bot/requirements.txt'
ssh mcserver systemctl restart mc-discord-bot
```

## Configuración (variables de entorno)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DISCORD_TOKEN` | sí | Token del bot de Discord. |
| `CRAFTY_TOKEN` | sí | API key de Crafty (igual que los helpers). |
| `CRAFTY_SERVER_ID` | sí | UUID del server en Crafty. |
| `DISCORD_GUILD_ID` | no* | ID del server de Discord. Sin él los slash commands tardan ~1h en aparecer. |
| `CRAFTY_PANEL` | no | URL del panel (def. `https://127.0.0.1:8443`). |
| `MC_SERVER_NAME` | no | Nombre a mostrar (def. `summerBuddies`). |
| `MC_SERVER_ADDRESS` | no | IP/dominio mostrado en el footer. |
| `STATUS_REFRESH_SECONDS` | no | Frecuencia de refresco de presencia (def. `60`). |
| `CHANNELS_DIR` | no | Carpeta del vault con los `.md` (def. `Channels`). |
| `SYNC_STATE_FILE` | no | JSON con el mapping canal/mensajes (def. `.sync-state.json`). |

## Estructura

```
bot.py        # cliente de Discord, slash commands /estado y /sync, presencia
crafty.py     # cliente de la API de Crafty (solo lectura de estado)
vault.py      # lee los .md del vault (frontmatter + bloques)
permissions.py# lenguaje de permisos del frontmatter -> overwrites de Discord
sync.py       # motor de sync vault->Discord (canales + mensajes, estado JSON)
config.py     # carga de config desde entorno / .env
Channels/     # vault de Obsidian: un .md por canal
deploy/mc-discord-bot.service   # unidad systemd para el VPS
```
