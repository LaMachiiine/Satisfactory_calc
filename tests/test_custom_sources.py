from satisfactory_planner.nodes.custom import (
    add_source,
    load_custom_sources,
    remove_source,
    save_custom_sources,
)


def test_add_source_generates_id_and_fields():
    srcs = add_source([], "Desc_Plastic_C", 20.0, 100.0, 200.0)
    assert len(srcs) == 1
    s = srcs[0]
    assert s.item == "Desc_Plastic_C" and s.rate_per_min == 20.0
    assert (s.x, s.y) == (100.0, 200.0)
    assert s.id


def test_add_source_ids_unique():
    srcs = add_source([], "Desc_Plastic_C", 20.0, 0.0, 0.0)
    srcs = add_source(srcs, "Desc_Plastic_C", 10.0, 1.0, 1.0)
    assert len({s.id for s in srcs}) == 2


def test_remove_source_by_id():
    srcs = add_source([], "Desc_Plastic_C", 20.0, 0.0, 0.0)
    assert remove_source(srcs, srcs[0].id) == []


def test_save_load_round_trip(tmp_path):
    srcs = add_source([], "Desc_Plastic_C", 20.0, 100.0, 200.0)
    p = tmp_path / "custom_sources.json"
    save_custom_sources(srcs, p)
    loaded = load_custom_sources(p)
    assert len(loaded) == 1
    assert loaded[0].model_dump() == srcs[0].model_dump()


def test_load_missing_returns_empty(tmp_path):
    assert load_custom_sources(tmp_path / "nope.json") == []
