"""Recherche de clusters & localisation d'usine (Phase 6, §5ter)."""

from .locate import Pick, SitingResult, Source, locate_factory
from .sources import build_sources
from .weber import weighted_geometric_median

__all__ = [
    "Source", "Pick", "SitingResult", "locate_factory", "build_sources",
    "weighted_geometric_median",
]
