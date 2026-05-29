"""Façade publique (§7). Réexporte les points d'entrée stables.

Le cœur (model + solver + distribution) n'a aucune dépendance UI ; cette façade
est le point d'entrée unique pour les couches d'interface.
"""

from __future__ import annotations

from .distribution import build_distribution
from .model import Repository
from .solver import solve_forward, solve_max_output

__all__ = [
    "Repository",
    "solve_forward",
    "solve_max_output",
    "build_distribution",
]
