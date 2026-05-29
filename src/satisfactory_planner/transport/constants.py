"""Profils & constantes des modes de transport (§5quater.1, §5quater.6).

Valeurs **approximatives, calibrables** (vitesses, slots, temps d'animation, coûts).
Le coût est un *score* relatif sans unité : `setup + coût/m × distance +
coût/unité × n + complexité × n`. À affiner ; il sert à ordonner les modes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Débit unitaire des modes « infrastructure » (objets ou m³/min par ligne).
BELT_UNIT_RATE = 1200.0   # tapis Mk.6 (meilleur tier)
PIPE_UNIT_RATE = 600.0    # pipeline Mk.2 (fluides)

# Véhicules : slots transportés et cinématique (m/s, secondes).
WAGON_SLOTS = 32          # 1 wagon = 32 piles (solides)
WAGON_FLUID = 1600.0      # 1 wagon-citerne = 1600 m³ (fluides, sans empaquetage)
DRONE_SLOTS = 9
TRUCK_SLOTS = 48
TRAIN_SPEED, TRAIN_TURN = 30.0, 60.0     # ~108 km/h + arrêts/chargement
TRUCK_SPEED, TRUCK_TURN = 20.0, 20.0
DRONE_SPEED, DRONE_RT_BASE = 28.0, 102.0  # 51 s décollage + 51 s atterrissage


@dataclass(frozen=True)
class ModeProfile:
    """Un mode de transport : faisabilité, débit unitaire, coût (score relatif)."""

    key: str
    name: str
    solid: bool          # transporte des objets solides
    fluid: bool          # transporte des fluides (sans empaquetage)
    setup: float         # coût fixe (stations/ports, 2 extrémités)
    cost_per_m: float    # coût d'infra le long du trajet (×lignes si continuous)
    cost_per_unit: float # coût par véhicule/ligne
    complexity: float    # pénalité de gestion par unité (micro-management)
    continuous: bool = False  # infra continue (tapis/pipe) : coût distance ×nb lignes


# Calibrage : infra continue (tapis/pipe) → coût distance ×lignes (N lignes parallèles
# coûtent N×) ; véhicules (camion/train/drone) → voie posée une fois, débit/coût par
# unité. Donne : tapis (court), camion (moyen), train (long + gros débit), drone
# (long + faible débit). Valeurs relatives, ajustables.
MODES: tuple[ModeProfile, ...] = (
    ModeProfile("belt", "Tapis", solid=True, fluid=False, continuous=True,
                setup=0.0, cost_per_m=1.5, cost_per_unit=0.0, complexity=15.0),
    ModeProfile("pipe", "Pipeline", solid=False, fluid=True, continuous=True,
                setup=50.0, cost_per_m=2.0, cost_per_unit=0.0, complexity=15.0),
    ModeProfile("truck", "Camion", solid=True, fluid=False,
                setup=400.0, cost_per_m=0.6, cost_per_unit=300.0, complexity=80.0),
    ModeProfile("train", "Train", solid=True, fluid=True,  # wagons-citernes (1600 m³)
                setup=2500.0, cost_per_m=0.4, cost_per_unit=200.0, complexity=30.0),
    ModeProfile("drone", "Drone", solid=True, fluid=False,
                setup=700.0, cost_per_m=0.1, cost_per_unit=600.0, complexity=50.0),
)

MODES_BY_KEY = {m.key: m for m in MODES}
