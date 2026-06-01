"""Lectura del vault de Obsidian: cada `.md` describe un canal de Discord.

Un archivo tiene **frontmatter** YAML (las "properties" de Obsidian) con la
config del canal (nombre, categoría, permisos) y un **cuerpo** que se parte en
bloques separados por una línea `---`; cada bloque será un mensaje editable.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("mc-discord-bot")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Embeds de imagen: ![[archivo.png|alias]] (Obsidian) y ![alt](destino) (markdown).
_WIKILINK_IMG = re.compile(r"!\[\[([^\]]+?)\]\]")
_MD_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass
class Block:
    """Un bloque del cuerpo = un mensaje de Discord."""

    text: str                                  # texto (sin los embeds locales)
    images: list[Path] = field(default_factory=list)  # archivos locales a adjuntar


@dataclass
class ChannelDoc:
    """Un canal de Discord descrito por un archivo `.md` del vault."""

    name: str                                  # nombre del canal (#...)
    blocks: list[Block]                        # un mensaje por bloque
    category: str | None = None                # categoría de Discord
    topic: str | None = None                   # topic del canal
    access: str | None = None                  # preset de permisos
    permissions: dict[str, list[str]] = field(default_factory=dict)
    ignore: bool = False                       # frontmatter `ignore: true` -> no sincronizar
    key: str = ""                              # clave de estado (stem del archivo)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Separa el frontmatter YAML (entre los primeros `---`) del cuerpo."""
    if not text.startswith("---"):
        return {}, text
    # Quitar el primer "---" y buscar el cierre.
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        return {}, text
    front_raw = rest[:end]
    body = rest[end + 4 :]  # saltar "\n---"
    # El cierre puede llevar un salto de línea extra.
    if body.startswith("\n"):
        body = body[1:]
    meta = yaml.safe_load(front_raw) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def _split_blocks(body: str) -> list[str]:
    """Parte el cuerpo en bloques por líneas que son exactamente `---`."""
    blocks: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.strip() == "---":
            blocks.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    blocks.append("\n".join(current).strip())
    # Conservamos los bloques vacíos intermedios (mapean a slots blanqueados),
    # pero descartamos vacíos sobrantes al final.
    while blocks and blocks[-1] == "":
        blocks.pop()
    return blocks


def _coerce_actions(actions) -> list[str]:
    """Una lista de acciones puede venir como string ('view -send') o lista."""
    if isinstance(actions, str):
        return [a for a in re.split(r"[,\s]+", actions.strip()) if a]
    if isinstance(actions, (list, tuple)):
        return [str(a).strip() for a in actions if str(a).strip()]
    return []


def _normalize_permissions(raw) -> dict[str, list[str]]:
    """Normaliza `permissions` a `{role: [actions]}`.

    Forma recomendada (editable en las Properties de Obsidian): una **lista de
    textos** `"Role: action action"`:

        permissions:
          - "@everyone: view -send"
          - "Moderator: view send manage"

    También se acepta la forma anidada `{Role: [actions]}` por compatibilidad.
    """
    out: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for role, actions in raw.items():
            out[str(role)] = _coerce_actions(actions)
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if not isinstance(item, str) or ":" not in item:
                continue
            role, _, actions_str = item.partition(":")
            role = role.strip()
            if role:
                out[role] = _coerce_actions(actions_str)
    return out


def _index_images(root: Path) -> dict[str, Path]:
    """Mapa `nombre.png (lower) -> Path` de todas las imágenes del vault.

    Replica el comportamiento de Obsidian: un embed referencia la imagen por su
    nombre de archivo, sin importar en qué subcarpeta esté (ej. `Media/`).
    """
    idx: dict[str, Path] = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue  # .obsidian/, etc.
        idx.setdefault(p.name.lower(), p)
    return idx


def _resolve_image(target: str, images_index: dict[str, Path]) -> Path | None:
    name = Path(urllib.parse.unquote(target.strip())).name.lower()
    return images_index.get(name)


def _extract_images(text: str, images_index: dict[str, Path]) -> tuple[str, list[Path]]:
    """Saca los embeds de imagen LOCAL del texto y devuelve `(texto, [Paths])`.

    Las URLs remotas (`http(s)://…`) se dejan en el texto: Discord las auto-embebe.
    """
    found: list[Path] = []

    def _wikilink(m: re.Match) -> str:
        target = m.group(1).split("|", 1)[0]  # quita |alias o |tamaño
        p = _resolve_image(target, images_index)
        if p is None:
            log.warning("Imagen no encontrada en el vault: %r", target)
            return ""
        found.append(p)
        return ""

    def _md(m: re.Match) -> str:
        target = m.group(1).strip().split(" ", 1)[0]  # quita un "title" opcional
        if target.lower().startswith(("http://", "https://")):
            return m.group(0)  # remota -> dejar tal cual
        p = _resolve_image(target, images_index)
        if p is None:
            log.warning("Imagen no encontrada en el vault: %r", target)
            return ""
        found.append(p)
        return ""

    text = _WIKILINK_IMG.sub(_wikilink, text)
    text = _MD_IMG.sub(_md, text)
    return text.strip(), found


def _build_blocks(body: str, images_index: dict[str, Path]) -> list[Block]:
    blocks: list[Block] = []
    for raw in _split_blocks(body):
        text, images = _extract_images(raw, images_index)
        blocks.append(Block(text=text, images=images))
    return blocks


def parse_doc(path: Path, images_index: dict[str, Path] | None = None) -> ChannelDoc:
    """Parsea un único archivo `.md` en un `ChannelDoc`."""
    if images_index is None:
        images_index = {}
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    name = str(meta.get("channel") or path.stem)
    category = meta.get("category")
    topic = meta.get("topic")
    access = meta.get("access")
    return ChannelDoc(
        name=name,
        blocks=_build_blocks(body, images_index),
        category=str(category) if category else None,
        topic=str(topic) if topic else None,
        access=str(access) if access else None,
        permissions=_normalize_permissions(meta.get("permissions")),
        ignore=bool(meta.get("ignore", False)),
        key=path.stem,
    )


def load_docs(channels_dir: str | Path) -> list[ChannelDoc]:
    """Lee los `.md` del vault que SÍ son canales.

    Se ignoran: `.obsidian/` y ocultos, archivos cuyo nombre empieza con `_`
    (convención para notas que no son canales) y los que traen `ignore: true`
    en el frontmatter.
    """
    root = Path(channels_dir)
    if not root.is_dir():
        return []
    images_index = _index_images(root)
    docs: list[ChannelDoc] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue  # .obsidian/, themes, etc.
        if path.stem.startswith("_"):
            continue  # nota auxiliar, no es un canal
        # Chequeo barato de `ignore: true` antes de parsear el cuerpo (evita
        # procesar/avisar sobre ejemplos dentro de notas que el bot ignora).
        meta, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("ignore"):
            continue
        docs.append(parse_doc(path, images_index))
    return docs
