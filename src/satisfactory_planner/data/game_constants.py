"""Constantes de jeu (§10 de la spec). Non présentes dans Docs.json."""

from __future__ import annotations

from ..model.entities import Belt

# Tapis Mk.1 -> Mk.6 (objets/min)
BELTS: list[Belt] = [
    Belt(tier=1, capacity_per_min=60),
    Belt(tier=2, capacity_per_min=120),
    Belt(tier=3, capacity_per_min=270),
    Belt(tier=4, capacity_per_min=480),
    Belt(tier=5, capacity_per_min=780),
    Belt(tier=6, capacity_per_min=1200),
]

# Pipelines Mk.1 / Mk.2 (m³/min)
PIPELINES: dict[int, float] = {1: 300.0, 2: 600.0}

# Surcadençage
PRODUCTION_POWER_EXPONENT = 1.321928  # bâtiments de production
GENERATOR_POWER_EXPONENT = 1.0  # générateurs : linéaire
MAX_CLOCK = 2.5  # 250 %, 3 Power Shards

# Somersloop : ressource finie du monde (collectible)
SOMERSLOOP_TOTAL = 106
SOMERSLOOP_MAX_AMP = 2.0  # multiplicateur de sortie max

# Extraction des gisements (§5bis.3) — débit de base du Mineur Mk.1 par pureté.
MINER_BASE_RATE: dict[str, float] = {"impure": 30.0, "normal": 60.0, "pure": 120.0}
MINER_TIER_MULT: dict[int, float] = {1: 1.0, 2: 2.0, 3: 4.0}  # Mk.1/Mk.2/Mk.3

# Conversion des fluides dans Docs.json : amounts stockés en m³ * 1000
FLUID_SCALE = 1000.0


def belt_for_rate(rate_per_min: float) -> Belt | None:
    """Retourne le tier de tapis le moins cher dont la capacité >= débit, ou None."""
    for belt in BELTS:
        if belt.capacity_per_min >= rate_per_min:
            return belt
    return None
