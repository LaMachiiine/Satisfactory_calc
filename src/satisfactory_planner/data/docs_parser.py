"""Parsing du Docs.json **format original du jeu** (`CommunityResources/Docs`).

Le fichier est un tableau JSON (souvent UTF-16) de groupes par classe native ;
chaque groupe a `NativeClass` (chemin complet) et `Classes` (liste d'objets aux
champs directs : `ClassName`, `mDisplayName`, ...). Les ingrédients/produits et
les bâtiments de production sont des **chaînes sérialisées** Unreal.

Notes de format :
- fluides : quantités stockées en m³ * 1000 -> divisées (FLUID_SCALE) ;
- recette retenue seulement si produite dans une machine connue (main / build
  gun / établi écartés) ;
- `is_alternate` : préfixe ClassName `Recipe_Alternate_` **ou** nom « Alternate: … » ;
- `somersloop_slots` lu depuis `mProductionShardSlotSize`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..model.entities import Item, Machine, Recipe
from .game_constants import FLUID_SCALE

_FLUID_FORMS = {"RF_LIQUID", "RF_GAS"}
_ALTERNATE_PREFIX = "Recipe_Alternate_"
_ITEM_AMOUNT_RE = re.compile(r'ItemClass="([^"]+)",Amount=([0-9.]+)')
_QUOTED_RE = re.compile(r'"([^"]+)"')


@dataclass
class ParsedDocs:
    """Résultat brut du parsing, indexé par `key`."""

    game_version: str
    items: dict[str, Item]
    recipes: dict[str, Recipe]
    machines: dict[str, Machine]


def _read_json(path: Path):
    """Lit le fichier en tolérant les encodages usuels (UTF-16 / UTF-8)."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Impossible de décoder {path} (encodage non reconnu)")


def _class_name(path: str) -> str:
    """Dernier segment d'un chemin Unreal : `....Desc_OreIron_C'` -> `Desc_OreIron_C`."""
    return path.rsplit(".", 1)[-1].rstrip("'\"")


def _form_is_fluid(props: dict) -> bool:
    return props.get("mForm", "").split("::")[-1] in _FLUID_FORMS


_STACK_SIZES = {
    "SS_ONE": 1, "SS_SMALL": 50, "SS_MEDIUM": 100, "SS_BIG": 200, "SS_HUGE": 500,
}


def _stack_size(props: dict) -> int:
    """Taille de pile depuis `mStackSize` (enum EStackSize), défaut 100."""
    token = props.get("mStackSize", "").split("::")[-1]
    return _STACK_SIZES.get(token, 100)


def _parse_stack(serialized: str, items: dict[str, Item]) -> dict[str, float]:
    """`((ItemClass="...Desc_X_C'",Amount=N),...)` -> `{item_key: qté}` (fluides /1000)."""
    out: dict[str, float] = {}
    for match in _ITEM_AMOUNT_RE.finditer(serialized or ""):
        key = _class_name(match.group(1))
        amount = float(match.group(2))
        item = items.get(key)
        if item is not None and item.is_fluid:
            amount /= FLUID_SCALE
        out[key] = amount
    return out


def _parse_produced_in(serialized: str) -> list[str]:
    """`("...Build_X.Build_X_C",...)` -> `["Build_X_C", ...]`."""
    return [_class_name(m.group(1)) for m in _QUOTED_RE.finditer(serialized or "")]


def parse_docs(path: str | Path) -> ParsedDocs:
    """Parse un Docs.json (format original) en entités normalisées."""
    groups = _read_json(Path(path))

    items: dict[str, Item] = {}
    machines: dict[str, Machine] = {}
    raw_recipes: list[dict] = []

    # 1re passe : items et machines (nécessaires pour résoudre les recettes).
    for group in groups:
        token = _class_name(group.get("NativeClass", ""))
        classes = group.get("Classes", [])

        if token == "FGRecipe":
            raw_recipes.extend(classes)
        elif token.startswith("FGBuildableManufacturer"):
            for c in classes:
                key = c["ClassName"]
                machines[key] = Machine(
                    key=key,
                    name=c.get("mDisplayName", key),
                    base_power_mw=float(c.get("mPowerConsumption", 0.0) or 0.0),
                    power_exponent=float(c.get("mPowerConsumptionExponent", 1.321928) or 1.321928),
                    production_boost_power_exponent=float(
                        c.get("mProductionBoostPowerConsumptionExponent", 2.0) or 2.0
                    ),
                    somersloop_slots=int(float(c.get("mProductionShardSlotSize", 0) or 0)),
                )
        else:
            is_raw_group = token == "FGResourceDescriptor"
            for c in classes:
                key = c.get("ClassName", "")
                if not key.startswith("Desc_"):
                    continue
                items[key] = Item(
                    key=key,
                    name=c.get("mDisplayName", key),
                    is_fluid=_form_is_fluid(c),
                    is_raw=is_raw_group,
                    stack_size=_stack_size(c),
                )

    # 2e passe : recettes (fluides et machines désormais connus).
    recipes: dict[str, Recipe] = {}
    for c in raw_recipes:
        key = c.get("ClassName", "")
        produced_in = _parse_produced_in(c.get("mProducedIn", ""))
        machine = next((m for m in produced_in if m in machines), None)
        if machine is None:
            continue  # non automatisable (main / build gun / établi)
        name = c.get("mDisplayName", key)
        recipes[key] = Recipe(
            key=key,
            name=name,
            machine=machine,
            duration_s=float(c.get("mManufactoringDuration", 0.0) or 0.0) or 1.0,
            inputs=_parse_stack(c.get("mIngredients", ""), items),
            outputs=_parse_stack(c.get("mProduct", ""), items),
            # Alternative : préfixe ClassName Recipe_Alternate_ OU nom affiché
            # « Alternate: … » (certaines, ex. Pure Aluminum Ingot en 1.1, n'ont pas
            # le préfixe de classe). Sinon elles seraient activées par défaut.
            is_alternate=key.startswith(_ALTERNATE_PREFIX) or name.startswith("Alternate"),
        )

    return ParsedDocs(
        game_version="", items=items, recipes=recipes, machines=machines
    )
