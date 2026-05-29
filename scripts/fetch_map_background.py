"""Récupère le fond de carte du jeu depuis satisfactory-calculator (SCIM) et
l'assemble en une seule image carrée -> `data/map_background.jpg`.

SCIM sert des tuiles Leaflet (CRS.Simple) couvrant exactement les **bornes jouables**
West=-324698.83, East=425301.83, North=-375000, South=+375000 (cm). On télécharge
toute la grille à un zoom donné et on la recolle (tuile (x,y) -> pixel (x·256, y·256),
x vers l'est, y vers le sud, y=0 au nord). Le fond est donc nord en haut, ouest à
gauche, sans marge ni artéfact (contrairement à l'image composite LancelotP).

    uv run python scripts/fetch_map_background.py            # gameLayer, zoom 4
    uv run python scripts/fetch_map_background.py realistic 5
"""

from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image

CDN = "https://static.satisfactory-calculator.com/imgMap"
BUILD = "Stable"
TILE = 256
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://satisfactory-calculator.com/"}
DATA = Path(__file__).resolve().parent.parent / "data"


def _tile(layer: str, z: int, x: int, y: int) -> Image.Image | None:
    url = f"{CDN}/{layer}/{BUILD}/{z}/{x}/{y}.png"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except urllib.error.HTTPError:
        return None


def _grid_extent(layer: str, z: int) -> tuple[int, int]:
    """Nombre de colonnes/lignes (la grille est un rectangle dense depuis (0,0))."""
    cols = 0
    while _tile(layer, z, cols, 0) is not None:
        cols += 1
    rows = 0
    while _tile(layer, z, 0, rows) is not None:
        rows += 1
    return cols, rows


def fetch(layer: str = "gameLayer", z: int = 4, max_px: int = 2048) -> None:
    cols, rows = _grid_extent(layer, z)
    print(f"{layer} z{z}: grille {cols}×{rows} tuiles")
    canvas = Image.new("RGB", (cols * TILE, rows * TILE), (60, 60, 60))
    got = 0
    for x in range(cols):
        for y in range(rows):
            t = _tile(layer, z, x, y)
            if t is not None:
                canvas.paste(t, (x * TILE, y * TILE))
                got += 1
    print(f"{got}/{cols * rows} tuiles assemblées ({canvas.size[0]}×{canvas.size[1]} px)")
    if max(canvas.size) > max_px:
        scale = max_px / max(canvas.size)
        canvas = canvas.resize(
            (round(canvas.size[0] * scale), round(canvas.size[1] * scale)), Image.LANCZOS
        )
    out = DATA / "map_background.jpg"
    canvas.save(out, quality=85)
    print(f"-> {out} ({canvas.size[0]}×{canvas.size[1]})")


if __name__ == "__main__":
    want_real = len(sys.argv) > 1 and sys.argv[1].startswith("real")
    layer = "realisticLayer" if want_real else "gameLayer"
    zoom = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    fetch(layer, zoom)
