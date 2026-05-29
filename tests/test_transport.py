import math

from satisfactory_planner.transport import (
    MODES_BY_KEY,
    decision_grid,
    evaluate,
    recommend,
    unit_rate,
)


def test_belt_and_pipe_unit_rates_fixed():
    assert unit_rate("belt", 100, 500.0) == 1200.0
    assert unit_rate("pipe", 100, 500.0) == 600.0


def test_vehicle_throughput_drops_with_distance_and_grows_with_stack():
    near = unit_rate("train", 100, 200.0)
    far = unit_rate("train", 100, 5000.0)
    assert far < near  # plus loin -> aller-retour plus long -> moins de débit
    assert unit_rate("train", 200, 1000.0) > unit_rate("train", 100, 1000.0)


def test_fluid_carried_by_pipe_and_train_only():
    opts = evaluate(item_is_fluid=True, rate=300.0, dist_m=400.0)
    feasible = {o.mode for o in opts if o.feasible}
    assert feasible == {"pipe", "train"}  # train = wagon-citerne ; pas tapis/camion/drone
    # Courte distance, débit modéré -> pipeline (le train a un gros coût fixe).
    assert recommend(True, 300.0, 400.0).mode == "pipe"


def test_train_carries_fluid_in_tanker_wagons():
    # Le train transporte du fluide (1600 m³/wagon) : débit fluide indépendant de la pile.
    o = next(o for o in evaluate(True, 600.0, 1000.0) if o.mode == "train")
    assert o.feasible and o.unit_rate > 0


def test_solid_not_carried_by_pipe():
    opts = {o.mode: o for o in evaluate(item_is_fluid=False, rate=300.0, dist_m=400.0)}
    assert not opts["pipe"].feasible
    assert opts["belt"].feasible


def test_units_is_ceil_rate_over_unit_rate():
    o = next(o for o in evaluate(False, 2500.0, 300.0) if o.mode == "belt")
    assert o.units == math.ceil(2500.0 / 1200.0)  # 3 tapis


def test_short_distance_prefers_belt_for_solid():
    assert recommend(False, 600.0, 10.0).mode == "belt"


def test_cost_increases_with_distance():
    near = recommend(False, 600.0, 50.0)
    far = next(o for o in evaluate(False, 600.0, 5000.0) if o.mode == near.mode)
    assert far.cost > near.cost


def test_evaluate_sorted_feasible_first_then_cost():
    opts = evaluate(item_is_fluid=True, rate=300.0, dist_m=400.0)
    # tous les faisables avant les non faisables
    feas = [o.feasible for o in opts]
    assert feas == sorted(feas, reverse=True)
    costs = [o.cost for o in opts if o.feasible]
    assert costs == sorted(costs)


def test_decision_grid_shape_and_valid_modes():
    dists = [50.0, 1000.0, 6000.0]
    rates = [120.0, 6000.0]
    grid = decision_grid(dists, rates, item_is_fluid=False)
    assert len(grid) == len(rates) and all(len(row) == len(dists) for row in grid)
    assert all(cell in MODES_BY_KEY for row in grid for cell in row)
    # courte distance -> tapis quel que soit le débit
    assert grid[0][0] == "belt" and grid[1][0] == "belt"


def test_belt_cost_scales_with_parallel_lines():
    # N tapis parall`eles sur une longue distance co^utent ~Nx (lignes parall`eles).
    one = next(o for o in evaluate(False, 1200.0, 5000.0) if o.mode == "belt")   # 1 ligne
    two = next(o for o in evaluate(False, 2400.0, 5000.0) if o.mode == "belt")   # 2 lignes
    assert two.cost >= one.cost * 1.8


def test_train_wins_long_distance_high_throughput():
    assert recommend(False, 1200.0, 12000.0).mode == "train"


def test_truck_wins_medium_distance():
    assert recommend(False, 480.0, 2000.0).mode == "truck"


def test_drone_wins_long_distance_low_throughput():
    assert recommend(False, 120.0, 5000.0).mode == "drone"


def test_belt_wins_short_distance_high_throughput():
    assert recommend(False, 1200.0, 250.0).mode == "belt"
