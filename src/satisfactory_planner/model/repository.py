"""Dépôt de recettes : chargement, cache et filtrage des alternatives."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .entities import Item, Machine, Recipe


@dataclass
class Repository:
    """Catalogue d'items/recettes/machines + ensemble de recettes activées.

    Une recette « activée » est candidate pour le solveur. Par défaut, toutes
    les recettes standard sont activées ; les alternatives le sont selon le
    paramètre `enable_alternates` ou via `with_recipes_enabled`.
    """

    items: dict[str, Item] = field(default_factory=dict)
    recipes: dict[str, Recipe] = field(default_factory=dict)
    machines: dict[str, Machine] = field(default_factory=dict)
    game_version: str = ""
    enabled: set[str] = field(default_factory=set)

    # --- Construction -----------------------------------------------------

    @classmethod
    def from_docs(
        cls, docs_path: str | Path, enable_alternates: bool = True
    ) -> Repository:
        """Construit le dépôt en parsant un Docs.json."""
        from ..data.docs_parser import parse_docs

        parsed = parse_docs(docs_path)
        repo = cls(
            items=parsed.items,
            recipes=parsed.recipes,
            machines=parsed.machines,
            game_version=parsed.game_version,
        )
        repo.enabled = repo._default_enabled(enable_alternates)
        return repo

    @classmethod
    def from_cache(cls, cache_path: str | Path) -> Repository:
        """Recharge un dépôt depuis un cache JSON normalisé (recipes.json)."""
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        repo = cls(
            items={k: Item(**v) for k, v in data["items"].items()},
            recipes={k: Recipe(**v) for k, v in data["recipes"].items()},
            machines={k: Machine(**v) for k, v in data["machines"].items()},
            game_version=data.get("game_version", ""),
        )
        repo.enabled = set(data.get("enabled", repo._default_enabled(True)))
        return repo

    def save_cache(self, cache_path: str | Path) -> None:
        """Sérialise le dépôt dans un cache JSON normalisé."""
        data = {
            "game_version": self.game_version,
            "items": {k: v.model_dump() for k, v in self.items.items()},
            "recipes": {k: v.model_dump() for k, v in self.recipes.items()},
            "machines": {k: v.model_dump() for k, v in self.machines.items()},
            "enabled": sorted(self.enabled),
        }
        Path(cache_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- Filtrage ---------------------------------------------------------

    def _default_enabled(self, enable_alternates: bool) -> set[str]:
        return {
            key
            for key, r in self.recipes.items()
            if enable_alternates or not r.is_alternate
        }

    def with_recipes_enabled(self, keys: list[str]) -> Repository:
        """Nouveau dépôt activant les recettes standard + les `keys` données."""
        enabled = self._default_enabled(enable_alternates=False) | set(keys)
        return Repository(
            items=self.items,
            recipes=self.recipes,
            machines=self.machines,
            game_version=self.game_version,
            enabled=enabled,
        )

    def _crafts_raw(self, recipe: Recipe) -> bool:
        """Vrai si la sortie principale de la recette est une ressource brute.

        Les bruts s'extraient, ils ne se fabriquent pas (le Converter qui synthétise
        des minerais n'a pas de sens dans une planification) : ces recettes sont écartées.
        """
        if not recipe.outputs:
            return False
        main = max(recipe.outputs, key=lambda k: recipe.outputs[k])
        item = self.items.get(main)
        return bool(item and item.is_raw)

    # --- Accès -------------------------------------------------------------

    def enabled_recipes(self) -> list[Recipe]:
        """Recettes candidates pour le solveur (hors synthèse de bruts)."""
        out = []
        for key in self.enabled:
            recipe = self.recipes.get(key)
            if recipe is None or self._crafts_raw(recipe):
                continue
            out.append(recipe)
        return out

    def recipes_producing(self, item_key: str) -> list[Recipe]:
        """Recettes activées produisant `item_key`."""
        return [r for r in self.enabled_recipes() if item_key in r.outputs]

    def resolve_item(self, name_or_key: str) -> str:
        """Résout une clé exacte ou un nom affiché (insensible à la casse)."""
        if name_or_key in self.items:
            return name_or_key
        needle = name_or_key.casefold()
        for key, item in self.items.items():
            if item.name.casefold() == needle:
                return key
        raise KeyError(f"Item introuvable : {name_or_key!r}")
