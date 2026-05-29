from pathlib import Path

import pytest

from satisfactory_planner.nodes.data import ResourceNode, load_nodes
from satisfactory_planner.nodes.state import NodeState
from satisfactory_planner.ui.map_view import (
    MAP_BOUNDS,
    PURITY_COLOR,
    marker_color,
    node_tooltip,
    world_to_latlng,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nodes_sample.json"
MIXED = Path(__file__).parent / "fixtures" / "nodes_mixed_sample.json"


def test_world_to_latlng_flips_y_and_scales():
    # Nord en haut : lat = -y/6400 (en jeu +Y = sud), lng = x/6400.
    assert world_to_latlng(6400.0, 12800.0) == (-2.0, 1.0)


def test_map_bounds_match_scim_padded_world():
    # Fond SCIM = bornes jouables élargies de 1/8, projeté (lat,lng) avec flip Y.
    (lat_min, lng_min), (lat_max, lng_max) = MAP_BOUNDS
    assert lat_min == pytest.approx(-73.2422, abs=1e-3)  # sud  (+468750)
    assert lat_max == pytest.approx(73.2422, abs=1e-3)   # nord (-468750)
    assert lng_min == pytest.approx(-65.3826, abs=1e-3)  # ouest
    assert lng_max == pytest.approx(81.1019, abs=1e-3)   # est


def test_purity_colors_distinct():
    assert {"impure", "normal", "pure"} <= set(PURITY_COLOR)
    assert len(set(PURITY_COLOR.values())) == 3


def _node(**kw):
    base = dict(id="X", resource="Desc_OreIron_C", purity="pure", form="solid",
                kind="node", x=0.0, y=0.0, z=0.0)
    base.update(kw)
    return ResourceNode(**base)


def test_marker_color_geyser_is_distinct():
    assert marker_color(_node(kind="node", purity="pure")) == PURITY_COLOR["pure"]
    assert marker_color(_node(kind="well", purity="normal")) == PURITY_COLOR["normal"]
    # Geyser : couleur dédiée, distincte des puretés.
    geyser_color = marker_color(_node(kind="geyser", purity="unknown"))
    assert geyser_color not in PURITY_COLOR.values()


def test_node_tooltip_uses_name_rate_and_status():
    node = load_nodes(FIXTURE)[0]  # N1 pur
    tip = node_tooltip(node, NodeState(miner_tier=3, clock=100.0), name="Minerai de fer")
    assert "Minerai de fer" in tip  # nom propre
    assert "disponible" in tip
    assert "480" in tip  # pur Mk.3 @100% = 480/min


def test_node_tooltip_well_mentions_puits_and_rate():
    well = _node(kind="well", purity="pure", resource="Desc_Water_C", form="liquid")
    tip = node_tooltip(well, NodeState(clock=250.0), name="Eau")
    assert "puits" in tip.lower()
    assert "300" in tip  # 120 * 2.5, tier ignoré


def test_node_tooltip_geyser_has_no_rate():
    tip = node_tooltip(_node(kind="geyser", purity="unknown", resource="Desc_Geyser_C"),
                       NodeState(), name=None)
    assert "geyser" in tip.lower()
    assert "/min" not in tip  # pas de débit de ressource


def _markers(fmap):
    import folium
    return [c for c in fmap._children.values() if isinstance(c, folium.Marker)]


def test_build_folium_map_marker_count_and_filter():
    pytest.importorskip("folium")
    from satisfactory_planner.ui.map_view import build_folium_map

    nodes = load_nodes(FIXTURE)
    assert len(_markers(build_folium_map(nodes, {}))) == len(nodes)
    # Filtre : seulement le minerai de fer (2 nœuds dans la fixture).
    assert len(_markers(build_folium_map(nodes, {}, visible={"Desc_OreIron_C"}))) == 2


def test_build_folium_map_handles_wells_and_geysers():
    pytest.importorskip("folium")
    from satisfactory_planner.ui.map_view import build_folium_map

    nodes = load_nodes(MIXED)  # node + well + geyser
    assert len(_markers(build_folium_map(nodes, {}))) == 3


def test_build_siting_map_has_lines_and_factory():
    folium = pytest.importorskip("folium")
    from satisfactory_planner.siting import Pick, SitingResult, Source
    from satisfactory_planner.ui.map_view import build_siting_map

    s1 = Source(item="Desc_OreIron_C", x=0.0, y=0.0, capacity_per_min=60.0, kind="node")
    s2 = Source(item="Desc_OreCopper_C", x=200.0, y=0.0, capacity_per_min=60.0, kind="node")
    res = SitingResult(
        site=(100.0, 100.0),
        picks=[Pick(s1, 60.0, 1.4), Pick(s2, 30.0, 2.2)], cost=120.0, shortfalls={},
    )
    fmap = build_siting_map(res, names={"Desc_OreIron_C": "Fer", "Desc_OreCopper_C": "Cuivre"})
    polylines = [c for c in fmap._children.values() if isinstance(c, folium.PolyLine)]
    markers = [c for c in fmap._children.values() if isinstance(c, folium.Marker)]
    assert len(polylines) == 2  # une ligne usine -> chaque source
    assert markers  # au moins le pin usine


_PNG_1x1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4"
    "2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_latlng_to_world_is_inverse_of_world_to_latlng():
    from satisfactory_planner.ui.map_view import latlng_to_world, world_to_latlng

    x, y = 6400.0, -12800.0
    lat, lng = world_to_latlng(x, y)
    rx, ry = latlng_to_world(lat, lng)
    assert (round(rx, 6), round(ry, 6)) == (x, y)


def test_build_folium_map_includes_custom_sources():
    pytest.importorskip("folium")
    from satisfactory_planner.nodes.custom import CustomSource
    from satisfactory_planner.ui.map_view import build_folium_map

    nodes = load_nodes(FIXTURE)
    cs = [CustomSource(id="cs1", item="Desc_Plastic_C", rate_per_min=20.0, x=0.0, y=0.0)]
    base = len(_markers(build_folium_map(nodes, {})))
    withcs = len(_markers(build_folium_map(nodes, {}, custom_sources=cs)))
    assert withcs == base + 1


def test_icon_data_uri_reads_local_png(tmp_path):
    import base64

    from satisfactory_planner.ui.map_view import icon_data_uri

    (tmp_path / "Desc_OreIron_C.png").write_bytes(base64.b64decode(_PNG_1x1))
    uri = icon_data_uri("Desc_OreIron_C", icon_dir=tmp_path)
    assert uri.startswith("data:image/png;base64,")
    # ressource sans icône -> None (repli pastille).
    assert icon_data_uri("Desc_Unknown_C", icon_dir=tmp_path) is None
