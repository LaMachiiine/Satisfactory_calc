"""Construction des sources d'approvisionnement depuis les gisements (§5ter.2)."""

from __future__ import annotations

from collections.abc import Iterable

from ..nodes.extraction import node_extraction_rate
from ..nodes.state import NodeState
from .locate import Source


def build_sources(
    nodes, states: dict[str, NodeState], items_needed: Iterable[str],
    *, belt_capacity: float | None = None, custom_sources=None,
) -> list[Source]:
    """Sources = gisements **disponibles** produisant l'un des `items_needed`.

    Capacité = débit max d'extraction (`node_extraction_rate`). Les gisements
    occupés ou à débit nul (geysers) sont exclus. `custom_sources` (sorties d'usine
    posées à la main) sont ajoutées pour les items demandés (`kind="factory_output"`).
    """
    wanted = set(items_needed)
    out: list[Source] = []
    for node in nodes:
        if node.resource not in wanted:
            continue
        st = states.get(node.id) or NodeState()
        if not st.available:
            continue
        rate = node_extraction_rate(node, st, belt_capacity)
        if rate <= 0:
            continue
        out.append(Source(
            item=node.resource, x=node.x, y=node.y,
            capacity_per_min=rate, kind="node", id=node.id,
        ))

    for cs in (custom_sources or []):
        if cs.item not in wanted or cs.rate_per_min <= 0:
            continue
        out.append(Source(
            item=cs.item, x=cs.x, y=cs.y,
            capacity_per_min=cs.rate_per_min, kind="factory_output", id=cs.id,
        ))
    return out
