"""Lectura del vault de Obsidian: cada `.md` describe un canal de Discord.

Un archivo tiene **frontmatter** YAML (las "properties" de Obsidian) con la
config del canal (nombre, categoría, permisos) y un **cuerpo** que se parte en
bloques separados por una línea `---`; cada bloque será un mensaje editable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ChannelDoc:
    """Un canal de Discord descrito por un archivo `.md` del vault."""

    name: str                                  # nombre del canal (#...)
    blocks: list[str]                          # un mensaje por bloque
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


def parse_doc(path: Path) -> ChannelDoc:
    """Parsea un único archivo `.md` en un `ChannelDoc`."""
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    name = str(meta.get("channel") or path.stem)
    category = meta.get("category")
    topic = meta.get("topic")
    access = meta.get("access")
    return ChannelDoc(
        name=name,
        blocks=_split_blocks(body),
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
    docs: list[ChannelDoc] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue  # .obsidian/, themes, etc.
        if path.stem.startswith("_"):
            continue  # nota auxiliar, no es un canal
        doc = parse_doc(path)
        if doc.ignore:
            continue  # frontmatter: ignore: true
        docs.append(doc)
    return docs
