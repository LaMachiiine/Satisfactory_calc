"""Gestion de capacité : lignes parallèles, tiers, façade build_distribution (§5.4)."""

from __future__ import annotations

import math

from .balancer import build_balancer
from .graph import DistributionGraph
from .manifold import build_manifold
from .tree import build_tree, is_factorizable


def build_distribution(
    item_key: str,
    total_rate: float,
    n_consumers: int,
    per_consumer_rate: float,
    belt_capacity: float,
    strategy: str = "auto",
    consumer_label: str = "",
    source_label: str = "",
) -> DistributionGraph:
    """Construit l'arbre de répartition pour une liaison producteur->consommateurs.

    Si `total_rate` dépasse `belt_capacity`, répartit les consommateurs en
    P = ceil(total/capacité) lignes parallèles équilibrées depuis la source.
    `consumer_label` étiquette les machines (type + horloge) ; `source_label` la source.
    """
    graph = DistributionGraph(item_key=item_key, belt_capacity=belt_capacity)
    if n_consumers <= 0:
        return graph

    source = graph.add_node("source", label=source_label or item_key)

    lines = 1
    if belt_capacity > 0 and total_rate > belt_capacity:
        lines = min(math.ceil(total_rate / belt_capacity), n_consumers)

    base, rem = divmod(n_consumers, lines)
    sizes = [base + 1] * rem + [base] * (lines - rem)
    sizes = [s for s in sizes if s > 0]

    if len(sizes) > 1:
        graph.notes.append(
            f"{len(sizes)} lignes parallèles "
            f"(débit total {total_rate:g}/min > capacité {belt_capacity:g}/min)"
        )
        if len(set(sizes)) > 1:
            graph.notes.append(f"groupes inégaux : {sizes}")

    for size in sizes:
        _build_line(
            graph, source, size, size * per_consumer_rate,
            per_consumer_rate, strategy, consumer_label,
        )

    return graph


def _build_line(
    graph: DistributionGraph,
    source: str,
    size: int,
    line_rate: float,
    per_consumer_rate: float,
    strategy: str,
    consumer_label: str,
) -> None:
    effective = strategy
    if strategy == "auto":
        effective = "tree" if is_factorizable(size) else "manifold"

    if effective == "tree":
        build_tree(graph, source, line_rate, size, consumer_label)
    elif effective == "manifold":
        build_manifold(graph, source, line_rate, size, per_consumer_rate, consumer_label)
    elif effective == "balancer":
        build_balancer(graph, source, line_rate, size, consumer_label)
    else:
        raise ValueError(f"stratégie inconnue : {strategy!r}")
