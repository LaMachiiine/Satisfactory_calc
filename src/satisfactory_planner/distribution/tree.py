"""Stratégie « arbre équilibré » /2 /3 (§5.2)."""

from __future__ import annotations

from .graph import DistributionGraph


def is_factorizable(n: int) -> bool:
    """Vrai si n = 2^a * 3^b (divisible proprement en répartiteurs /2 et /3)."""
    if n < 1:
        return False
    while n % 2 == 0:
        n //= 2
    while n % 3 == 0:
        n //= 3
    return n == 1


def build_tree(
    graph: DistributionGraph, parent_id: str, rate: float, n: int, consumer_label: str = ""
) -> None:
    """Divise récursivement `rate` en `n` flux égaux (greedy /3 puis /2)."""
    if n == 1:
        machine = graph.add_node("machine", label=consumer_label)
        graph.add_edge(parent_id, machine, rate)
        return
    if n % 3 == 0:
        factor = 3
    elif n % 2 == 0:
        factor = 2
    else:
        raise ValueError(f"{n} non factorisable en 2 et 3 (repli manifold requis)")

    splitter = graph.add_node(f"splitter_{factor}")
    graph.add_edge(parent_id, splitter, rate)
    for _ in range(factor):
        build_tree(graph, splitter, rate / factor, n // factor, consumer_label)
