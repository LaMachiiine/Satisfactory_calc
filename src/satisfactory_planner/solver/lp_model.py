"""Construction du programme linéaire (§4.1–4.3).

Variables continues `x_r >= 0` (machines-équivalent à 100 %), bilan net par item
`net_i = Σ_r x_r * rate(r, i)`, et contraintes selon le rôle de l'item.
"""

from __future__ import annotations

from dataclasses import dataclass

from ortools.linear_solver import pywraplp

from ..model.entities import Item, Machine, Recipe

# Bruts **illimités/gratuits** : disponibles partout en quantité illimitée et hors
# objectif min_raw (l'eau du jeu). Ils restent recyclés (le bilan net réinjecte les
# sous-produits), mais ne contraignent ni ne pénalisent jamais le plan.
FREE_RAWS = frozenset({"Desc_Water_C"})


def rate(recipe: Recipe, item_key: str) -> float:
    """Débit net/min de `item_key` pour une machine de `recipe` à 100 %."""
    out = recipe.outputs.get(item_key, 0.0)
    inp = recipe.inputs.get(item_key, 0.0)
    return (out - inp) * 60.0 / recipe.duration_s


@dataclass
class LpModel:
    """Le LP construit + ce qu'il faut pour exploiter la solution."""

    solver: pywraplp.Solver
    x: dict[str, pywraplp.Variable]  # recipe_key -> variable
    coefs: dict[str, list[tuple[float, str]]]  # item_key -> [(coef, recipe_key)]
    raw_keys: list[str]
    item_keys: set[str]

    def net_value(self, item_key: str) -> float:
        """Évalue net_i sur la solution courante (0 si aucune recette ne le touche)."""
        return sum(c * self.x[rk].solution_value() for c, rk in self.coefs.get(item_key, []))


def build_forward(
    recipes: list[Recipe],
    items: dict[str, Item],
    machines: dict[str, Machine],
    targets: dict[str, float],
    available: dict[str, float] | None = None,
    objective: str = "min_raw",
) -> LpModel:
    """Construit le LP du mode direct (§4.3) pour l'objectif demandé."""
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:  # pragma: no cover
        raise RuntimeError("Solveur GLOP indisponible (OR-Tools).")

    x = {r.key: solver.NumVar(0, solver.infinity(), r.key) for r in recipes}

    item_keys: set[str] = set(targets)
    for r in recipes:
        item_keys |= set(r.inputs) | set(r.outputs)

    coefs: dict[str, list[tuple[float, str]]] = {ik: [] for ik in item_keys}
    for r in recipes:
        for ik in set(r.inputs) | set(r.outputs):
            coefs[ik].append((rate(r, ik), r.key))

    def net_expr(ik: str):
        return solver.Sum([c * x[rk] for c, rk in coefs[ik]])

    raw_keys: list[str] = []
    for ik in item_keys:
        is_raw = items[ik].is_raw if ik in items else False
        if ik in targets:
            solver.Add(net_expr(ik) >= targets[ik])
        elif ik in FREE_RAWS:
            continue  # illimité : aucune contrainte, hors objectif min_raw
        elif is_raw:
            raw_keys.append(ik)
            if available and ik in available:
                solver.Add(net_expr(ik) >= -available[ik])
        elif available and ik in available:
            # Entrée externe déclarée (item non-brut, ex. source perso) :
            # consommable jusqu'au cap, comme un brut capé.
            solver.Add(net_expr(ik) >= -available[ik])
        else:
            solver.Add(net_expr(ik) >= 0)  # intermédiaire : pas de consommation nette

    _set_objective(solver, x, net_expr, raw_keys, recipes, machines, objective)

    return LpModel(
        solver=solver, x=x, coefs=coefs, raw_keys=raw_keys, item_keys=item_keys
    )


def build_max_output(
    recipes: list[Recipe],
    items: dict[str, Item],
    target: str,
    available: dict[str, float],
) -> LpModel:
    """Construit le LP du mode inverse (§4.4) : maximiser net_target sous caps.

    Entrées fournies : consommation <= cap. Tout le reste (intermédiaires et
    bruts non fournis) : net >= 0 (cap implicite 0 -> non consommable).
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:  # pragma: no cover
        raise RuntimeError("Solveur GLOP indisponible (OR-Tools).")

    x = {r.key: solver.NumVar(0, solver.infinity(), r.key) for r in recipes}

    item_keys: set[str] = {target}
    for r in recipes:
        item_keys |= set(r.inputs) | set(r.outputs)

    coefs: dict[str, list[tuple[float, str]]] = {ik: [] for ik in item_keys}
    for r in recipes:
        for ik in set(r.inputs) | set(r.outputs):
            coefs[ik].append((rate(r, ik), r.key))

    def net_expr(ik: str):
        return solver.Sum([c * x[rk] for c, rk in coefs[ik]])

    for ik in item_keys:
        if ik == target or ik in FREE_RAWS:
            continue  # cible / brut illimité (eau) : aucune contrainte
        if ik in available:
            solver.Add(net_expr(ik) >= -available[ik])
        else:
            solver.Add(net_expr(ik) >= 0)

    # Régularisation : -ε·Σx pour annuler l'activité indifférente (recettes sans
    # effet sur la cible qui consommeraient des bruts dispo vers des surplus).
    eps = 1e-6
    solver.Maximize(net_expr(target) - eps * solver.Sum([x[r.key] for r in recipes]))

    return LpModel(
        solver=solver, x=x, coefs=coefs,
        raw_keys=list(available), item_keys=item_keys,
    )


def _set_objective(solver, x, net_expr, raw_keys, recipes, machines, objective):
    """Pose la fonction objectif (§4.3)."""
    if objective == "min_raw":
        # Minimiser l'EXTRACTION (pas -net) : un brut produit en surplus compte 0,
        # sinon l'objectif serait non borné dès qu'une recette produit un brut.
        extract = []
        for ik in raw_keys:
            e = solver.NumVar(0, solver.infinity(), f"extract_{ik}")
            solver.Add(net_expr(ik) + e >= 0)  # e >= consommation nette
            extract.append(e)
        solver.Minimize(solver.Sum(extract))
    elif objective == "min_power":
        solver.Minimize(
            solver.Sum(
                [_base_power(machines, r) * x[r.key] for r in recipes]
            )
        )
    elif objective == "min_machines":
        solver.Minimize(solver.Sum([x[r.key] for r in recipes]))
    else:
        raise ValueError(f"Objectif inconnu : {objective!r}")


def _base_power(machines: dict[str, Machine], recipe: Recipe) -> float:
    machine = machines.get(recipe.machine)
    return machine.base_power_mw if machine else 0.0
