"""Sélection du mode de transport par liaison (§5quater.2–4).

Pour une liaison `(item, débit/min, distance m)` : débit unitaire de chaque mode,
nombre d'unités `ceil(débit/unitaire)`, faisabilité (fluide → pipeline/train) et
**coût** (score relatif). On classe les modes et on recommande le moins cher.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import (
    BELT_UNIT_RATE,
    DRONE_RT_BASE,
    DRONE_SLOTS,
    DRONE_SPEED,
    MODES,
    PIPE_UNIT_RATE,
    TRAIN_SPEED,
    TRAIN_TURN,
    TRUCK_SLOTS,
    TRUCK_SPEED,
    TRUCK_TURN,
    WAGON_FLUID,
    WAGON_SLOTS,
    ModeProfile,
)


@dataclass
class LinkOption:
    """Un mode évalué pour une liaison : faisabilité, débit unitaire, unités, coût."""

    mode: str
    name: str
    feasible: bool
    unit_rate: float   # débit /min par unité (tapis, wagon, drone, camion…)
    units: int
    cost: float
    unit_label: str    # libellé d'unité ("tapis Mk.6", "wagons", …)


def _round_trip_s(dist_m: float, speed: float, base_turn: float) -> float:
    return 2.0 * dist_m / speed + base_turn


def unit_rate(mode: str, stack_size: int, dist_m: float, is_fluid: bool = False) -> float:
    """Débit /min d'**une** unité du mode (objets/min, ou m³/min pour les fluides)."""
    if mode == "belt":
        return BELT_UNIT_RATE
    if mode == "pipe":
        return PIPE_UNIT_RATE
    if mode == "train":
        rt = _round_trip_s(dist_m, TRAIN_SPEED, TRAIN_TURN)
        # Wagon-citerne (1600 m³) pour les fluides, sinon 32 piles de solide.
        cap = WAGON_FLUID if is_fluid else WAGON_SLOTS * stack_size
        return cap * 60.0 / rt
    if mode == "truck":
        rt = _round_trip_s(dist_m, TRUCK_SPEED, TRUCK_TURN)
        return TRUCK_SLOTS * stack_size * 60.0 / rt
    if mode == "drone":
        rt = DRONE_RT_BASE + 2.0 * dist_m / DRONE_SPEED
        return DRONE_SLOTS * stack_size * 60.0 / rt
    raise ValueError(f"mode inconnu : {mode!r}")


_UNIT_LABEL = {"belt": "tapis Mk.6", "pipe": "pipeline Mk.2", "train": "wagons",
               "truck": "camions", "drone": "drones"}


def _feasible(profile: ModeProfile, is_fluid: bool) -> bool:
    return profile.fluid if is_fluid else profile.solid


def evaluate(item_is_fluid: bool, rate: float, dist_m: float,
             stack_size: int = 100) -> list[LinkOption]:
    """Évalue tous les modes pour une liaison, classés par coût (faisables d'abord)."""
    opts: list[LinkOption] = []
    for p in MODES:
        feasible = _feasible(p, item_is_fluid)
        ur = unit_rate(p.key, stack_size, dist_m, item_is_fluid)
        units = max(1, math.ceil(rate / ur)) if rate > 0 else 0
        # Infra continue (tapis/pipe) : la distance coûte ×nb de lignes parallèles ;
        # véhicules : voie/route posée une fois (distance ×1), unités via cost_per_unit.
        dist_cost = p.cost_per_m * dist_m * (units if p.continuous else 1)
        cost = p.setup + dist_cost + (p.cost_per_unit + p.complexity) * units
        opts.append(LinkOption(
            mode=p.key, name=p.name, feasible=feasible, unit_rate=round(ur, 3),
            units=units, cost=round(cost, 3), unit_label=_UNIT_LABEL[p.key],
        ))
    # Faisables d'abord, puis coût croissant.
    opts.sort(key=lambda o: (not o.feasible, o.cost))
    return opts


def recommend(item_is_fluid: bool, rate: float, dist_m: float,
              stack_size: int = 100) -> LinkOption:
    """Meilleur mode (faisable, coût minimal) pour une liaison."""
    return evaluate(item_is_fluid, rate, dist_m, stack_size)[0]


def decision_grid(distances_m: list[float], rates: list[float],
                  *, item_is_fluid: bool = False, stack_size: int = 100) -> list[list[str]]:
    """Mode gagnant par cellule (distance × débit) pour la carte de décision."""
    return [
        [recommend(item_is_fluid, rate, d, stack_size).mode for d in distances_m]
        for rate in rates
    ]
