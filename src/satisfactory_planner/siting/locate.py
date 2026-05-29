"""Localisation d'usine : sélection sous capacité + raffinement Weber (§5ter).

Décorrélé du LP : on reçoit une **demande** (item → /min) et des **sources**
(gisements), on choisit pour chaque item les sources les plus proches couvrant le
débit, et on place l'usine à la médiane géométrique pondérée par les flux routés.
Itéré façon Lloyd ; relancé depuis plusieurs amorces → alternatives classées.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .weber import weighted_geometric_median

Point = tuple[float, float]


@dataclass
class Source:
    """Une source d'approvisionnement (gisement, sortie d'usine, pin manuel)."""

    item: str
    x: float
    y: float
    capacity_per_min: float
    kind: str = "node"  # "node" | "factory_output" | "manual_input"
    id: str = ""


@dataclass
class Pick:
    """Une source retenue : flux routé (/min) et distance à l'usine (m)."""

    source: Source
    flow: float
    dist_m: float


@dataclass
class SitingResult:
    """Site retenu, sources routées, coût de transport et pénuries éventuelles."""

    site: Point
    picks: list[Pick] = field(default_factory=list)
    cost: float = 0.0  # Σ flux × distance(m)
    shortfalls: dict[str, float] = field(default_factory=dict)  # item -> /min manquant


def _dist_m(site: Point, s: Source) -> float:
    return math.hypot(site[0] - s.x, site[1] - s.y) / 100.0  # cm -> m


def _select(site: Point, demand: dict[str, float],
            by_item: dict[str, list[Source]]) -> tuple[list[Pick], dict[str, float]]:
    """Glouton : pour chaque item, sources les plus proches jusqu'à couvrir le débit."""
    picks: list[Pick] = []
    shortfalls: dict[str, float] = {}
    for item, need in demand.items():
        srcs = sorted(by_item.get(item, []), key=lambda s: _dist_m(site, s))
        remaining = need
        for s in srcs:
            if remaining <= 1e-9:
                break
            take = min(s.capacity_per_min, remaining)
            picks.append(Pick(s, round(take, 6), _dist_m(site, s)))
            remaining -= take
        if remaining > 1e-6:
            shortfalls[item] = round(remaining, 6)
    return picks, shortfalls


def _cost(picks: list[Pick]) -> float:
    return round(sum(p.flow * p.dist_m for p in picks), 6)


def _refine(seed: Point, demand: dict[str, float],
            by_item: dict[str, list[Source]], max_iter: int) -> SitingResult:
    """Lloyd : alterne sélection ↔ médiane de Weber jusqu'à stabilité."""
    site = seed
    for _ in range(max_iter):
        picks, _ = _select(site, demand, by_item)
        if not picks:
            break
        pts = [(p.source.x, p.source.y) for p in picks]
        weights = [p.flow for p in picks]
        new = weighted_geometric_median(pts, weights)
        if math.hypot(new[0] - site[0], new[1] - site[1]) <= 1.0:
            site = new
            break
        site = new
    picks, shortfalls = _select(site, demand, by_item)
    return SitingResult(site=site, picks=picks, cost=_cost(picks), shortfalls=shortfalls)


def locate_factory(demand: dict[str, float], sources: list[Source],
                   *, n_alternatives: int = 3, max_iter: int = 50) -> list[SitingResult]:
    """Sites candidats classés par coût croissant (meilleur en tête).

    `demand` : item → /min requis. `sources` : gisements disponibles (tous items).
    Amorces : positions des sources + barycentre pondéré → optima locaux distincts.
    """
    demand = {k: v for k, v in demand.items() if v > 1e-9}
    if not demand or not sources:
        return []
    by_item: dict[str, list[Source]] = {}
    for s in sources:
        by_item.setdefault(s.item, []).append(s)

    seeds: list[Point] = [(s.x, s.y) for s in sources]
    wsum = sum(s.capacity_per_min for s in sources) or 1.0
    seeds.append((
        sum(s.x * s.capacity_per_min for s in sources) / wsum,
        sum(s.y * s.capacity_per_min for s in sources) / wsum,
    ))

    results = [_refine(seed, demand, by_item, max_iter) for seed in seeds]

    # Déduplication par site (grille ~1 km) en gardant le coût le plus bas.
    best: dict[tuple[int, int], SitingResult] = {}
    for r in results:
        key = (round(r.site[0] / 1000.0), round(r.site[1] / 1000.0))
        if key not in best or r.cost < best[key].cost:
            best[key] = r
    ranked = sorted(best.values(), key=lambda r: r.cost)
    return ranked[:n_alternatives]
