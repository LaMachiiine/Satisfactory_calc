from pathlib import Path

from satisfactory_planner.nodes.data import ResourceNode, load_nodes
from satisfactory_planner.nodes.extraction import (
    available_caps,
    extraction_rate,
    node_extraction_rate,
)
from satisfactory_planner.nodes.state import NodeState, get_state, load_states, save_states

FIXTURE = Path(__file__).parent / "fixtures" / "nodes_sample.json"
MIXED = Path(__file__).parent / "fixtures" / "nodes_mixed_sample.json"


def test_load_nodes():
    nodes = load_nodes(FIXTURE)
    assert len(nodes) == 4
    by_id = {n.id: n for n in nodes}
    iron = by_id["N1"]
    assert isinstance(iron, ResourceNode)
    assert iron.resource == "Desc_OreIron_C"
    assert iron.purity == "pure"
    assert iron.form == "solid"
    assert (iron.x, iron.y, iron.z) == (1.0, 2.0, 3.0)
    assert by_id["N4"].form == "liquid"


def test_extraction_rate_table():
    # base Mk.1 : impur 30 / normal 60 / pur 120 (à 100 %).
    assert extraction_rate("impure", 1, clock=100.0) == 30.0
    assert extraction_rate("normal", 1, clock=100.0) == 60.0
    assert extraction_rate("pure", 1, clock=100.0) == 120.0
    # tier Mk.2 ×2, Mk.3 ×4.
    assert extraction_rate("normal", 2, clock=100.0) == 120.0
    assert extraction_rate("pure", 3, clock=100.0) == 480.0


def test_extraction_rate_clock_and_sloop():
    assert extraction_rate("pure", 3, clock=250.0) == 1200.0  # 480 * 2.5
    assert extraction_rate("normal", 2, clock=100.0, somersloop=True) == 240.0
    # défaut clock = 250 % (overclock max).
    assert extraction_rate("normal", 1) == 150.0  # 60 * 2.5


def test_extraction_rate_belt_cap():
    # pur Mk.3 250 % + sloop = 2400, plafonné par un tapis Mk.6 (1200).
    assert extraction_rate("pure", 3, 250.0, somersloop=True) == 2400.0
    assert extraction_rate("pure", 3, 250.0, somersloop=True, belt_capacity=1200) == 1200.0


def test_node_state_defaults():
    st = NodeState()
    assert st.available is True
    assert st.miner_tier == 1
    assert st.clock == 250.0  # overclock max par défaut
    assert st.somersloop is False


def test_node_state_persistence(tmp_path):
    path = tmp_path / "nodes_state.json"
    states = {"N1": NodeState(available=False, miner_tier=3, clock=200.0)}
    save_states(states, path)
    reloaded = load_states(path)
    assert reloaded["N1"].available is False
    assert reloaded["N1"].miner_tier == 3
    assert reloaded["N1"].clock == 200.0
    # gisement non configuré -> état par défaut.
    assert get_state(reloaded, "inconnu").clock == 250.0


def test_load_states_missing_file(tmp_path):
    assert load_states(tmp_path / "absent.json") == {}


def test_available_caps_sums_available_nodes():
    # États par défaut (tous dispo, Mk.1, 250 %).
    nodes = load_nodes(FIXTURE)
    caps = available_caps(nodes, {})
    # Fer : N1 pur 250% (300) + N2 normal 250% (150) = 450 ; cuivre N3 impur 250% = 75.
    assert caps["Desc_OreIron_C"] == 450.0
    assert caps["Desc_OreCopper_C"] == 75.0
    assert caps["Desc_LiquidOil_C"] == 300.0


def test_available_caps_excludes_occupied():
    nodes = load_nodes(FIXTURE)
    caps = available_caps(nodes, {"N2": NodeState(available=False)})
    assert caps["Desc_OreIron_C"] == 300.0  # seul N1 reste


def test_load_nodes_kind_and_core():
    by_id = {n.id: n for n in load_nodes(MIXED)}
    assert by_id["IRON1"].kind == "node"
    assert by_id["WELL1"].kind == "well"
    assert by_id["WELL1"].core == "CORE1"
    assert by_id["GEY1"].kind == "geyser"
    # rétrocompat : un nœud sans champ kind reste un "node".
    assert load_nodes(FIXTURE)[0].kind == "node"


def test_node_extraction_rate_well_ignores_miner_tier():
    # Un puits de ressource n'a pas de foreuse Mk : tier ignoré, pas de Somersloop.
    well = ResourceNode(
        id="W", resource="Desc_Water_C", purity="pure", form="liquid",
        kind="well", x=0.0, y=0.0, z=0.0,
    )
    # Mk.3 + sloop dans l'état ne doivent PAS s'appliquer : 120 × 2.5 = 300 (pas ×4 ×2).
    st = NodeState(miner_tier=3, clock=250.0, somersloop=True)
    assert node_extraction_rate(well, st) == 300.0


def test_node_extraction_rate_geyser_is_zero():
    g = ResourceNode(
        id="G", resource="Desc_Geyser_C", purity="unknown", form="geyser",
        kind="geyser", x=0.0, y=0.0, z=0.0,
    )
    assert node_extraction_rate(g, NodeState()) == 0.0


def test_available_caps_includes_wells_excludes_geysers():
    caps = available_caps(load_nodes(MIXED), {})
    assert caps["Desc_OreIron_C"] == 150.0  # node normal @250 %
    assert caps["Desc_Water_C"] == 300.0    # puits pur @250 %
    assert "Desc_Geyser_C" not in caps        # geyser = énergie, hors plafonds
