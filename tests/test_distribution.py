import json

import pytest

from satisfactory_planner.distribution.balancer import build_balancer, next_factorizable
from satisfactory_planner.distribution.capacity import build_distribution
from satisfactory_planner.distribution.graph import DistributionGraph
from satisfactory_planner.distribution.manifold import build_manifold
from satisfactory_planner.distribution.tree import build_tree, is_factorizable


def test_is_factorizable():
    assert is_factorizable(1)
    assert is_factorizable(6)  # 2*3
    assert is_factorizable(12)  # 2^2*3
    assert not is_factorizable(5)
    assert not is_factorizable(7)
    assert not is_factorizable(10)  # 2*5


def test_build_tree_six_consumers():
    # 6 = 3*2 : greedy /3 d'abord -> 1 splitter_3, puis 3 splitter_2, 6 machines.
    g = DistributionGraph(item_key="X")
    src = g.add_node("source")
    build_tree(g, src, rate=60.0, n=6)

    assert g.count("splitter_3") == 1
    assert g.count("splitter_2") == 3
    assert g.count("machine") == 6
    assert g.leaf_rate_total() == 60.0  # conservation du débit


def test_build_tree_single_consumer():
    g = DistributionGraph()
    src = g.add_node("source")
    build_tree(g, src, rate=45.0, n=1)
    assert g.count("machine") == 1
    assert g.count("splitter_2") == 0
    assert g.leaf_rate_total() == 45.0


def test_build_tree_non_factorizable_raises():
    g = DistributionGraph()
    src = g.add_node("source")
    with pytest.raises(ValueError):
        build_tree(g, src, rate=50.0, n=5)


def test_build_manifold_seven_consumers():
    # 7 machines à 10/min : N-1 = 6 répartiteurs 1->2, tronçon de tête = 70.
    g = DistributionGraph(item_key="X")
    src = g.add_node("source")
    build_manifold(g, src, total=70.0, n=7, q=10.0)

    assert g.count("splitter_2") == 6
    assert g.count("machine") == 7
    assert g.leaf_rate_total() == 70.0
    # Le tronçon de tête (depuis la source) porte le débit total.
    head = next(e for e in g.edges if e.src == src)
    assert head.rate == 70.0


def test_next_factorizable():
    assert next_factorizable(5) == 6
    assert next_factorizable(7) == 8
    assert next_factorizable(10) == 12
    assert next_factorizable(6) == 6


def test_build_balancer_five():
    # N=5 (premier) : M=6 sorties égales, 5 vers machines + 1 réinjecté.
    g = DistributionGraph(item_key="X")
    src = g.add_node("source")
    build_balancer(g, src, total=50.0, n=5)
    assert g.count("machine") == 5
    assert g.leaf_rate_total() == 50.0  # 5 machines * 10/min
    assert g.count("merger_2") >= 1  # surplus réinjecté via groupeur


def test_build_balancer_ten_merge_cascade():
    # N=10 : M=12, 2 lignes de retour -> au moins un groupeur de fusion.
    g = DistributionGraph(item_key="X")
    src = g.add_node("source")
    build_balancer(g, src, total=100.0, n=10)
    assert g.count("machine") == 10
    assert g.leaf_rate_total() == 100.0
    assert g.count("merger_2") >= 1


def test_build_balancer_factorizable_is_plain_tree():
    # N déjà factorisable : pas de retour, arbre simple (aucun groupeur).
    g = DistributionGraph(item_key="X")
    src = g.add_node("source")
    build_balancer(g, src, total=60.0, n=6)
    assert g.count("machine") == 6
    assert g.count("merger_2") == 0


def test_build_distribution_auto_tree():
    g = build_distribution("X", total_rate=60, n_consumers=6,
                           per_consumer_rate=10, belt_capacity=270, strategy="auto")
    assert g.count("machine") == 6
    assert g.count("splitter_3") == 1  # 6 factorisable -> arbre
    assert g.leaf_rate_total() == 60.0


def test_build_distribution_auto_manifold_for_prime():
    g = build_distribution("X", total_rate=50, n_consumers=5,
                           per_consumer_rate=10, belt_capacity=270, strategy="auto")
    assert g.count("machine") == 5
    assert g.count("splitter_2") == 4  # 5 premier -> repli manifold (N-1)
    assert g.leaf_rate_total() == 50.0


def test_build_distribution_parallel_lines():
    # 600/min > 270 -> 3 lignes parallèles ; aucune arête ne dépasse la capacité.
    g = build_distribution("X", total_rate=600, n_consumers=20,
                           per_consumer_rate=30, belt_capacity=270, strategy="auto")
    assert g.count("machine") == 20
    assert g.leaf_rate_total() == 600.0
    assert g.over_capacity_edges() == []
    assert any("ligne" in note for note in g.notes)


def test_build_distribution_balancer_on_prime():
    # Stratégie balancer sur N=7 (premier) : 7 machines au débit exact, avec retour.
    g = build_distribution("X", total_rate=70, n_consumers=7,
                           per_consumer_rate=10, belt_capacity=270, strategy="balancer")
    assert g.count("machine") == 7
    assert g.leaf_rate_total() == 70.0
    assert g.count("merger_2") >= 1


def test_build_distribution_tree_forced_on_prime_raises():
    with pytest.raises(ValueError):
        build_distribution("X", total_rate=50, n_consumers=5,
                           per_consumer_rate=10, belt_capacity=270, strategy="tree")


def test_build_distribution_flags_over_capacity():
    # 1 machine demandant 300/min sur un tapis 270 -> arête en dépassement signalée.
    g = build_distribution("X", total_rate=300, n_consumers=1,
                           per_consumer_rate=300, belt_capacity=270, strategy="auto")
    assert len(g.over_capacity_edges()) == 1


def test_build_distribution_labels_machines_and_source():
    g = build_distribution(
        "Desc_IronPlate_C", total_rate=60, n_consumers=6, per_consumer_rate=10,
        belt_capacity=270, consumer_label="Constructor @ 100%", source_label="Iron Plate",
    )
    machines = [n for n in g.nodes if n.kind == "machine"]
    assert machines and all(n.label == "Constructor @ 100%" for n in machines)
    source = next(n for n in g.nodes if n.kind == "source")
    assert source.label == "Iron Plate"


def test_export_dot():
    g = build_distribution("Desc_IronPlate_C", total_rate=60, n_consumers=6,
                           per_consumer_rate=10, belt_capacity=270)
    dot = g.to_dot()
    assert dot.startswith("digraph")
    assert "splitter_3" in dot
    assert "->" in dot


def test_export_json_roundtrip():
    g = build_distribution("X", total_rate=60, n_consumers=6,
                           per_consumer_rate=10, belt_capacity=270)
    data = json.loads(g.to_json())
    assert len(data["nodes"]) == len(g.nodes)
    assert len(data["edges"]) == len(g.edges)
    assert all("tier" in e for e in data["edges"])  # tier conseillé par arête


def test_report_mentions_counts():
    g = build_distribution("X", total_rate=60, n_consumers=6,
                           per_consumer_rate=10, belt_capacity=270)
    report = g.report()
    assert "répartiteurs" in report
    assert "machines : 6" in report
