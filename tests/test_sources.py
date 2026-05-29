from satisfactory_planner.nodes.custom import CustomSource
from satisfactory_planner.nodes.data import ResourceNode
from satisfactory_planner.siting.sources import build_sources


def _node():
    return ResourceNode(id="N", resource="Desc_OreIron_C", purity="pure",
                        form="solid", kind="node", x=0.0, y=0.0, z=0.0)


def test_build_sources_includes_custom_when_item_needed():
    cs = CustomSource(id="cs1", item="Desc_Plastic_C", rate_per_min=20.0, x=500.0, y=500.0)
    srcs = build_sources([_node()], {}, {"Desc_OreIron_C", "Desc_Plastic_C"},
                         custom_sources=[cs])
    plastic = [s for s in srcs if s.item == "Desc_Plastic_C"]
    assert len(plastic) == 1
    assert plastic[0].kind == "factory_output"
    assert plastic[0].capacity_per_min == 20.0
    assert plastic[0].id == "cs1"


def test_build_sources_excludes_custom_when_item_not_needed():
    cs = CustomSource(id="cs1", item="Desc_Plastic_C", rate_per_min=20.0, x=0.0, y=0.0)
    srcs = build_sources([_node()], {}, {"Desc_OreIron_C"}, custom_sources=[cs])
    assert all(s.item != "Desc_Plastic_C" for s in srcs)
