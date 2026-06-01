---
ignore: true
---

# 📖 Vocabulario del sync (el bot ignora este archivo)

Este archivo **no** se sincroniza con Discord porque tiene `ignore: true` en sus
properties. Úsalo como chuleta. (También se ignoran los archivos cuyo nombre
empieza con `_`.)

## Properties de un canal (frontmatter)

| property      | qué hace                                                       |
| ------------- | -------------------------------------------------------------- |
| `channel`     | Nombre del canal (#…). Si falta, usa el nombre del archivo.     |
| `category`    | Categoría de Discord (se crea si no existe).                   |
| `topic`       | Topic / descripción del canal.                                 |
| `access`      | Preset de permisos (abajo).                                    |
| `permissions` | Lista de overrides por rol (abajo).                            |
| `ignore`      | `true` para que el bot ignore este archivo.                    |

## Presets — `access:`

| preset      | efecto sobre @everyone        |
| ----------- | ----------------------------- |
| `public`    | ven y escriben                |
| `read-only` | ven, no escriben              |
| `staff`     | no ven (solo roles con override) |
| `hidden`    | no ven                        |

## Acciones (dentro de `permissions`)

`view` · `send` · `threads` · `reactions` · `attach` · `links` · `history` · `manage` · `mention`

- Sin prefijo = **permitir**.
- Prefijo `-` = **denegar** (ej. `-send`).
- Ausente = **heredar**.

## `permissions` — lista editable en Obsidian

Es una **lista de textos**, un ítem por rol, con el formato `Rol: action action`:

> permissions:
> - "@everyone: view -send"
> - "Moderator: view send manage threads"

- El **nombre del rol** debe ser el real de tu Discord (ej. `Moderador` si así se
  llama tu rol). `@everyone` = todos. Un rol que no exista solo genera un aviso.

## Cuerpo → mensajes

El cuerpo (debajo del frontmatter) se parte en **bloques separados por una línea `---`**.
Cada bloque es **un mensaje editable**. Una URL de imagen `![](url)` se auto-embebe.
Borrar un bloque no borra el mensaje: lo deja en blanco.
