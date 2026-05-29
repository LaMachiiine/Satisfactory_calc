"""Résultat d'un plan de production (§7)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model.entities import Recipe


@dataclass
class PlanStep:
    """Une recette retenue par le solveur, réalisée en machines + horloge."""

    recipe: Recipe
    x: float  # nombre de machines-équivalent à 100 % (ratio idéal)
    machines: int  # ceil(x)
    clock: float  # horloge en % (<= 100 en sous-cadençage exact)
    power_mw: float
    main_output: str  # item principal produit
    output_rate: float  # débit total /min de l'item principal
    per_machine_rate: float
    somersloops: int = 0  # sloops alloués sur cette étape
    amplification: float = 1.0  # multiplicateur de sortie (1.0 = aucun)
    power_amplification: float = 1.0  # multiplicateur de puissance (amp ** exposant)
    clock_groups: list[tuple[int, float]] = field(default_factory=list)  # (nb, horloge%)

    def clock_label(self) -> str:
        """Libellé d'horloge : '83%' ou '2×100% + 1×50%' si groupes mixtes."""
        if len(self.clock_groups) <= 1:
            return f"{self.clock:.0f}%"
        return " + ".join(f"{n}×{c:.0f}%" for n, c in self.clock_groups)


@dataclass
class Plan:
    """Plan complet : étapes, bruts consommés, sous-produits en surplus."""

    steps: list[PlanStep]
    raw_consumed: dict[str, float]  # item_key -> /min
    byproducts: dict[str, float]  # surplus d'intermédiaires -> /min
    targets: dict[str, float]
    item_names: dict[str, str] = field(default_factory=dict)

    @property
    def power_total_mw(self) -> float:
        return round(sum(s.power_mw for s in self.steps), 6)

    def _name(self, key: str) -> str:
        return self.item_names.get(key, key)

    def summary(self) -> str:
        lines: list[str] = []
        header = (
            f"{'Recette':<30} {'machines':>8}  {'horloge':>14}  "
            f"{'débit/min':>10}  puissance"
        )
        lines.append(header)
        lines.append("-" * 84)
        for s in sorted(self.steps, key=lambda s: s.recipe.name):
            lines.append(
                f"{s.recipe.name:<30} {s.machines:>8}  {s.clock_label():>14}  "
                f"{s.output_rate:>10.2f}  {s.power_mw:>8.2f} MW"
            )
        lines.append("-" * 80)
        lines.append(f"Puissance totale : {self.power_total_mw:.2f} MW")

        if self.raw_consumed:
            lines.append("\nBruts consommés :")
            for k, v in sorted(self.raw_consumed.items()):
                lines.append(f"  {self._name(k):<28} {v:>10.2f} /min")

        if self.byproducts:
            lines.append("\nSous-produits (surplus) :")
            for k, v in sorted(self.byproducts.items()):
                lines.append(f"  {self._name(k):<28} {v:>10.2f} /min")

        amplified = [s for s in self.steps if s.somersloops > 0]
        if amplified:
            total = sum(s.somersloops for s in amplified)
            lines.append(f"\nSomersloops ({total} utilisés) :")
            for s in sorted(amplified, key=lambda s: s.recipe.name):
                lines.append(
                    f"  {s.recipe.name:<28} {s.somersloops} sloops "
                    f"-> sortie x{s.amplification:.2f}, puissance x{s.power_amplification:.2f}"
                )

        return "\n".join(lines)
