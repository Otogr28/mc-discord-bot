# Changelog

Cambios notables del proyecto. Fechas en formato ISO.

## 2026-10-21 — `apply_sync.py`: aplicar un vault sin levantar el bot

### Añadido

- `apply_sync.py GUILD_ID CHANNELS_DIR` — corre `sync_vault` desde la terminal (conecta, sincroniza,
  sale), sin slash commands ni Crafty (el `bot.py` sigue sin arrancar por `config.py`). `--dry-run`
  lista los canales del vault; `--rename VIEJO=NUEVO` renombra categorías antes (las que Discord
  crea en español); `--order` deja las categorías en orden. Estado por guild en
  `.sync-state-GUILD.json` (gitignored).
- Pensado para el server nuevo **CMD CLUB** (`1562620709329575947`) con la plantilla del vault
  `CMD-Club/Discord/`. Falta invitar UrFavoriteHost ahí (link de invitación en CLAUDE.md).

## 2026-09-09 — Archivado de CMD Club (categoría `old`)

### Añadido

- `archive.py` — mueve los canales viejos a una categoría `old` solo-Admin y borra las
  categorías que quedan vacías. Dry-run por defecto.

### Aplicado

- Creada la categoría **`old`** (`1547391748106485763`): `@everyone` denegado, `Admin` permitido.
- **12 canales movidos** a `old`, borrando sus overwrites propios para que hereden:
  💻general, 📝class-help, 📢announcements, 🛬landing, 🥫roles, 🌚student-general, 🎠memes,
  🎮gaming, ⭐starboard, 🚢farewell y las voces Everyone / Student Lounge.
- **5 categorías borradas**: information, Everyone, students, Exodus, Voice Channels.
- **Intactos**: la categoría `Admin Only` con sus 5 canales, y `📜welcome-and-rules`
  (fuera de categoría, único visible para `@everyone`).
- Verificado rol por rol: los 12 canales de `old` los ve solo `Admin`.

### Por qué se limpiaron los overwrites

No bastaba con mover y denegar `@everyone`: esos canales tenían *allow* explícito de VIEW
para Student, Senior, Junior, Sophomore, Freshman, Professor, Bot y RTuck (hasta un usuario
suelto en ⭐starboard). Un allow de canal gana sobre el deny de la categoría, así que
cualquiera que recuperase un rol habría vuelto a verlos. Dejarlos con cero overwrites hace
que hereden de `old` y no haya puertas traseras.

### Nota

- Los roles `Moderator` y `RTuck` conservan acceso a canales de `Admin Only`
  (moderators-chat, bot-spam, important-stuff, voz moderators). Hoy no los tiene nadie
  asignado, pero el permiso sigue ahí.
- Backup previo en `backup-channels-cmdclub-2026-09-09-pre-archive.json` (gitignored).

## 2026-09-09 — Lockdown de CMD Club (canales)

El bot se invitó a **CMD Club** (`1139268564608630977`) y se le dio el rol `Admin`.

### Añadido

- `lockdown.py` — dos fases independientes, dry-run por defecto:
  - `channels`: `@everyone` pierde *Ver canal* en todo salvo los IDs de `VISIBLE`.
  - `roles`: quita todos los roles a los miembros que no tengan `Admin`.

### Aplicado

- `@everyone` ahora solo ve `📜welcome-and-rules`. Cambios reales: categorías
  `information` y `Exodus` ocultadas, `🛬landing` oculto, `welcome-and-rules` con
  *allow* explícito. El resto del server ya estaba denegado de antes.
- Backup del estado previo de los 24 canales en `backup-overwrites-cmdclub-2026-09-09.json`
  (gitignored).

### Aprendido a la mala

- **Orden importa:** si se deniega la categoría antes de dar *allow* explícito al canal
  hijo que hereda, el bot se queda sin acceso y no puede terminar (403 `Missing Access`),
  ni revertir. `phase_channels` ahora procesa los canales visibles primero y se asigna un
  override propio de VIEW antes de denegar nada.
- **Jerarquía de roles:** solo se pueden quitar roles *estrictamente por debajo* del rol
  más alto del bot, y nunca los `managed`.
- **Server Members Intent** es un ajuste de la app en el Developer Portal, no un permiso
  del servidor: **Administrator no lo suplanta**. Sin él, `GET /guilds/{id}/members` da 403.

### Aplicado (fase roles)

- Activado SERVER MEMBERS INTENT en el Developer Portal (desbloquea `GET /guilds/{id}/members`).
- Quitados **47 roles a 27 miembros**: Student ×25, Senior ×9, Sophomore ×8, Junior ×2,
  Professor ×2, RTuck ×1, Moderator ×1. Intactos los 5 Admins y los bots.
- Verificado: 0 no-admins conservan roles.
- Backup previo de los 37 miembros con sus roles en `backup-roles-cmdclub-2026-09-09.json`
  (gitignored) — es la única forma de revertir, Discord no lo guarda.

### Pendiente

- El bot quedó con el rol `Admin` en CMD Club. Para lo que hace le basta `UrFavoriteHost`
  (Manage Roles + Manage Channels) posicionado por encima de `Moderator`.

## 2026-09-09 — Pivot: de bot de Minecraft a herramienta de Discord

### Cambiado

- **El proyecto ya no es un bot de Minecraft.** Se conserva únicamente el motor `/sync`
  (vault de Obsidian → canales y mensajes de Discord); el propósito ahora es customizar
  servidores de Discord.
- **Se retiró el VPS.** El host `mcserver` (Hetzner, con Crafty Controller) ya no existe.
  Con él se van el servicio systemd, el flujo de deploy `git push` → `git pull` → restart,
  y el acceso por Tailscale.
- **El bot corre en la PC local**, a mano y bajo demanda. No hay servicio ni uptime: se
  levanta para correr `/sync` y se apaga.
- **Secretos:** `DISCORD_TOKEN` pasa del `EnvironmentFile` de systemd (`/etc/mcserver/discord-bot.env`)
  a un `.env` local (chmod 600, gitignored).

### Añadido

- `check_guilds.py` — lista los guilds en los que está el bot vía `GET /users/@me/guilds`.

### Obsoleto (sigue en el repo, ya no funciona)

- `crafty.py`, el comando `/estado` y el loop de presencia: dependían de la API de Crafty
  en el VPS.
- `deploy.sh` y `deploy/mc-discord-bot.service`.
- El contenido de `Channels/*.md` es del server de Minecraft; queda como ejemplo del formato.

### Pendiente

- El bot **no arranca**: `Config.from_env()` todavía exige `CRAFTY_TOKEN` y `CRAFTY_SERVER_ID`.
- Invitar el bot al server "Computer Science Club" — hoy solo está en `Realm Gates`
  (`1510705735091224812`).
- `README.md` sigue describiendo el proyecto viejo de Minecraft.

## 2026-05-31 — Inicio

- Bot de estado para el server de Minecraft summerBuddies leyendo la API de Crafty Controller
  (`/estado` + presencia automática).
- Feature `/sync`: replica canales y mensajes de Discord desde un vault de Obsidian
  (`vault.py`, `permissions.py`, `sync.py`).
- Desplegado como servicio systemd en el VPS; repo privado `Otogr28/mc-discord-bot` con
  deploy key read-only.
