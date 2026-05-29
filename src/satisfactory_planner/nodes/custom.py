"""Sources personnalisées (sorties d'usine) posées sur la carte (§5ter).

Persistées par projet dans un JSON (comme `nodes_state.json`). Une source déclare
qu'un item est disponible à un débit donné, à une position monde — utilisable comme
entrée du solveur et comme source de localisation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

DEFAULT_CUSTOM_PATH = "custom_sources.json"


class CustomSource(BaseModel):
    """Une source d'item manufacturé posée à la main sur la carte."""

    id: str
    item: str  # clé d'item, ex. "Desc_Plastic_C"
    rate_per_min: float
    x: float  # coords monde (cm), comme les gisements
    y: float
    label: str = ""


def load_custom_sources(path: str | Path) -> list[CustomSource]:
    """Charge la liste des sources (vide si le fichier n'existe pas)."""
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [CustomSource(**cfg) for cfg in data]


def save_custom_sources(sources: list[CustomSource], path: str | Path) -> None:
    """Sérialise la liste (dernier-écrit-gagne)."""
    data = [s.model_dump() for s in sources]
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_id(sources: list[CustomSource], item: str) -> str:
    prefix = f"cs_{item}_"
    n = 1 + max(
        (int(s.id[len(prefix):]) for s in sources
         if s.id.startswith(prefix) and s.id[len(prefix):].isdigit()),
        default=0,
    )
    return f"{prefix}{n}"


def add_source(sources: list[CustomSource], item: str, rate: float,
               x: float, y: float, label: str = "") -> list[CustomSource]:
    """Renvoie une nouvelle liste avec une source ajoutée (id généré, stable)."""
    new = CustomSource(
        id=_next_id(sources, item), item=item, rate_per_min=rate, x=x, y=y, label=label
    )
    return [*sources, new]


def remove_source(sources: list[CustomSource], source_id: str) -> list[CustomSource]:
    """Renvoie une nouvelle liste sans la source d'id `source_id`."""
    return [s for s in sources if s.id != source_id]
