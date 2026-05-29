"""État de disponibilité des gisements par projet (§5bis.2).

`nodes.json` (statique) n'est pas modifié ; un fichier séparé `nodes_state.json`
porte la configuration par gisement (disponible, foreuse, horloge, Somersloop),
persistée immédiatement (dernier-écrit-gagne).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class NodeState(BaseModel):
    """Configuration d'un gisement (par défaut : dispo, Mk.1, overclock max 250 %)."""

    available: bool = True  # False = occupé / réservé, exclu du solveur
    miner_tier: int = 1  # 1..3 (impacte le débit max)
    clock: float = 250.0  # 1..250 (%) — overclock max par défaut
    somersloop: bool = False


def load_states(path: str | Path) -> dict[str, NodeState]:
    """Charge les états par id de gisement (dict vide si le fichier n'existe pas)."""
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {node_id: NodeState(**cfg) for node_id, cfg in data.items()}


def save_states(states: dict[str, NodeState], path: str | Path) -> None:
    """Sérialise les états (dernier-écrit-gagne)."""
    data = {node_id: st.model_dump() for node_id, st in states.items()}
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_state(states: dict[str, NodeState], node_id: str) -> NodeState:
    """État d'un gisement, ou l'état par défaut s'il n'est pas configuré."""
    return states.get(node_id, NodeState())
