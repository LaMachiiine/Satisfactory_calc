from satisfactory_planner.model.entities import Machine, Recipe
from satisfactory_planner.solver.realize import realize_step

MACHINES = {"M": Machine(key="M", name="M", base_power_mw=4.0, power_exponent=1.321928)}
RECIPE = Recipe(
    key="R", name="R", machine="M", duration_s=2.0,
    inputs={"A": 1.0}, outputs={"B": 1.0},
)


def test_ceil_and_clock_fractional():
    step = realize_step(RECIPE, 2.5, MACHINES)
    assert step.machines == 3  # ceil(2.5)
    assert round(step.clock, 4) == 83.3333  # 2.5 / 3 * 100


def test_exact_integer_full_clock():
    step = realize_step(RECIPE, 3.0, MACHINES)
    assert step.machines == 3
    assert step.clock == 100.0
    assert step.power_mw == 12.0  # 4 MW * 3 machines à 100 %


def test_power_underclock_uses_exponent():
    # 1 machine à 50 % : 4 * (0.5 ** 1.321928).
    step = realize_step(RECIPE, 0.5, MACHINES)
    assert step.machines == 1
    assert step.clock == 50.0
    assert round(step.power_mw, 4) == round(4.0 * 0.5**1.321928, 4)


def test_realize_max100_full_plus_remainder():
    # x=2.5, strategy max100 -> 2 machines à 100 % + 1 à 50 %.
    step = realize_step(RECIPE, 2.5, MACHINES, strategy="max100")
    assert step.machines == 3
    assert step.clock_groups == [(2, 100.0), (1, 50.0)]
    expected = 4.0 * (2 * 1.0 + 1 * 0.5**1.321928)
    assert round(step.power_mw, 3) == round(expected, 3)
    assert step.clock_label() == "2×100% + 1×50%"


def test_realize_max100_integer_all_full():
    step = realize_step(RECIPE, 3.0, MACHINES, strategy="max100")
    assert step.machines == 3
    assert step.clock_groups == [(3, 100.0)]
    assert step.power_mw == 12.0


def test_realize_overclock_fewer_machines():
    # x=2.5, overclock (max 250 %) -> 1 machine à 250 %.
    step = realize_step(RECIPE, 2.5, MACHINES, strategy="overclock")
    assert step.machines == 1
    assert step.clock == 250.0
    assert round(step.power_mw, 2) == round(4.0 * 2.5**1.321928, 2)


def test_realize_uniform_is_default():
    step = realize_step(RECIPE, 2.5, MACHINES)
    assert step.machines == 3
    assert round(step.clock, 4) == 83.3333
    assert step.clock_groups == [(3, round(2.5 / 3 * 100, 6))]


def test_main_output_is_largest():
    recipe = Recipe(
        key="R2", name="R2", machine="M", duration_s=60.0,
        inputs={"A": 1.0}, outputs={"Small": 1.0, "Big": 5.0},
    )
    step = realize_step(recipe, 1.0, MACHINES)
    assert step.main_output == "Big"
    assert step.output_rate == 5.0  # 5/cycle * 60/60s
