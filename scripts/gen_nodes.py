"""Régénère `data/nodes.json` depuis les sources communautaires.

Sources (déposées dans `data/`, voir README) :
- `MapInfo.json` (0xjc/SatisfactoryLP, format satisfactory-calculator) : onglets
  `resource_nodes` (gisements solides + pétrole) et `resource_wells` (azote, puits
  de pétrole, eau).
- `geysers.ts` (LancelotP/satisfactory-map) : 17 geysers (énergie géothermique,
  sans pureté dans la source).

Coordonnées monde du jeu (x, y, z) conservées telles quelles. Lancement :
    uv run python scripts/gen_nodes.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# type de puits MapInfo -> item réellement produit (l'item « well » n'existe pas).
WELL_RESOURCE = {
    "Desc_LiquidOilWell_C": "Desc_LiquidOil_C",  # puits de pétrole -> pétrole brut
    "Desc_NitrogenGas_C": "Desc_NitrogenGas_C",
    "Desc_Water_C": "Desc_Water_C",
}
# forme (transport) par item ; défaut solide.
FORM = {
    "Desc_LiquidOil_C": "liquid",
    "Desc_Water_C": "liquid",
    "Desc_NitrogenGas_C": "gas",
}


def _short(path_name: str) -> str:
    """Identifiant court depuis un pathName Unreal (dernier segment)."""
    return path_name.rsplit(".", 1)[-1]


def _resource_id(option: dict) -> str:
    return option.get("tabId") or option.get("type") or option.get("name")


def parse_mapinfo(map_info: dict) -> list[dict]:
    tabs = {
        t.get("tabId"): t
        for t in map_info["options"]
        if isinstance(t, dict) and t.get("tabId")
    }
    out: list[dict] = []

    for res in tabs.get("resource_nodes", {}).get("options", []):
        resource = _resource_id(res)
        if not resource or not resource.startswith("Desc_"):
            continue  # « Unknown nodes »
        for layer in res.get("options", []):
            for m in layer.get("markers", []):
                out.append({
                    "id": _short(m["pathName"]),
                    "resource": resource,
                    "purity": m.get("purity", layer.get("purity")),
                    "form": FORM.get(resource, "solid"),
                    "kind": "node",
                    "x": m["x"], "y": m["y"], "z": m["z"],
                })

    for res in tabs.get("resource_wells", {}).get("options", []):
        well_type = _resource_id(res)
        if well_type not in WELL_RESOURCE:
            continue  # « Unknown wells », geysers (traités à part) ...
        resource = WELL_RESOURCE[well_type]
        for layer in res.get("options", []):
            for m in layer.get("markers", []):
                out.append({
                    "id": _short(m["pathName"]),
                    "resource": resource,
                    "purity": m.get("purity", layer.get("purity")),
                    "form": FORM.get(resource, "liquid"),
                    "kind": "well",
                    "core": _short(m["core"]) if m.get("core") else None,
                    "x": m["x"], "y": m["y"], "z": m["z"],
                })
    return out


_GEYSER_OBJ = re.compile(
    r"x:\s*(-?[\d.]+),\s*y:\s*(-?[\d.]+),\s*z:\s*(-?[\d.]+),\s*originId:\s*\"([^\"]+)\"",
    re.S,
)


def parse_geysers(ts_source: str) -> list[dict]:
    out = []
    for x, y, z, origin in _GEYSER_OBJ.findall(ts_source):
        out.append({
            "id": origin,
            "resource": "Desc_Geyser_C",
            "purity": "unknown",  # non fourni par la source (énergie géothermique)
            "form": "geyser",
            "kind": "geyser",
            "x": float(x), "y": float(y), "z": float(z),
        })
    return out


def main() -> None:
    map_info = json.loads((DATA / "MapInfo.json").read_text(encoding="utf-8"))
    nodes = parse_mapinfo(map_info)
    nodes += parse_geysers((DATA / "geysers.ts").read_text(encoding="utf-8"))
    (DATA / "nodes.json").write_text(
        json.dumps(nodes, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    kinds: dict[str, int] = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    print(f"{len(nodes)} gisements écrits -> data/nodes.json")
    print("par type :", kinds)


if __name__ == "__main__":
    main()
