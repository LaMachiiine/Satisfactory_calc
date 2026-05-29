from satisfactory_planner.distribution.plan_graph import (
    build_full_belt,
    build_plan_graph,
    build_step_belt,
    build_step_io,
)
from satisfactory_planner.model.entities import Item, Machine, Recipe
from satisfactory_planner.model.repository import Repository
from satisfactory_planner.solver import solve_forward
from satisfactory_planner.solver.result import Plan, PlanStep


def _mkstep(recipe, main, x=1.0, out_rate=60.0):
    return PlanStep(
        recipe=recipe, x=x, machines=1, clock=100.0, power_mw=0.0,
        main_output=main, output_rate=out_rate, per_machine_rate=out_rate,
    )


def _bare_repo(recipes):
    return Repository(items={}, recipes={r.key: r for r in recipes}, machines={}, enabled=set())


def test_plan_graph_reinjects_byproduct():
    # A produit P (principal) + W (sous-produit) ; B consomme W -> Q : W doit être
    # réinjecté depuis l'étape A (pas dessiné comme un brut).
    a = Recipe(key="A", name="A", machine="M", duration_s=60.0,
               inputs={"raw": 1.0}, outputs={"P": 1.0, "W": 2.0})
    b = Recipe(key="B", name="B", machine="M", duration_s=60.0,
               inputs={"W": 1.0}, outputs={"Q": 1.0})
    plan = Plan(
        steps=[_mkstep(a, "P"), _mkstep(b, "Q")],
        raw_consumed={"raw": 1.0}, byproducts={"W": 1.0}, targets={"Q": 1.0},
        item_names={"W": "Eau", "P": "P", "Q": "Q", "raw": "Raw"},
    )
    g = build_plan_graph(plan, _bare_repo([a, b]))
    by_id = {n.id: n for n in g.nodes}
    water_edges = [e for e in g.edges if e.label == "Eau"]
    assert water_edges, "aucune arête d'eau"
    # L'eau vient d'une étape (machine), pas d'un brut (source).
    assert all(by_id[e.src].kind != "source" for e in water_edges)
    # Surplus signalé : un nœud « à évacuer ».
    assert any("évacuer" in n.label for n in g.nodes)


def test_plan_graph_byproduct_water_reinjected_then_surplus_sink():
    # B rejette 2 eau/min (sous-produit), A en consomme 1/min : on **recycle**
    # (l'eau de A vient de B), et le surplus (1/min) part vers un puits.
    a = Recipe(key="A", name="A", machine="M", duration_s=60.0,
               inputs={"W": 1.0}, outputs={"P": 1.0})
    b = Recipe(key="B", name="B", machine="M", duration_s=60.0,
               inputs={"raw": 1.0}, outputs={"Q": 1.0, "W": 2.0})
    repo = Repository(
        items={"W": Item(key="W", name="Eau", is_raw=True),
               "P": Item(key="P", name="P"), "Q": Item(key="Q", name="Q"),
               "raw": Item(key="raw", name="Raw", is_raw=True)},
        recipes={"A": a, "B": b}, machines={}, enabled={"A", "B"},
    )
    plan = Plan(
        steps=[_mkstep(a, "P"), _mkstep(b, "Q")],
        raw_consumed={"raw": 1.0}, byproducts={"W": 1.0}, targets={"P": 1.0},
        item_names={"W": "Eau", "P": "P", "Q": "Q", "raw": "Raw"},
    )
    g = build_plan_graph(plan, repo)
    by_id = {n.id: n for n in g.nodes}
    # L'eau consommée par A est réinjectée depuis l'étape B (pas un brut).
    a_water_in = [e for e in g.edges if e.label == "Eau" and "P" in by_id[e.dst].label]
    assert a_water_in and all(by_id[e.src].kind != "source" for e in a_water_in)
    # Le surplus d'eau (2 produits − 1 consommé) part vers un puits « à évacuer ».
    assert any("évacuer" in n.label and "Eau" in n.label for n in g.nodes)


def test_plan_graph_raw_when_not_produced():
    # Un item produit nulle part reste un brut (nœud source).
    a = Recipe(key="A", name="A", machine="M", duration_s=60.0,
               inputs={"raw": 1.0}, outputs={"P": 1.0})
    plan = Plan(
        steps=[_mkstep(a, "P")], raw_consumed={"raw": 1.0}, byproducts={},
        targets={"P": 1.0}, item_names={"raw": "Raw", "P": "P"},
    )
    g = build_plan_graph(plan, _bare_repo([a]))
    assert any(n.kind == "source" for n in g.nodes)


def _step(machines: int, clock_groups=None):
    # duration 6 s, 1 entrée -> 10/min/machine en sortie et en entrée à 100 %.
    recipe = Recipe(key="R", name="R", machine="M", duration_s=6.0,
                    inputs={"A": 1.0}, outputs={"B": 1.0})
    repo = Repository(
        items={"A": Item(key="A", name="A"), "B": Item(key="B", name="B")},
        recipes={"R": recipe},
        machines={"M": Machine(key="M", name="Maker", base_power_mw=1.0)},
    )
    step = PlanStep(
        recipe=recipe, x=float(machines), machines=machines, clock=100.0,
        power_mw=0.0, main_output="B", output_rate=float(machines) * 10,
        per_machine_rate=10.0, clock_groups=clock_groups or [(machines, 100.0)],
    )
    return step, repo


def test_build_plan_graph_chain(sample_docs):
    # 20 plaques : Iron Ore (source) -> Iron Ingot (step) -> Iron Plate (step).
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronPlate_C": 20})
    g = build_plan_graph(plan, repo)

    # Un nœud par étape + au moins une source (minerai).
    assert g.count("machine") == len(plan.steps) == 2
    assert g.count("source") >= 1

    # Sens production : une arête entre dans chaque étape, étiquetée par l'item.
    labels = {e.label for e in g.edges}
    assert "Iron Ore" in labels
    assert "Iron Ingot" in labels
    # Le produit final (Iron Plate) ne ré-alimente personne : c'est un puits.
    plate = next(n.id for n in g.nodes if "Iron Plate" in n.label)
    assert not any(e.src == plate for e in g.edges)


def test_build_full_belt_connects_steps(sample_docs):
    # Schéma complet : Iron Ore (source) -> machines Iron Ingot -> machines Iron Plate
    # -> produit Iron Plate. Les étapes sont reliées au niveau machine.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronPlate_C": 20})
    g = build_full_belt(plan, repo, plan.item_names)

    assert g.count("machine") == sum(s.machines for s in plan.steps)
    assert any(n.kind == "source" and n.label == "Iron Ore" for n in g.nodes)
    assert any(n.kind == "product" and n.label == "Iron Plate" for n in g.nodes)
    # Un flux « Iron Ingot » relie l'étape lingot à l'étape plaque (inter-étapes).
    assert any(e.label == "Iron Ingot" for e in g.edges)


def test_build_step_io_shows_input_and_output(sample_docs):
    # La vue compacte d'une étape montre l'entrée ET la sortie avec leurs débits.
    repo = Repository.from_docs(sample_docs, enable_alternates=False)
    plan = solve_forward(repo, {"Desc_IronPlate_C": 20})
    plate = next(s for s in plan.steps if s.main_output == "Desc_IronPlate_C")
    g = build_step_io(plate, repo, plan.item_names)

    # Entrée Iron Ingot (source) -> étape -> sortie Iron Plate (product).
    assert any(n.kind == "source" and n.label == "Iron Ingot" for n in g.nodes)
    assert any(n.kind == "product" and n.label == "Iron Plate" for n in g.nodes)
    # Débit d'entrée Iron Ingot = 30/min ; sortie Iron Plate = 20/min.
    rates = {e.label: e.rate for e in g.edges}
    assert rates["Iron Ingot"] == 30.0
    assert rates["Iron Plate"] == 20.0


def _into_product(g):
    out = next(n.id for n in g.nodes if n.kind == "product")
    return round(sum(e.rate for e in g.edges if e.dst == out), 6)


def test_build_step_belt_output_merge():
    step, repo = _step(6)
    g = build_step_belt(step, repo, {"A": "Ay", "B": "Bee"}, layout="balanced")
    assert g.count("machine") == 6
    assert g.count("product") == 1
    assert g.count("merger_2") == 5  # regroupement sortie : 6 -> 3 -> (1+carry) -> 1
    assert _into_product(g) == 60.0  # conservation sortie


def test_build_step_belt_includes_input_distribution():
    # La répartition des entrées vers les machines doit figurer (source + répartiteurs).
    step, repo = _step(6)
    g = build_step_belt(step, repo, {"A": "Ay", "B": "Bee"}, layout="balanced")
    assert any(n.kind == "source" and n.label == "Ay" for n in g.nodes)
    assert g.count("splitter_2") == 5  # arbre de répartition vers 6 machines
    # Total entrant aux machines depuis la source = total produit (10/min/machine).
    machine_ids = {n.id for n in g.nodes if n.kind == "machine"}
    into_machines = round(sum(e.rate for e in g.edges if e.dst in machine_ids), 6)
    assert into_machines == 60.0


def test_build_step_belt_per_machine_clock_labels():
    # Horloge individuelle par machine : 5 machines à 100 % + 1 à 33 %.
    step, repo = _step(6, clock_groups=[(5, 100.0), (1, 33.0)])
    g = build_step_belt(step, repo, {"A": "Ay", "B": "Bee"})
    labels = [n.label for n in g.nodes if n.kind == "machine"]
    assert sum("100%" in lbl for lbl in labels) == 5
    assert sum("33%" in lbl for lbl in labels) == 1


def test_build_step_belt_single_machine_direct():
    step, repo = _step(1)
    g = build_step_belt(step, repo, {"A": "Ay", "B": "Bee"})
    assert g.count("merger_2") == 0
    assert g.count("splitter_2") == 0  # 1 machine : liaisons directes
    assert _into_product(g) == 10.0


def test_build_step_belt_balanced_shallower_than_linear():
    step, repo = _step(8)

    def depth(g):
        out = next(n.id for n in g.nodes if n.kind == "product")
        preds = {}
        for e in g.edges:
            preds.setdefault(e.dst, []).append(e.src)

        def d(node):
            return 0 if node not in preds else 1 + max(d(p) for p in preds[node])

        return d(out)

    bal = depth(build_step_belt(step, repo, {"A": "A", "B": "B"}, layout="balanced"))
    lin = depth(build_step_belt(step, repo, {"A": "A", "B": "B"}, layout="linear"))
    assert bal < lin


def test_custom_source_renders_as_blue_square():
    from satisfactory_planner.distribution.graph import DistributionGraph
    g = DistributionGraph()
    g.add_node("custom_source", label="\U0001f3ed Plastic")
    dot = g.to_dot()
    assert "#5b9bd5" in dot  # carre bleu plein, distinct du brut naturel


def test_build_plan_graph_marks_external_input_as_custom_source():
    a = Recipe(key="A", name="A", machine="M", duration_s=60.0,
               inputs={"ext": 1.0}, outputs={"P": 1.0})
    plan = Plan(steps=[_mkstep(a, "P")], raw_consumed={"ext": 1.0}, byproducts={},
                targets={"P": 1.0}, item_names={"ext": "Plastic", "P": "P"})
    g = build_plan_graph(plan, _bare_repo([a]), external_items={"ext"})
    assert any(n.kind == "custom_source" for n in g.nodes)
    assert not any(n.kind == "source" for n in g.nodes)
    # Sans external_items : l'item non produit reste un brut (source).
    g2 = build_plan_graph(plan, _bare_repo([a]))
    assert any(n.kind == "source" for n in g2.nodes)
    assert not any(n.kind == "custom_source" for n in g2.nodes)


def test_build_step_io_marks_external_input():
    step, repo = _step(1)
    g = build_step_io(step, repo, {"A": "Ay", "B": "Bee"}, external_items={"A"})
    assert any(n.kind == "custom_source" and "Ay" in n.label for n in g.nodes)
    assert not any(n.kind == "source" for n in g.nodes)


def test_build_step_belt_marks_external_input():
    step, repo = _step(6)
    g = build_step_belt(step, repo, {"A": "Ay", "B": "Bee"}, external_items={"A"})
    assert any(n.kind == "custom_source" for n in g.nodes)
    assert not any(n.kind == "source" for n in g.nodes)


def test_build_plan_graph_splits_partial_external_source():
    from satisfactory_planner.solver import solve_forward
    items = {"Ore": Item(key="Ore", name="Ore", is_raw=True),
             "Mid": Item(key="Mid", name="Mid"),
             "Out": Item(key="Out", name="Out")}
    recipes = {"R1": Recipe(key="R1", name="R1", machine="M", duration_s=60.0,
                            inputs={"Ore": 1.0}, outputs={"Mid": 1.0}),
               "R2": Recipe(key="R2", name="R2", machine="M", duration_s=60.0,
                            inputs={"Mid": 1.0}, outputs={"Out": 1.0})}
    repo = Repository(items=items, recipes=recipes,
                      machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
                      enabled={"R1", "R2"})
    # 4 Mid fournis en externe, 6 produits en interne, 10 consommes par R2.
    plan = solve_forward(repo, {"Out": 10.0}, available={"Mid": 4.0})
    g = build_plan_graph(plan, repo, external_items={"Mid"})
    by_id = {n.id: n for n in g.nodes}
    mid_edges = [e for e in g.edges if e.label == "Mid"]
    kinds = {by_id[e.src].kind for e in mid_edges}
    assert "custom_source" in kinds and "machine" in kinds  # part externe + part interne
    ext = sum(e.rate for e in mid_edges if by_id[e.src].kind == "custom_source")
    intern = sum(e.rate for e in mid_edges if by_id[e.src].kind == "machine")
    assert ext == 4.0 and intern == 6.0


def test_build_plan_graph_two_producers_split_no_orphan():
    # Deux recettes produisent le meme item (36 + 54 = 90) : 2 noeuds distincts,
    # aucun orphelin, et le consommateur tire des deux.
    r1 = Recipe(key="R1", name="R1", machine="M", duration_s=60.0,
                inputs={"raw": 1.0}, outputs={"Ing": 1.0})
    r2 = Recipe(key="R2", name="R2", machine="M", duration_s=60.0,
                inputs={"raw": 1.0}, outputs={"Ing": 1.0})
    rc = Recipe(key="RC", name="RC", machine="M", duration_s=60.0,
                inputs={"Ing": 1.0}, outputs={"Cas": 1.0})
    plan = Plan(
        steps=[_mkstep(r1, "Ing", x=36.0, out_rate=36.0),
               _mkstep(r2, "Ing", x=54.0, out_rate=54.0),
               _mkstep(rc, "Cas", x=90.0, out_rate=90.0)],
        raw_consumed={"raw": 90.0}, byproducts={}, targets={"Cas": 90.0},
        item_names={"raw": "Raw", "Ing": "Ingot", "Cas": "Casing"},
    )
    g = build_plan_graph(plan, _bare_repo([r1, r2, rc]))
    machine_nodes = [n for n in g.nodes if n.kind == "machine"]
    assert len(machine_nodes) == 3  # un noeud par recette (pas de collision)
    for n in machine_nodes:  # aucun orphelin
        assert any(e.src == n.id or e.dst == n.id for e in g.edges)
    ing_edges = sorted(round(e.rate) for e in g.edges if e.label == "Ingot")
    assert ing_edges == [36, 54]  # consommateur tire des deux producteurs


def test_to_dot_merges_opposing_edges_into_double_arrow():
    from satisfactory_planner.distribution.graph import DistributionGraph
    g = DistributionGraph()
    a = g.add_node("machine", "A")
    b = g.add_node("machine", "B")
    g.add_edge(a, b, 108.0, "Alumina")
    g.add_edge(b, a, 162.0, "Water", recycled=True)
    dot = g.to_dot()
    assert "dir=both" in dot          # double fleche
    assert "Alumina" in dot and "Water" in dot
    assert "162" in dot and "108" in dot  # debit dans chaque sens


def test_to_dot_styles_recycled_single_edge():
    from satisfactory_planner.distribution.graph import DistributionGraph
    g = DistributionGraph()
    a = g.add_node("machine", "A")
    b = g.add_node("machine", "B")
    g.add_edge(a, b, 5.0, "W", recycled=True)
    assert "style=dashed" in g.to_dot()
