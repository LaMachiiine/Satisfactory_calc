"""Équilibreur à retour pour les N non factorisables (§5.5).

Principe : produire `M = plus petit 2^a·3^b ≥ N` sorties égales via un arbre,
en réinjectant le surplus (M−N lignes) par des groupeurs à l'entrée. En régime
permanent, le flux d'entrée de l'arbre vaut `F = total·M/N`, chaque feuille porte
`total/N`, et les N feuilles « machines » reçoivent donc exactement le bon débit.

Réseau plus complexe que le manifold (flux interne F > total), mais ratio exact.
"""

from __future__ import annotations

from .graph import DistributionGraph
from .tree import build_tree, is_factorizable


def next_factorizable(n: int) -> int:
    """Plus petit entier >= n de la forme 2^a·3^b."""
    m = max(n, 1)
    while not is_factorizable(m):
        m += 1
    return m


def _split_open(
    graph: DistributionGraph, parent: str, rate: float, n: int,
    slots: list[tuple[str, float]],
) -> None:
    """Arbre de répartiteurs dont les feuilles sont des « slots » ouverts."""
    if n == 1:
        slots.append((parent, rate))
        return
    factor = 3 if n % 3 == 0 else 2
    splitter = graph.add_node(f"splitter_{factor}")
    graph.add_edge(parent, splitter, rate)
    for _ in range(factor):
        _split_open(graph, splitter, rate / factor, n // factor, slots)


def _merge_lines(
    graph: DistributionGraph, parents: list[str], rate_each: float
) -> tuple[str, float]:
    """Fusionne en cascade `parents` (une ligne chacun) en un nœud unique."""
    prev, acc = parents[0], rate_each
    for parent in parents[1:]:
        merger = graph.add_node("merger_2")
        graph.add_edge(prev, merger, acc)
        graph.add_edge(parent, merger, rate_each)
        acc += rate_each
        prev = merger
    return prev, acc


def build_balancer(
    graph: DistributionGraph, source_id: str, total: float, n: int,
    consumer_label: str = "",
) -> None:
    """Construit l'équilibreur à retour vers N machines au débit total/N."""
    if n <= 0:
        return
    m = next_factorizable(n)
    if m == n:  # déjà factorisable : arbre simple, pas de retour
        build_tree(graph, source_id, total, n, consumer_label)
        return

    per = total / n
    flow = total * m / n
    feedback = total * (m - n) / n

    merger = graph.add_node("merger_2")  # entrée = source + retour
    graph.add_edge(source_id, merger, total)

    slots: list[tuple[str, float]] = []
    _split_open(graph, merger, flow, m, slots)

    for parent, rate in slots[:n]:
        machine = graph.add_node("machine", label=consumer_label)
        graph.add_edge(parent, machine, rate)

    feedback_parents = [parent for parent, _ in slots[n:]]
    if len(feedback_parents) == 1:
        graph.add_edge(feedback_parents[0], merger, per)
    else:
        node, _ = _merge_lines(graph, feedback_parents, per)
        graph.add_edge(node, merger, feedback)
