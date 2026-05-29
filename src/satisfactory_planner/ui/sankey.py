"""Construction des données d'un diagramme de Sankey à partir d'un plan.

Logique pure (sans dépendance Streamlit/Plotly) pour rester testable. Les liens
modélisent les flux item -> item : pour chaque étape, chaque entrée alimente la
sortie principale, au débit consommé (objets/min).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..solver.result import Plan


@dataclass
class SankeyData:
    """Format neutre : indices de nœuds + liens, convertible en Plotly."""

    labels: list[str] = field(default_factory=list)
    source: list[int] = field(default_factory=list)
    target: list[int] = field(default_factory=list)
    value: list[float] = field(default_factory=list)


def build_sankey(plan: Plan) -> SankeyData:
    """Construit les flux item->item du plan (liens agrégés par paire)."""
    # Débit total consommé de chaque entrée, agrégé par (entrée, sortie principale).
    flows: dict[tuple[str, str], float] = {}
    for step in plan.steps:
        recipe = step.recipe
        out = step.main_output
        for item_key, qty in recipe.inputs.items():
            rate = step.x * qty * 60.0 / recipe.duration_s
            if rate <= 0:
                continue
            flows[(item_key, out)] = flows.get((item_key, out), 0.0) + rate

    keys = {k for pair in flows for k in pair}
    labels_keys = sorted(keys)
    index = {k: i for i, k in enumerate(labels_keys)}

    data = SankeyData(labels=[plan.item_names.get(k, k) for k in labels_keys])
    for (src, dst), rate in flows.items():
        data.source.append(index[src])
        data.target.append(index[dst])
        data.value.append(round(rate, 6))
    return data
