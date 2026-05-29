"""Données statiques des gisements (§5bis.1).

`data/nodes.json` (positions, type, pureté, forme) est intégré au projet — généré
une fois depuis une donnée communautaire (satisfactory-calculator MapInfo.json).
Il n'est jamais modifié à l'exécution ; la disponibilité vit dans `state.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

DEFAULT_NODES_PATH = "data/nodes.json"


class ResourceNode(BaseModel):
    """Un gisement du monde (fixe, indépendant de la partie)."""

    id: str  # identifiant stable du gisement
    resource: str  # item_key extrait (ex. "Desc_OreIron_C")
    purity: str  # "impure" | "normal" | "pure" (ou "unknown" pour un geyser)
    form: str  # "solid" | "liquid" | "gas" | "geyser"
    kind: str = "node"  # "node" (foreuse) | "well" (puits) | "geyser" (énergie)
    core: str | None = None  # puits : identifiant du pressuriseur (Fracking Core)
    x: float
    y: float
    z: float


def load_nodes(path: str | Path = DEFAULT_NODES_PATH) -> list[ResourceNode]:
    """Charge les gisements depuis `nodes.json` (tableau JSON)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ResourceNode(**entry) for entry in data]
