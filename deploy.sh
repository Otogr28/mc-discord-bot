#!/usr/bin/env bash
# Sube los cambios a GitHub y hace que el VPS los jale (git en medio, sin rsync).
#
#   ./deploy.sh "mensaje"            # canales editados: push + el VPS jala
#   ./deploy.sh "mensaje" --restart  # cambiaste CÓDIGO: además reinicia el bot
#
# Tras editar canales (.md): corre esto y luego /sync en Discord.
set -euo pipefail

msg="${1:-update}"
restart="${2:-}"

cd "$(dirname "$0")"

# 1) Commit + push desde la laptop.
git add -A
if ! git diff --cached --quiet; then
  git commit -m "$msg"
else
  echo "· nada nuevo que commitear"
fi
git push origin main

# 2) El VPS jala (deploy key read-only).
ssh mcserver 'cd /opt/mc-discord-bot && git pull --ff-only'

# 3) Reiniciar solo si cambió el código del bot.
if [[ "$restart" == "--restart" ]]; then
  ssh mcserver 'systemctl restart mc-discord-bot'
  echo "· servicio reiniciado"
fi

echo "✓ Listo. Si editaste canales, corre /sync en Discord para aplicar."
