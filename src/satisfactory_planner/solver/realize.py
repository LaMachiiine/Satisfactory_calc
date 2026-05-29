"""Réalisation : machines entières, horloge, puissance (§4.5).

Trois stratégies pour rendre le ratio continu `x` constructible :
- `uniform`  : ceil(x) machines, toutes à x/ceil(x) (min-puissance, sans Power Shard) ;
- `max100`   : floor(x) machines à 100 % + 1 au reliquat (plus de machines pleines) ;
- `overclock`: le moins de machines possible en surcadençant jusqu'à 250 %.

Puissance : `Σ nb * base * (horloge/100) ** exposant`.
"""

from __future__ import annotations

import math

from ..model.entities import Machine, Recipe
from .result import PlanStep


def _main_output(recipe: Recipe) -> str:
    """Item principal : la sortie de plus forte quantité par cycle."""
    return max(recipe.outputs, key=lambda k: recipe.outputs[k])


def _clock_groups(x: float, strategy: str, max_clock: float) -> list[tuple[int, float]]:
    """Découpe `x` en groupes (nombre de machines, horloge %)."""
    if strategy == "uniform":
        n = max(math.ceil(x - 1e-9), 1)
        return [(n, x / n * 100.0)]
    if strategy == "max100":
        full = math.floor(x + 1e-9)
        frac = x - full
        groups: list[tuple[int, float]] = []
        if full > 0:
            groups.append((full, 100.0))
        if frac > 1e-9:
            groups.append((1, frac * 100.0))
        return groups or [(1, x * 100.0)]
    if strategy == "overclock":
        n = max(math.ceil(x / max_clock - 1e-9), 1)
        return [(n, x / n * 100.0)]
    raise ValueError(f"stratégie de réalisation inconnue : {strategy!r}")


def realize_step(
    recipe: Recipe,
    x: float,
    machines: dict[str, Machine],
    strategy: str = "uniform",
    max_clock: float = 2.5,
) -> PlanStep:
    """Convertit le ratio continu `x` en machines entières + horloge + puissance."""
    machine = machines.get(recipe.machine)
    base = machine.base_power_mw if machine else 0.0
    exponent = machine.power_exponent if machine else 1.321928

    groups = _clock_groups(x, strategy, max_clock)
    n = sum(c for c, _ in groups)
    power = sum(c * base * (clk / 100.0) ** exponent for c, clk in groups)
    # Horloge représentative : la valeur unique, ou la dominante (par nombre).
    rep_clock = groups[0][1] if len(groups) == 1 else max(groups, key=lambda g: g[0])[1]

    main = _main_output(recipe)
    output_rate = x * recipe.rate_per_min(main)
    return PlanStep(
        recipe=recipe,
        x=x,
        machines=n,
        clock=round(rep_clock, 6),
        power_mw=round(power, 6),
        main_output=main,
        output_rate=round(output_rate, 6),
        per_machine_rate=round(output_rate / n, 6) if n else 0.0,
        clock_groups=[(c, round(clk, 6)) for c, clk in groups],
    )
