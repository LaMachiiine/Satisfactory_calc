from satisfactory_planner.model.repository import Repository
from satisfactory_planner.solver import solve_forward
from satisfactory_planner.ui.sankey import build_sankey


def _value(data, src_name, dst_name):
    i = data.labels.index(src_name)
    j = data.labels.index(dst_name)
    for s, t, v in zip(data.source, data.target, data.value, strict=True):
        if s == i and t == j:
            return v
    return None


def test_build_sankey_flows(sample_docs):
    # 20 plaques : Iron Ore -> Iron Ingot -> Iron Plate, 30/min sur chaque maillon.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronPlate_C": 20})
    data = build_sankey(plan)

    assert _value(data, "Iron Ore", "Iron Ingot") == 30.0
    assert _value(data, "Iron Ingot", "Iron Plate") == 30.0
    # Cohérence des longueurs.
    assert len(data.source) == len(data.target) == len(data.value)


def test_build_sankey_no_duplicate_pairs(sample_docs):
    # Chaque paire (source, cible) n'apparaît qu'une fois (liens agrégés).
    repo = Repository.from_docs(sample_docs, enable_alternates=True)
    plan = solve_forward(repo, {"Desc_IronPlate_C": 20})
    data = build_sankey(plan)
    pairs = list(zip(data.source, data.target, strict=True))
    assert len(pairs) == len(set(pairs))
