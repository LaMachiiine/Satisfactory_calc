import math

from satisfactory_planner.siting import Source, locate_factory
from satisfactory_planner.siting.weber import weighted_geometric_median


def _close(a, b, tol=1e-2):
    return math.dist(a, b) <= tol


def test_weber_center_of_square():
    pts = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    assert _close(weighted_geometric_median(pts, [1, 1, 1, 1]), (0.0, 0.0))


def test_weber_single_point():
    assert _close(weighted_geometric_median([(3.0, 4.0)], [1.0]), (3.0, 4.0))


def test_weber_dominant_weight_pulls_to_point():
    # Poids écrasant sur (0,0) -> médiane quasi sur ce point.
    p = weighted_geometric_median([(0.0, 0.0), (10.0, 0.0), (-10.0, 0.0)], [100.0, 1.0, 1.0])
    assert _close(p, (0.0, 0.0), tol=0.2)


def test_weber_median_is_a_data_point_for_collinear_dominant():
    # Médiane géométrique de 3 points colinéaires = le point du milieu (poids égaux).
    p = weighted_geometric_median([(0.0, 0.0), (5.0, 0.0), (12.0, 0.0)], [1.0, 1.0, 1.0])
    assert _close(p, (5.0, 0.0), tol=1e-2)


def _src(item, x, y, cap):
    return Source(item=item, x=x, y=y, capacity_per_min=cap, kind="node")


def test_select_covers_demand_without_exceeding_capacity():
    # Demande 100 ; deux gisements à 60 -> flux routés 60 + 40, aucune pénurie.
    srcs = [_src("I", 0, 0, 60.0), _src("I", 100, 0, 60.0)]
    best = locate_factory({"I": 100.0}, srcs)[0]
    assert not best.shortfalls
    flows = sorted(p.flow for p in best.picks)
    assert flows == [40.0, 60.0]
    assert all(p.flow <= p.source.capacity_per_min + 1e-9 for p in best.picks)


def test_shortfall_when_capacity_insufficient():
    best = locate_factory({"I": 100.0}, [_src("I", 0, 0, 30.0)])[0]
    assert best.shortfalls.get("I") == 70.0


def test_site_converges_near_demand_weighted_cluster():
    # Un seul item, gisements groupés autour de (1000,1000) -> usine proche.
    srcs = [_src("I", 1000, 1000, 50.0), _src("I", 1100, 900, 50.0), _src("I", 900, 1100, 50.0)]
    best = locate_factory({"I": 120.0}, srcs)[0]
    assert math.dist(best.site, (1000.0, 1000.0)) < 200.0


def test_far_source_does_not_reduce_cost():
    near = [_src("I", 0, 0, 60.0), _src("I", 50, 0, 60.0)]
    cost_near = locate_factory({"I": 100.0}, near)[0].cost
    cost_with_far = locate_factory({"I": 100.0}, near + [_src("I", 999999, 0, 60.0)])[0].cost
    assert cost_with_far <= cost_near + 1e-6


def test_alternatives_sorted_by_cost():
    srcs = [_src("I", 0, 0, 100.0), _src("I", 100000, 0, 100.0)]
    results = locate_factory({"I": 50.0}, srcs, n_alternatives=3)
    costs = [r.cost for r in results]
    assert costs == sorted(costs)
