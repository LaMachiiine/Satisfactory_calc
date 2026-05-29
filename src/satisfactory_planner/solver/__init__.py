"""Cœur d'optimisation LP/MILP (Phase 1+). Stubs pour l'instant.

Le choix du solveur (OR-Tools vs PuLP+CBC) est volontairement repoussé à la
Phase 1 ; aucune dépendance solveur n'est encore installée.
"""

from .modes import OBJECTIVES, solve_forward, solve_max_output
from .somersloop import allocate_somersloops

__all__ = ["OBJECTIVES", "solve_forward", "solve_max_output", "allocate_somersloops"]
