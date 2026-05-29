"""Médiane géométrique pondérée — point de Weber via Weiszfeld (§5ter.4).

`P* = argmin_P Σ wᵢ·‖P − sᵢ‖` (distance euclidienne 2D). Itération de Weiszfeld
avec gestion du cas où l'itéré tombe **sur** un point de données (singularité).
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def weighted_geometric_median(
    points: list[Point], weights: list[float],
    *, tol: float = 1e-6, max_iter: int = 1000,
) -> Point:
    """Point minimisant la distance pondérée aux `points`. Robuste à la singularité."""
    if not points:
        raise ValueError("au moins un point requis")
    if len(points) == 1:
        return points[0]

    # Initialisation : barycentre pondéré.
    wsum = sum(weights) or 1.0
    x = sum(w * px for (px, _), w in zip(points, weights, strict=True)) / wsum
    y = sum(w * py for (_, py), w in zip(points, weights, strict=True)) / wsum

    for _ in range(max_iter):
        num_x = num_y = den = 0.0
        on_point = None
        for (px, py), w in zip(points, weights, strict=True):
            d = math.hypot(x - px, y - py)
            if d < 1e-12:  # l'itéré coïncide avec un point -> traiter à part
                on_point = (px, py, w)
                continue
            inv = w / d
            num_x += inv * px
            num_y += inv * py
            den += inv
        if den == 0.0:
            return (x, y)
        nx, ny = num_x / den, num_y / den
        if on_point is not None:
            # Variante de Weiszfeld (Vardi-Zhang) gérant la singularité : si le
            # « tirage » des autres points ne dépasse pas le poids du point courant,
            # l'optimum est ce point.
            px, py, w = on_point
            r = math.hypot(num_x - den * px, num_y - den * py)
            if r <= w:
                return (px, py)
            ratio = max(0.0, 1.0 - w / r)
            nx = px + ratio * (nx - px)
            ny = py + ratio * (ny - py)
        if math.hypot(nx - x, ny - y) <= tol:
            return (nx, ny)
        x, y = nx, ny
    return (x, y)
