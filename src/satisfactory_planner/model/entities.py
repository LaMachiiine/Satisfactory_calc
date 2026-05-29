"""Entités normalisées du jeu (schéma §3.2 de la spec)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Item(BaseModel):
    """Un item du jeu (part, fluide ou ressource brute)."""

    key: str  # identifiant stable, ex. "Desc_IronIngot_C"
    name: str  # nom affiché localisé
    is_fluid: bool = False
    is_raw: bool = False  # extrait d'un gisement (minerai, pétrole, eau...)
    stack_size: int = 100  # taille de pile (slots véhicules/trains ; transport §5quater)


class Recipe(BaseModel):
    """Une recette : entrées/sorties par cycle dans une machine donnée."""

    key: str
    name: str
    machine: str  # ex. "Build_SmelterMk1_C"
    duration_s: float  # durée d'un cycle à 100 %
    inputs: dict[str, float] = Field(default_factory=dict)  # item_key -> qté/cycle
    outputs: dict[str, float] = Field(default_factory=dict)  # item_key -> qté/cycle
    is_alternate: bool = False

    def rate_per_min(self, item_key: str) -> float:
        """Débit/min à 100 % pour `item_key` (sortie prioritaire sur entrée)."""
        if item_key in self.outputs:
            qty = self.outputs[item_key]
        elif item_key in self.inputs:
            qty = self.inputs[item_key]
        else:
            raise KeyError(f"{item_key} absent de la recette {self.key}")
        return qty * 60.0 / self.duration_s


class Machine(BaseModel):
    """Un bâtiment de production."""

    key: str
    name: str
    base_power_mw: float
    power_exponent: float = 1.321928  # exposant surcadençage des bâtiments de prod
    # exposant puissance amplification Somersloop (Docs.json ; =2 en 1.0/1.1)
    production_boost_power_exponent: float = 2.0
    somersloop_slots: int = 0


class Belt(BaseModel):
    """Un tier de tapis convoyeur."""

    tier: int  # 1..6
    capacity_per_min: float  # 60, 120, 270, 480, 780, 1200
