"""Vue globale d'un plan : toute la chaîne de production en un seul graphe.

Chaque étape (recette) devient un nœud ; les arêtes portent les flux d'items
entre étapes (et depuis les bruts), dans le **sens de production** (bruts ->
intermédiaires -> produit final).
"""

from __future__ import annotations

from ..model.repository import Repository
from ..solver.result import Plan
from .graph import DistributionGraph


def _add_input_node(graph, item_key: str, name: str, external) -> str:
    """Nœud d'entrée : carré bleu 🏭 (source perso) si `item_key` est externe, sinon brut."""
    if external and item_key in external:
        return graph.add_node("custom_source", label=f"🏭 {name}")
    return graph.add_node("source", label=name)


def build_step_io(
    step, repo: Repository, item_names: dict[str, str], external_items=None
) -> DistributionGraph:
    """Schéma compact d'une étape : entrées → bloc machine → sorties (avec débits).

    `external_items` : items fournis par une source perso → marqués 🏭 (carré bleu).
    """
    graph = DistributionGraph(item_key=step.main_output)
    machine = repo.machines.get(step.recipe.machine)
    mname = machine.name if machine else step.recipe.machine
    center = graph.add_node(
        "machine",
        label=f"{step.recipe.name}\\n{mname} ×{step.machines} @ {step.clock_label()}",
    )
    dur = step.recipe.duration_s
    for in_key, qty in step.recipe.inputs.items():
        rate = round(step.x * qty * 60.0 / dur, 6)
        name = item_names.get(in_key, in_key)
        node = _add_input_node(graph, in_key, name, external_items)
        graph.add_edge(node, center, rate, label=name)
    for out_key, qty in step.recipe.outputs.items():
        rate = round(step.x * qty * 60.0 / dur, 6)
        node = graph.add_node("product", label=item_names.get(out_key, out_key))
        graph.add_edge(center, node, rate, label=item_names.get(out_key, out_key))
    return graph


def _balanced_merge(graph, items, label=""):
    """Fusionne par paires en cascade équilibrée. items: [(node_id, rate)]."""
    level = list(items)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            chunk = level[i:i + 2]
            if len(chunk) == 1:
                nxt.append(chunk[0])  # nombre impair : remonte tel quel
                continue
            merger = graph.add_node("merger_2")
            total = chunk[0][1] + chunk[1][1]
            graph.add_edge(chunk[0][0], merger, chunk[0][1], label)
            graph.add_edge(chunk[1][0], merger, chunk[1][1], label)
            nxt.append((merger, total))
        level = nxt
    return level[0]


def _linear_merge(graph, items, label=""):
    """Lignes droites : machines appairées (2 par groupeur) puis cascade sur un bus."""
    # 1. Paires de machines : 2 machines par groupeur (impair -> 1 machine remonte).
    pairs = []
    for i in range(0, len(items), 2):
        chunk = items[i:i + 2]
        if len(chunk) == 1:
            pairs.append(chunk[0])
            continue
        merger = graph.add_node("merger_2")
        total = chunk[0][1] + chunk[1][1]
        graph.add_edge(chunk[0][0], merger, chunk[0][1], label)
        graph.add_edge(chunk[1][0], merger, chunk[1][1], label)
        pairs.append((merger, total))

    # 2. Bus : cascade des sorties de paires le long d'un tronçon.
    prev, acc = pairs[0]
    for node, rate in pairs[1:]:
        merger = graph.add_node("merger_2")
        graph.add_edge(prev, merger, acc, label)
        graph.add_edge(node, merger, rate, label)
        acc += rate
        prev = merger
    return prev, acc


def _balanced_split(graph, source, leaves, label=""):
    """Arbre de répartiteurs équilibré : source -> ... -> feuilles (machines)."""
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            chunk = level[i:i + 2]
            if len(chunk) == 1:
                nxt.append(chunk[0])
                continue
            splitter = graph.add_node("splitter_2")
            total = chunk[0][1] + chunk[1][1]
            graph.add_edge(splitter, chunk[0][0], chunk[0][1], label)
            graph.add_edge(splitter, chunk[1][0], chunk[1][1], label)
            nxt.append((splitter, total))
        level = nxt
    root, total = level[0]
    graph.add_edge(source, root, total, label)


def _linear_split(graph, source, leaves, label=""):
    """Lignes droites : 2 machines par répartiteur, alimentées par un bus."""
    pairs = []
    for i in range(0, len(leaves), 2):
        chunk = leaves[i:i + 2]
        if len(chunk) == 1:
            pairs.append(chunk[0])
            continue
        splitter = graph.add_node("splitter_2")
        total = chunk[0][1] + chunk[1][1]
        graph.add_edge(splitter, chunk[0][0], chunk[0][1], label)
        graph.add_edge(splitter, chunk[1][0], chunk[1][1], label)
        pairs.append((splitter, total))

    prev = source
    remaining = sum(rate for _, rate in pairs)
    for i, (node, rate) in enumerate(pairs):
        if i == len(pairs) - 1:
            graph.add_edge(prev, node, rate, label)  # dernier : tout le reste
        else:
            bus = graph.add_node("splitter_2")
            graph.add_edge(prev, bus, remaining, label)
            graph.add_edge(bus, node, rate, label)
            remaining -= rate
            prev = bus


def build_step_belt(
    step, repo: Repository, item_names: dict[str, str],
    belt_capacity: float = 0.0, layout: str = "balanced", external_items=None,
) -> DistributionGraph:
    """Détail tapis complet d'une étape : entrées -> répartiteurs -> machines ->
    groupeurs -> sortie.

    `layout="balanced"` : arbres équilibrés (2 machines par nœud, lignes
    parallèles) ; `"linear"` : lignes droites (paires + bus).
    """
    graph = DistributionGraph(item_key=step.main_output, belt_capacity=belt_capacity)
    machine = repo.machines.get(step.recipe.machine)
    mname = machine.name if machine else step.recipe.machine
    n = step.machines
    dur = step.recipe.duration_s
    split = _linear_split if layout == "linear" else _balanced_split
    merge = _linear_merge if layout == "linear" else _balanced_merge

    # Horloge individuelle de chaque machine (ex. 5×100% + 1×33% -> [100,100,100,100,100,33]).
    clocks = _machine_clocks(step)
    machines = [graph.add_node("machine", label=f"{mname}\\n{c:.0f}%") for c in clocks]

    # Entrées : chaque item réparti vers les machines (débit ∝ horloge de la machine).
    for in_key, qty in step.recipe.inputs.items():
        per_100 = qty * 60.0 / dur
        leaves = [(machines[i], round(per_100 * clocks[i] / 100.0, 6)) for i in range(n)]
        name = item_names.get(in_key, in_key)
        src = _add_input_node(graph, in_key, name, external_items)
        if n == 1:
            graph.add_edge(src, machines[0], leaves[0][1], name)
        else:
            split(graph, src, leaves, name)

    # Sortie principale : regroupement (débit ∝ horloge de la machine).
    out_100 = step.recipe.outputs[step.main_output] * 60.0 / dur
    out_leaves = [(machines[i], round(out_100 * clocks[i] / 100.0, 6)) for i in range(n)]
    out_name = item_names.get(step.main_output, step.main_output)
    out = graph.add_node("product", label=out_name)
    if n == 1:
        graph.add_edge(machines[0], out, out_leaves[0][1], out_name)
    else:
        final, total = merge(graph, out_leaves, out_name)
        graph.add_edge(final, out, total, out_name)
    return graph


def _machine_clocks(step) -> list[float]:
    clocks: list[float] = []
    for count, clk in (step.clock_groups or [(step.machines, step.clock)]):
        clocks.extend([clk] * count)
    if len(clocks) != step.machines:  # garde-fou
        clocks = [step.clock] * step.machines
    return clocks


def build_full_belt(
    plan: Plan, repo: Repository, item_names: dict[str, str],
    belt_capacity: float = 0.0, layout: str = "balanced",
) -> DistributionGraph:
    """Schéma complet de l'usine au niveau machine : sources/étapes amont ->
    répartiteurs -> machines -> groupeurs -> étapes aval -> produit final.

    Toutes les étapes sont reliées : la sortie regroupée d'une étape alimente la
    répartition des entrées des étapes qui la consomment.
    """
    graph = DistributionGraph(item_key="usine", belt_capacity=belt_capacity)
    split = _linear_split if layout == "linear" else _balanced_split
    merge = _linear_merge if layout == "linear" else _balanced_merge

    # 1. Machines de chaque étape (horloge individuelle).
    step_machines: dict[str, list[tuple[str, float]]] = {}
    for step in plan.steps:
        machine = repo.machines.get(step.recipe.machine)
        mname = machine.name if machine else step.recipe.machine
        clocks = _machine_clocks(step)
        step_machines[step.recipe.key] = [
            (graph.add_node("machine", label=f"{mname}\\n{c:.0f}%"), c) for c in clocks
        ]

    # 2. Regroupement de la sortie de chaque étape -> « hub » de l'item produit.
    item_hub: dict[str, str] = {}
    for step in plan.steps:
        dur = step.recipe.duration_s
        out_100 = step.recipe.outputs[step.main_output] * 60.0 / dur
        leaves = [
            (node, round(out_100 * c / 100.0, 6))
            for node, c in step_machines[step.recipe.key]
        ]
        out_name = item_names.get(step.main_output, step.main_output)
        if len(leaves) == 1:
            item_hub[step.main_output] = leaves[0][0]
        else:
            final, _ = merge(graph, leaves, out_name)
            item_hub[step.main_output] = final

    # 3. Consommateurs de chaque item (toutes étapes confondues).
    consumers: dict[str, list[tuple[str, float]]] = {}
    for step in plan.steps:
        dur = step.recipe.duration_s
        for in_key, qty in step.recipe.inputs.items():
            in_100 = qty * 60.0 / dur
            for node, c in step_machines[step.recipe.key]:
                consumers.setdefault(in_key, []).append(
                    (node, round(in_100 * c / 100.0, 6))
                )

    # 4. Répartition de chaque item depuis son hub (étape amont) ou un brut.
    for item, cons in consumers.items():
        name = item_names.get(item, item)
        hub = item_hub.get(item) or graph.add_node("source", label=name)
        if len(cons) == 1:
            graph.add_edge(hub, cons[0][0], cons[0][1], name)
        else:
            split(graph, hub, cons, name)

    # 5. Produits finaux (non consommés) -> nœud produit.
    for step in plan.steps:
        main = step.main_output
        if main not in consumers:
            name = item_names.get(main, main)
            out = graph.add_node("product", label=name)
            graph.add_edge(item_hub[main], out, round(step.output_rate, 6), name)

    return graph


def build_plan_graph(plan: Plan, repo: Repository, external_items=None) -> DistributionGraph:
    """Construit le graphe global du plan (étapes + flux inter-étapes).

    `external_items` : items fournis par une source perso → marqués 🏭 (carré bleu)
    au lieu d'un brut naturel.
    """
    graph = DistributionGraph(item_key="plan")
    ext_items = external_items or set()

    # Un nœud par RECETTE (clé unique) : si deux recettes produisent le même item
    # (recette standard + alternative), chacune garde son nœud (pas de collision).
    step_node: dict[str, str] = {}
    for step in plan.steps:
        machine = repo.machines.get(step.recipe.machine)
        mname = machine.name if machine else step.recipe.machine
        item = plan.item_names.get(step.main_output, step.main_output)
        label = (
            f"{step.recipe.name}\\n{mname} ×{step.machines} @ {step.clock_label()}"
            f"\\n{item} {step.output_rate:g}/min"
        )
        step_node[step.recipe.key] = graph.add_node("machine", label=label)

    # Producteurs (nœud, débit, principal/sous-produit) et consommation, par item.
    producers: dict[str, list[tuple[str, float, bool]]] = {}
    consumed: dict[str, float] = {}
    for step in plan.steps:
        dur = step.recipe.duration_s
        node = step_node[step.recipe.key]
        for out_key, qty in step.recipe.outputs.items():
            producers.setdefault(out_key, []).append(
                (node, step.x * qty * 60.0 / dur, out_key == step.main_output)
            )
        for in_key, qty in step.recipe.inputs.items():
            consumed[in_key] = consumed.get(in_key, 0.0) + step.x * qty * 60.0 / dur

    supply_node: dict[str, str] = {}

    def _supply(key: str) -> str:
        if key not in supply_node:
            name = plan.item_names.get(key, key)
            supply_node[key] = _add_input_node(graph, key, name, ext_items)
        return supply_node[key]

    # Chaque entrée est répartie, au prorata, entre ses producteurs internes
    # (sous-produit → **recyclage**), la **source perso** (externe) et l'**extraction**
    # (brut). Gère naturellement : plusieurs producteurs d'un même item, et le panachage
    # interne/externe partiel.
    for step in plan.steps:
        dst = step_node[step.recipe.key]
        dur = step.recipe.duration_s
        for in_key, qty in step.recipe.inputs.items():
            r = round(step.x * qty * 60.0 / dur, 6)
            name = plan.item_names.get(in_key, in_key)
            prods = producers.get(in_key, [])
            internal = sum(rate for _, rate, _ in prods)
            external = plan.raw_consumed.get(in_key, 0.0) if in_key in ext_items else 0.0
            need = consumed.get(in_key) or r
            denom = internal + external
            if denom <= 1e-9:  # uniquement produit nulle part → 100 % brut
                graph.add_edge(_supply(in_key), dst, r, label=name)
                continue
            scale = min(need, denom) / need  # part couverte par interne + externe
            for pnode, prate, is_main in prods:
                er = round(r * (prate / denom) * scale, 6)
                if er > 1e-9:
                    graph.add_edge(pnode, dst, er, label=name, recycled=not is_main)
            if external > 1e-9:
                er = round(r * (external / denom) * scale, 6)
                if er > 1e-9:
                    graph.add_edge(_supply(in_key), dst, er, label=name)
            raw_r = round(r * max(0.0, 1.0 - denom / need), 6)  # complément depuis brut
            if raw_r > 1e-9:
                graph.add_edge(_supply(in_key), dst, raw_r, label=name)

    # Surplus : produit au-delà du consommé (hors cible) → puits « à évacuer ».
    for item, plist in producers.items():
        surplus = sum(rate for _, rate, _ in plist) - consumed.get(item, 0.0)
        if surplus > 1e-6 and item not in plan.targets:
            name = plan.item_names.get(item, item)
            sink = graph.add_node("product", label=f"{name}\\n♻ surplus à évacuer")
            main_node = next((n for n, _, m in plist if m), plist[0][0])
            graph.add_edge(main_node, sink, round(surplus, 6), label=name)

    return graph
