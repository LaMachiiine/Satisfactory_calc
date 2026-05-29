"""Allocation de Somersloops (§4.5), post-solveur, gloutonne.

Un Somersloop amplifie la **sortie** d'une machine sans augmenter ses entrées,
au prix de la puissance. Pour `s` sloops sur une étape de capacité
`capacité = machines * slots`, l'amplification vaut `amp = 1 + s / capacité`
(plein -> x2), la puissance est multipliée par `amp ** e` où `e` est l'exposant
`mProductionBoostPowerConsumptionExponent` du bâtiment (=2 en 1.0/1.1, plein -> x4).

On amplifie uniquement les étapes produisant un item **cible** : amplifier un
intermédiaire ne ferait que du surplus. Le budget est alloué glouton, par gain
de sortie par sloop décroissant.
"""

from __future__ import annotations

from ..model.repository import Repository
from .result import Plan, PlanStep


def _capacity(repo: Repository, step: PlanStep) -> int:
    machine = repo.machines.get(step.recipe.machine)
    slots = machine.somersloop_slots if machine else 0
    return step.machines * slots


def allocate_somersloops(plan: Plan, repo: Repository, budget: int) -> int:
    """Alloue `budget` sloops aux étapes cibles de `plan` (mutées). Retourne l'usage."""
    targets = set(plan.targets)
    candidates = [
        s for s in plan.steps if s.main_output in targets and _capacity(repo, s) > 0
    ]
    # Glouton : meilleur gain de sortie par sloop d'abord.
    candidates.sort(
        key=lambda s: s.output_rate / _capacity(repo, s), reverse=True
    )

    remaining = budget
    used_total = 0
    for step in candidates:
        capacity = _capacity(repo, step)
        use = min(capacity, remaining)
        if use <= 0:
            break
        machine = repo.machines.get(step.recipe.machine)
        exponent = machine.production_boost_power_exponent if machine else 2.0
        amp = 1.0 + use / capacity
        power_mult = amp**exponent
        step.somersloops = use
        step.amplification = amp
        step.power_amplification = round(power_mult, 6)
        step.output_rate = round(step.output_rate * amp, 6)
        step.per_machine_rate = round(step.per_machine_rate * amp, 6)
        step.power_mw = round(step.power_mw * power_mult, 6)
        remaining -= use
        used_total += use

    # Recalcule les sorties cibles atteintes après amplification.
    for t in plan.targets:
        plan.targets[t] = round(
            sum(s.output_rate for s in plan.steps if s.main_output == t), 6
        )
    return used_total
