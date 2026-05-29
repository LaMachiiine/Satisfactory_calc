"""Modes de résolution : forward et max-output (§4.3, §4.4)."""

from __future__ import annotations

from ortools.linear_solver import pywraplp

from ..model.repository import Repository
from .lp_model import LpModel, build_forward, build_max_output
from .realize import realize_step
from .result import Plan

# Objectifs supportés en mode forward.
OBJECTIVES = ("min_raw", "min_power", "min_machines")

_EPS = 1e-6


def _make_plan(
    model: LpModel,
    recipes: list,
    repo: Repository,
    targets: dict[str, float],
    consumed_keys,
    realize_strategy: str = "uniform",
) -> Plan:
    """Extrait un Plan d'un LP résolu (commun forward / max_output)."""
    steps = []
    for r in recipes:
        value = model.x[r.key].solution_value()
        if value <= _EPS:
            continue
        steps.append(realize_step(r, round(value, 9), repo.machines, realize_strategy))

    raw_consumed: dict[str, float] = {}
    for ik in consumed_keys:
        consumption = -model.net_value(ik)
        if consumption > _EPS:
            raw_consumed[ik] = round(consumption, 6)

    consumed_set = set(consumed_keys)
    byproducts: dict[str, float] = {}
    for ik in model.item_keys:
        if ik in targets or ik in consumed_set:
            continue
        if ik in repo.items and repo.items[ik].is_raw:
            continue
        net = model.net_value(ik)
        if net > _EPS:
            byproducts[ik] = round(net, 6)

    return Plan(
        steps=steps,
        raw_consumed=raw_consumed,
        byproducts=byproducts,
        targets=dict(targets),
        item_names={k: v.name for k, v in repo.items.items()},
    )


def solve_forward(
    repo: Repository,
    targets: dict[str, float],
    objective: str = "min_raw",
    available: dict[str, float] | None = None,
    realize_strategy: str = "uniform",
) -> Plan:
    """« Je veux N unités/min de X » -> plan de production."""
    if objective not in OBJECTIVES:
        raise ValueError(f"objectif inconnu : {objective!r} (attendu {OBJECTIVES})")

    recipes = repo.enabled_recipes()
    model = build_forward(recipes, repo.items, repo.machines, targets, available, objective)

    if model.solver.Solve() != pywraplp.Solver.OPTIMAL:
        raise ValueError(
            "Pas de solution optimale : problème infaisable "
            "(cible inatteignable avec les recettes/bruts disponibles) ou non borné."
        )
    external_keys = [
        k for k in (available or {})
        if k in repo.items and not repo.items[k].is_raw and k not in targets
    ]
    consumed_keys = model.raw_keys + external_keys
    return _make_plan(model, recipes, repo, targets, consumed_keys, realize_strategy)


def solve_max_output(
    repo: Repository,
    target: str,
    available: dict[str, float],
    realize_strategy: str = "uniform",
) -> Plan:
    """« J'ai ces ressources -> production max de la cible » (§4.4)."""
    recipes = repo.enabled_recipes()
    model = build_max_output(recipes, repo.items, target, available)

    if model.solver.Solve() != pywraplp.Solver.OPTIMAL:
        raise ValueError(
            "Pas de solution optimale pour le mode inverse "
            "(problème non borné : la cible est productible sans limite ?)."
        )

    achieved = round(model.net_value(target), 6)
    return _make_plan(
        model, recipes, repo, {target: achieved}, list(available), realize_strategy
    )
