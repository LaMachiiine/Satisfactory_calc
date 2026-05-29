from satisfactory_planner.data.game_constants import belt_for_rate
from satisfactory_planner.model.entities import Recipe


def test_rate_per_min_output():
    # Lingot de fer : 1 produit / 2 s -> 30/min (valeur connue).
    r = Recipe(
        key="Recipe_IngotIron_C", name="Iron Ingot", machine="Build_SmelterMk1_C",
        duration_s=2.0, inputs={"Desc_OreIron_C": 1.0}, outputs={"Desc_IronIngot_C": 1.0},
    )
    assert r.rate_per_min("Desc_IronIngot_C") == 30.0
    assert r.rate_per_min("Desc_OreIron_C") == 30.0


def test_rate_per_min_unknown_item():
    r = Recipe(
        key="r", name="r", machine="m", duration_s=1.0,
        inputs={}, outputs={"Desc_X_C": 1.0},
    )
    try:
        r.rate_per_min("Desc_Absent_C")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("KeyError attendue pour un item absent")


def test_belt_for_rate():
    assert belt_for_rate(40).tier == 1  # 60/min suffit
    assert belt_for_rate(300).tier == 4  # 480/min (270 insuffisant)
    assert belt_for_rate(5000) is None  # au-delà du Mk.6
