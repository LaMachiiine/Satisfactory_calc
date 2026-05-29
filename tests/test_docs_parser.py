from satisfactory_planner.data.docs_parser import parse_docs


def test_items_raw_and_fluid_flags(sample_docs):
    parsed = parse_docs(sample_docs)
    assert parsed.items["Desc_OreIron_C"].is_raw is True
    assert parsed.items["Desc_OreIron_C"].is_fluid is False
    assert parsed.items["Desc_Water_C"].is_raw is True
    assert parsed.items["Desc_Water_C"].is_fluid is True
    assert parsed.items["Desc_IronIngot_C"].is_raw is False


def test_machine_power(sample_docs):
    parsed = parse_docs(sample_docs)
    smelter = parsed.machines["Build_SmelterMk1_C"]
    assert smelter.base_power_mw == 4.0
    assert round(smelter.power_exponent, 5) == 1.32193


def test_machine_somersloop_slots(sample_docs):
    parsed = parse_docs(sample_docs)
    assert parsed.machines["Build_SmelterMk1_C"].somersloop_slots == 1
    assert parsed.machines["Build_OilRefinery_C"].somersloop_slots == 2


def test_standard_recipe(sample_docs):
    parsed = parse_docs(sample_docs)
    r = parsed.recipes["Recipe_IngotIron_C"]
    assert r.machine == "Build_SmelterMk1_C"  # établi écarté
    assert r.is_alternate is False
    assert r.inputs == {"Desc_OreIron_C": 1.0}
    assert r.outputs == {"Desc_IronIngot_C": 1.0}
    assert r.rate_per_min("Desc_IronIngot_C") == 30.0


def test_fluid_amount_scaling(sample_docs):
    parsed = parse_docs(sample_docs)
    r = parsed.recipes["Recipe_Alternate_PureIronIngot_C"]
    assert r.is_alternate is True
    assert r.inputs["Desc_Water_C"] == 4.0  # 4000 / 1000 (fluide)
    assert r.inputs["Desc_OreIron_C"] == 7.0
    assert r.outputs["Desc_IronIngot_C"] == 13.0
    # Débits/min (valeurs connues de Pure Iron Ingot).
    assert r.rate_per_min("Desc_OreIron_C") == 35.0
    assert r.rate_per_min("Desc_Water_C") == 20.0
    assert r.rate_per_min("Desc_IronIngot_C") == 65.0


def test_handcrafted_recipe_excluded(sample_docs):
    parsed = parse_docs(sample_docs)
    # Produite uniquement au build gun -> non automatisable -> écartée.
    assert "Recipe_HandCraftedOnly_C" not in parsed.recipes


def test_alternate_detected_by_display_name():
    # Bug 1.1 : "Alternate: Pure Aluminum Ingot" a un ClassName SANS prefixe
    # Recipe_Alternate_, mais son nom commence par "Alternate:" -> doit etre alternate
    # (sinon elle est activee par defaut et le solveur l'utilise sans autorisation).
    from pathlib import Path

    import pytest
    real = Path(__file__).resolve().parents[1] / "data" / "Docs.json"
    if not real.exists():
        pytest.skip("data/Docs.json absent")
    parsed = parse_docs(real)
    r = parsed.recipes["Recipe_PureAluminumIngot_C"]
    assert r.name.startswith("Alternate")
    assert r.is_alternate is True
    # Un alternate detecte par prefixe ClassName reste alternate.
    assert parsed.recipes["Recipe_Alternate_Turbofuel_C"].is_alternate is True
