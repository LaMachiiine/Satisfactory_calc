"""Débit d'extraction d'un gisement (§5bis.3).

`débit_max = base_pureté × tier × (clock/100) × (2 si Somersloop)`, où base_pureté
est le débit du Mineur Mk.1 (impur 30 / normal 60 / pur 120) et tier le
multiplicateur de foreuse (Mk.1 ×1, Mk.2 ×2, Mk.3 ×4). Plafonnable par le tapis.
"""

from __future__ import annotations

from ..data.game_constants import MINER_BASE_RATE, MINER_TIER_MULT
from .state import NodeState


def extraction_rate(
    purity: str,
    tier: int = 1,
    clock: float = 250.0,
    somersloop: bool = False,
    belt_capacity: float | None = None,
) -> float:
    """Débit max d'un gisement (objets/min). `clock` en % (défaut 250 = overclock max).

    Sans `belt_capacity` : débit brut (le distributeur gérera les lignes parallèles
    si le débit dépasse la capacité d'un tapis).
    """
    rate = (
        MINER_BASE_RATE[purity]
        * MINER_TIER_MULT[tier]
        * (clock / 100.0)
        * (2.0 if somersloop else 1.0)
    )
    if belt_capacity is not None:
        rate = min(rate, belt_capacity)
    return rate


def node_extraction_rate(node, state: NodeState, belt_capacity: float | None = None) -> float:
    """Débit d'un gisement selon son type (`node` / `well` / `geyser`).

    - `node` : foreuse Mk.1-3 + horloge + Somersloop (modèle complet).
    - `well` : puits de ressource — extracteurs uniformes (pas de tier Mk ni de
      Somersloop), seul l'overclock du pressuriseur joue → base pureté × horloge.
    - `geyser` : énergie géothermique, aucune ressource extraite → 0.
    """
    if node.kind == "geyser":
        return 0.0
    tier = 1 if node.kind == "well" else state.miner_tier
    somersloop = False if node.kind == "well" else state.somersloop
    return extraction_rate(node.purity, tier, state.clock, somersloop, belt_capacity)


def available_caps(
    nodes, states: dict[str, NodeState], belt_capacity: float | None = None
) -> dict[str, float]:
    """Plafond d'entrée par ressource = Σ débit_max des gisements **disponibles** (§5bis.4).

    Branche directement sur `solve_max_output(..., available=...)` ou les bornes du
    mode direct. Les gisements occupés (`available=False`) et les geysers (énergie,
    débit nul) sont exclus.
    """
    caps: dict[str, float] = {}
    for node in nodes:
        st = states.get(node.id) or NodeState()
        if not st.available:
            continue
        rate = node_extraction_rate(node, st, belt_capacity)
        if rate <= 0:
            continue
        caps[node.resource] = caps.get(node.resource, 0.0) + rate
    return caps
