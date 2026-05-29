"""Stratégie « manifold » universelle (§5.3)."""

from __future__ import annotations

from .graph import DistributionGraph


def build_manifold(
    graph: DistributionGraph, source_id: str, total: float, n: int, q: float,
    consumer_label: str = "",
) -> None:
    """Tronçon unique le long des machines, N-1 répartiteurs 1->2 (§5.3)."""
    if n == 1:
        machine = graph.add_node("machine", label=consumer_label)
        graph.add_edge(source_id, machine, total)
        return

    prev = source_id
    reste = total
    for _ in range(n - 1):
        splitter = graph.add_node("splitter_2")
        graph.add_edge(prev, splitter, reste)  # le tronçon porte le reste
        machine = graph.add_node("machine", label=consumer_label)
        graph.add_edge(splitter, machine, q)
        reste -= q
        prev = splitter
    last = graph.add_node("machine", label=consumer_label)
    graph.add_edge(prev, last, reste)  # la dernière machine prend le résidu (= q)
