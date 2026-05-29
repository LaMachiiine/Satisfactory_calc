import pytest

from satisfactory_planner.model.entities import Item, Machine, Recipe
from satisfactory_planner.model.repository import Repository


def _raw_craft_repo():
    items = {
        "Plate": Item(key="Plate", name="Plate"),
        "Scrap": Item(key="Scrap", name="Scrap"),
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Water": Item(key="Water", name="Water", is_raw=True, is_fluid=True),
    }
    recipes = {
        # Sortie principale = brut -> synthèse de brut (style Converter).
        "Conv": Recipe(key="Conv", name="Conv", machine="M", duration_s=60.0,
                       inputs={"Plate": 1.0}, outputs={"Ore": 1.0}),
        # Brut en simple sous-produit (sortie principale non brute) -> à garder.
        "Scrapper": Recipe(key="Scrapper", name="Scrapper", machine="M", duration_s=60.0,
                           inputs={"Plate": 1.0}, outputs={"Scrap": 6.0, "Water": 2.0}),
    }
    return Repository(
        items=items, recipes=recipes,
        machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
        enabled={"Conv", "Scrapper"},
    )


def test_raw_crafting_always_excluded():
    # La synthèse de bruts (sortie principale = brut) est toujours écartée ;
    # un brut en simple sous-produit n'écarte pas la recette.
    repo = _raw_craft_repo()
    keys = {r.key for r in repo.enabled_recipes()}
    assert "Conv" not in keys  # synthèse de brut écartée
    assert "Scrapper" in keys  # sous-produit brut : conservé


def test_alternates_enabled_by_default(sample_docs):
    repo = Repository.from_docs(sample_docs, enable_alternates=True)
    assert "Recipe_Alternate_PureIronIngot_C" in repo.enabled


def test_alternates_disabled(sample_docs):
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    # Toujours dans le catalogue, mais pas activée.
    assert "Recipe_Alternate_PureIronIngot_C" in repo.recipes
    assert "Recipe_Alternate_PureIronIngot_C" not in repo.enabled
    assert "Recipe_IngotIron_C" in repo.enabled


def test_with_recipes_enabled(sample_docs):
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    fine = repo.with_recipes_enabled(["Recipe_Alternate_PureIronIngot_C"])
    assert "Recipe_Alternate_PureIronIngot_C" in fine.enabled
    assert "Recipe_IngotIron_C" in fine.enabled  # standard toujours là


def test_recipes_producing(sample_docs):
    repo = Repository.from_docs(sample_docs, enable_alternates=True)
    producers = {r.key for r in repo.recipes_producing("Desc_IronIngot_C")}
    assert producers == {"Recipe_IngotIron_C", "Recipe_Alternate_PureIronIngot_C"}


def test_resolve_item_by_key(sample_docs):
    repo = Repository.from_docs(sample_docs)
    assert repo.resolve_item("Desc_IronIngot_C") == "Desc_IronIngot_C"


def test_resolve_item_by_name_case_insensitive(sample_docs):
    repo = Repository.from_docs(sample_docs)
    assert repo.resolve_item("iron ingot") == "Desc_IronIngot_C"


def test_resolve_item_unknown_raises(sample_docs):
    repo = Repository.from_docs(sample_docs)
    with pytest.raises(KeyError):
        repo.resolve_item("Inexistant")


def test_cache_roundtrip(sample_docs, tmp_path):
    repo = Repository.from_docs(sample_docs, enable_alternates=True)
    cache = tmp_path / "recipes.json"
    repo.save_cache(cache)
    reloaded = Repository.from_cache(cache)
    assert reloaded.game_version == repo.game_version
    assert reloaded.recipes.keys() == repo.recipes.keys()
    assert reloaded.enabled == repo.enabled
    assert reloaded.recipes["Recipe_IngotIron_C"].rate_per_min("Desc_IronIngot_C") == 30.0
