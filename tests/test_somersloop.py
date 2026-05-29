from satisfactory_planner.model.entities import Item, Machine, Recipe
from satisfactory_planner.model.repository import Repository
from satisfactory_planner.solver import allocate_somersloops, solve_forward


def _step(plan, key):
    return next(s for s in plan.steps if s.recipe.key == key)


def test_somersloop_full_amplification(sample_docs):
    # 30 lingots/min = 1 Smelter (1 slot). 1 sloop -> amp x2, puissance x4.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronIngot_C": 30})
    used = allocate_somersloops(plan, repo, budget=1)

    step = _step(plan, "Recipe_IngotIron_C")
    assert used == 1
    assert step.somersloops == 1
    assert step.amplification == 2.0
    assert step.output_rate == 60.0
    assert step.power_mw == 16.0  # 4 MW * 2^2
    assert plan.targets["Desc_IronIngot_C"] == 60.0


def test_somersloop_partial_amplification():
    # Machine à 2 slots, 1 sloop -> amp 1.5, puissance x2.25.
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Out": Item(key="Out", name="Out"),
    }
    recipes = {
        "R": Recipe(key="R", name="R", machine="M", duration_s=60.0,
                    inputs={"Ore": 1.0}, outputs={"Out": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=10.0, somersloop_slots=2)},
        enabled={"R"},
    )
    plan = solve_forward(repo, {"Out": 1})  # 1 machine, capacité = 2 slots
    used = allocate_somersloops(plan, repo, budget=1)
    step = _step(plan, "R")
    assert used == 1
    assert step.amplification == 1.5
    assert step.power_mw == round(10.0 * 1.5**2, 6)  # 22.5


def test_somersloop_power_exponent_is_data_driven():
    # L'exposant de puissance vient de la machine (Docs.json), pas codé en dur :
    # avec exposant 1.0, puissance x amp^1 (=x2) au lieu de amp^2 (=x4).
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Out": Item(key="Out", name="Out"),
    }
    recipes = {
        "R": Recipe(key="R", name="R", machine="M", duration_s=60.0,
                    inputs={"Ore": 1.0}, outputs={"Out": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=10.0,
                               somersloop_slots=1, production_boost_power_exponent=1.0)},
        enabled={"R"},
    )
    plan = solve_forward(repo, {"Out": 1})  # 1 machine @ 100% -> 10 MW
    allocate_somersloops(plan, repo, budget=1)
    step = _step(plan, "R")
    assert step.amplification == 2.0
    assert step.power_amplification == 2.0       # amp^1 = 2 (et non amp^2 = 4)
    assert step.power_mw == round(10.0 * 2.0, 6)  # 20 MW, pas 40


def test_somersloop_budget_capped_by_capacity(sample_docs):
    # Budget surdimensionné : on ne dépasse pas la capacité (1 Smelter, 1 slot).
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronIngot_C": 30})
    used = allocate_somersloops(plan, repo, budget=999)
    assert used == 1  # capacité = 1
    assert _step(plan, "Recipe_IngotIron_C").amplification == 2.0


def test_somersloop_zero_budget_noop(sample_docs):
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronIngot_C": 30})
    used = allocate_somersloops(plan, repo, budget=0)
    assert used == 0
    assert _step(plan, "Recipe_IngotIron_C").amplification == 1.0
