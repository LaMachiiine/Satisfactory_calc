import pytest

from satisfactory_planner.model.entities import Item, Machine, Recipe
from satisfactory_planner.model.repository import Repository
from satisfactory_planner.solver import solve_forward, solve_max_output


def _steps_by_recipe(plan):
    return {s.recipe.key: s for s in plan.steps}


def test_forward_iron_plate_clean(sample_docs):
    # 20 plaques/min : 1 Constructor (20/min) + 1 Smelter (30 lingots/min).
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, targets={"Desc_IronPlate_C": 20}, objective="min_raw")

    steps = _steps_by_recipe(plan)
    assert set(steps) == {"Recipe_IronPlate_C", "Recipe_IngotIron_C"}

    plate = steps["Recipe_IronPlate_C"]
    assert plate.x == 1.0
    assert plate.machines == 1
    assert plate.clock == 100.0
    assert plate.output_rate == 20.0

    ingot = steps["Recipe_IngotIron_C"]
    assert ingot.x == 1.0
    assert ingot.machines == 1

    assert plan.raw_consumed == {"Desc_OreIron_C": 30.0}
    assert plan.byproducts == {}
    assert plan.power_total_mw == 8.0  # 4 MW Constructor + 4 MW Smelter à 100 %


def test_forward_fractional_clock(sample_docs):
    # 10 plaques/min : moitié d'un Constructor et d'un Smelter -> horloge 50 %.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, targets={"Desc_IronPlate_C": 10}, objective="min_raw")

    steps = _steps_by_recipe(plan)
    plate = steps["Recipe_IronPlate_C"]
    assert plate.x == 0.5
    assert plate.machines == 1
    assert plate.clock == 50.0
    assert plate.per_machine_rate == 10.0

    assert plan.raw_consumed == {"Desc_OreIron_C": 15.0}


def test_byproduct_surplus_reported():
    # Recette produisant un sous-produit sans consommateur -> reporté en surplus.
    items = {
        "A": Item(key="A", name="A", is_raw=True),
        "Main": Item(key="Main", name="Main"),
        "By": Item(key="By", name="By"),
    }
    rec = Recipe(
        key="R", name="R", machine="M", duration_s=60.0,
        inputs={"A": 1.0}, outputs={"Main": 1.0, "By": 1.0},
    )
    repo = Repository(
        items=items,
        recipes={"R": rec},
        machines={"M": Machine(key="M", name="M", base_power_mw=10.0)},
        enabled={"R"},
    )
    plan = solve_forward(repo, targets={"Main": 1})
    assert plan.byproducts == {"By": 1.0}
    assert plan.raw_consumed == {"A": 1.0}


def test_infeasible_raises():
    # Cible inatteignable : le seul brut est borné à 0.
    items = {
        "A": Item(key="A", name="A", is_raw=True),
        "Main": Item(key="Main", name="Main"),
    }
    rec = Recipe(
        key="R", name="R", machine="M", duration_s=60.0,
        inputs={"A": 1.0}, outputs={"Main": 1.0},
    )
    repo = Repository(
        items=items, recipes={"R": rec},
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)}, enabled={"R"},
    )
    with pytest.raises(ValueError):
        solve_forward(repo, targets={"Main": 10}, available={"A": 0})


def test_net_balance(sample_docs):
    # Cohérence : ce qui entre = ce qui sort + bruts (ici, ore consommé = ore requis).
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, targets={"Desc_IronPlate_C": 20})
    # 20 plaques exigent 30 lingots, qui exigent 30 minerais.
    assert plan.raw_consumed["Desc_OreIron_C"] == 30.0


def test_min_raw_bounded_with_raw_byproduct():
    # Régression : une recette produisant un brut (eau) ne doit pas rendre
    # l'objectif min_raw non borné. L'extraction se mesure, le surplus ne crédite pas.
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Water": Item(key="Water", name="Water", is_raw=True, is_fluid=True),
        "Widget": Item(key="Widget", name="Widget"),
    }
    recipes = {
        "R1": Recipe(key="R1", name="R1", machine="M", duration_s=60.0,
                     inputs={"Ore": 1.0}, outputs={"Widget": 1.0}),
        "Rfree": Recipe(key="Rfree", name="Rfree", machine="M", duration_s=60.0,
                        inputs={}, outputs={"Water": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
        enabled={"R1", "Rfree"},
    )
    plan = solve_forward(repo, targets={"Widget": 10}, objective="min_raw")
    assert plan.raw_consumed == {"Ore": 10.0}


def test_objective_min_machines_prefers_fewer_machines():
    # Deux voies vers Widget : 1 machine (lente, 1/min) vs 2 étapes. min_machines
    # doit préférer la voie à 1 machine même si elle consomme plus de brut.
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Mid": Item(key="Mid", name="Mid"),
        "Widget": Item(key="Widget", name="Widget"),
    }
    recipes = {
        # Voie directe : 1 machine à 60/min (1 Ore -> 1 Widget en 1s).
        "Direct": Recipe(key="Direct", name="Direct", machine="M", duration_s=1.0,
                         inputs={"Ore": 1.0}, outputs={"Widget": 1.0}),
        # Voie indirecte : 2 machines (Ore->Mid puis Mid->Widget), moins de brut.
        "Step1": Recipe(key="Step1", name="Step1", machine="M", duration_s=1.0,
                        inputs={"Ore": 1.0}, outputs={"Mid": 2.0}),
        "Step2": Recipe(key="Step2", name="Step2", machine="M", duration_s=1.0,
                        inputs={"Mid": 1.0}, outputs={"Widget": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
        enabled=set(recipes),
    )
    plan = solve_forward(repo, targets={"Widget": 60}, objective="min_machines")
    used = {s.recipe.key for s in plan.steps}
    assert used == {"Direct"}


def test_objective_min_power_prefers_low_power_machine():
    # Deux recettes pour Widget : machine sobre (1 MW) vs gourmande (100 MW).
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Widget": Item(key="Widget", name="Widget"),
    }
    recipes = {
        "Cheap": Recipe(key="Cheap", name="Cheap", machine="Low", duration_s=1.0,
                        inputs={"Ore": 1.0}, outputs={"Widget": 1.0}),
        "Pricey": Recipe(key="Pricey", name="Pricey", machine="High", duration_s=1.0,
                         inputs={"Ore": 1.0}, outputs={"Widget": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={
            "Low": Machine(key="Low", name="Low", base_power_mw=1.0),
            "High": Machine(key="High", name="High", base_power_mw=100.0),
        },
        enabled=set(recipes),
    )
    plan = solve_forward(repo, targets={"Widget": 60}, objective="min_power")
    assert {s.recipe.key for s in plan.steps} == {"Cheap"}


def test_max_output_respects_cap(sample_docs):
    # 60 minerais/min -> max lingots. Standard : 1 ore -> 1 lingot -> 60/min.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_max_output(repo, "Desc_IronIngot_C", available={"Desc_OreIron_C": 60})
    assert plan.targets["Desc_IronIngot_C"] == 60.0
    assert plan.raw_consumed["Desc_OreIron_C"] == 60.0


def test_max_output_unprovided_raw_forbidden():
    # L'eau n'est pas fournie -> cap 0 -> la recette qui en a besoin est interdite.
    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Water": Item(key="Water", name="Water", is_raw=True, is_fluid=True),
        "Out": Item(key="Out", name="Out"),
    }
    recipes = {
        # Seule voie : a besoin d'eau (non fournie) -> sortie max = 0.
        "R": Recipe(key="R", name="R", machine="M", duration_s=60.0,
                    inputs={"Ore": 1.0, "Water": 1.0}, outputs={"Out": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
        enabled={"R"},
    )
    plan = solve_max_output(repo, "Out", available={"Ore": 100})
    assert plan.targets["Out"] == 0.0


def test_max_output_more_with_alternate(sample_docs):
    # Non-régression : ajouter Pure Iron Ingot ne doit jamais baisser la sortie max.
    repo_std = Repository.from_docs(sample_docs, enable_alternates=False)
    repo_alt = Repository.from_docs(sample_docs, enable_alternates=True)
    avail = {"Desc_OreIron_C": 70, "Desc_Water_C": 100}
    out_std = solve_max_output(repo_std, "Desc_IronIngot_C", avail).targets["Desc_IronIngot_C"]
    out_alt = solve_max_output(repo_alt, "Desc_IronIngot_C", avail).targets["Desc_IronIngot_C"]
    assert out_alt >= out_std


def test_max_output_excludes_unrelated_recipes():
    # Une recette consommant un AUTRE brut dispo vers un surplus est indifférente
    # pour l'objectif : elle ne doit pas polluer le plan (régularisation).
    items = {
        "OreA": Item(key="OreA", name="OreA", is_raw=True),
        "OreB": Item(key="OreB", name="OreB", is_raw=True),
        "Widget": Item(key="Widget", name="Widget"),
        "Junk": Item(key="Junk", name="Junk"),
    }
    recipes = {
        "R": Recipe(key="R", name="R", machine="M", duration_s=60.0,
                    inputs={"OreA": 1.0}, outputs={"Widget": 1.0}),
        "J": Recipe(key="J", name="J", machine="M", duration_s=60.0,
                    inputs={"OreB": 1.0}, outputs={"Junk": 1.0}),
    }
    repo = Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
        enabled={"R", "J"},
    )
    plan = solve_max_output(repo, "Widget", {"OreA": 100, "OreB": 100})
    assert {s.recipe.key for s in plan.steps} == {"R"}
    assert plan.targets["Widget"] == 100.0


def test_min_raw_prefers_alternate(sample_docs):
    # Avec alternatives activées, Pure Iron Ingot consomme moins de brut/lingot
    # (35 ore + 20 eau pour 65 lingots) que la recette standard (1 ore/lingot).
    repo = Repository.from_docs(sample_docs, enable_alternates=True)
    plan = solve_forward(repo, targets={"Desc_IronIngot_C": 65})
    used = {s.recipe.key for s in plan.steps}
    assert "Recipe_Alternate_PureIronIngot_C" in used
    assert "Recipe_IngotIron_C" not in used


def _free_water_repo():
    items = {
        "Desc_Water_C": Item(key="Desc_Water_C", name="Water", is_raw=True, is_fluid=True),
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "T": Item(key="T", name="T"),
    }
    r = Recipe(key="R", name="R", machine="M", duration_s=60.0,
               inputs={"Desc_Water_C": 2.0, "Ore": 1.0}, outputs={"T": 1.0})
    return Repository(items=items, recipes={"R": r}, machines={}, enabled={"R"})


def test_inverse_water_is_unlimited():
    # L'eau (illimitée) n'a pas besoin d'être fournie : la cible est produite
    # jusqu'à la limite de l'ore.
    plan = solve_max_output(_free_water_repo(), "T", {"Ore": 60.0})
    assert plan.targets["T"] == pytest.approx(60.0)


def test_forward_min_raw_ignores_water():
    # min_raw ne compte pas l'eau : seul l'ore apparaît dans les bruts consommés.
    plan = solve_forward(_free_water_repo(), {"T": 10.0}, objective="min_raw")
    assert "Desc_Water_C" not in plan.raw_consumed
    assert plan.raw_consumed.get("Ore") == pytest.approx(10.0)


def test_forward_uses_external_nonraw_input():
    from satisfactory_planner.model.entities import Item, Machine, Recipe
    from satisfactory_planner.model.repository import Repository
    from satisfactory_planner.solver import solve_forward

    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Mid": Item(key="Mid", name="Mid"),
        "Out": Item(key="Out", name="Out"),
    }
    recipes = {
        "R1": Recipe(key="R1", name="R1", machine="M", duration_s=60.0,
                     inputs={"Ore": 1.0}, outputs={"Mid": 1.0}),
        "R2": Recipe(key="R2", name="R2", machine="M", duration_s=60.0,
                     inputs={"Mid": 1.0}, outputs={"Out": 1.0}),
    }
    repo = Repository(items=items, recipes=recipes,
                      machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
                      enabled={"R1", "R2"})

    base = solve_forward(repo, {"Out": 10.0})
    assert base.raw_consumed.get("Ore") == 10.0

    coupled = solve_forward(repo, {"Out": 10.0}, available={"Mid": 4.0})
    assert coupled.raw_consumed.get("Ore") == 6.0   # 4 Mid externes -> 6 Ore
    assert coupled.raw_consumed.get("Mid") == 4.0    # entree externe consommee
