"""Interface Streamlit (§8) : modes direct/inverse, objectifs, alternatives,
Somersloop, plan, Sankey et graphes de distribution.

Lancer :  uv run --extra ui streamlit run src/satisfactory_planner/ui/app.py
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from satisfactory_planner.data import game_constants
from satisfactory_planner.distribution import (
    build_plan_graph,
    build_step_belt,
    build_step_io,
)
from satisfactory_planner.model.repository import Repository
from satisfactory_planner.nodes import (
    DEFAULT_CUSTOM_PATH,
    NodeState,
    add_source,
    available_caps,
    load_custom_sources,
    load_nodes,
    load_states,
    remove_source,
    save_custom_sources,
)
from satisfactory_planner.siting import build_sources, locate_factory
from satisfactory_planner.solver import (
    OBJECTIVES,
    allocate_somersloops,
    solve_forward,
    solve_max_output,
)
from satisfactory_planner.transport import decision_grid, recommend
from satisfactory_planner.ui import map_view
from satisfactory_planner.ui.graph_view import render_dot
from satisfactory_planner.ui.sankey import build_sankey

DOCS_DEFAULT = "data/Docs.json"

st.set_page_config(page_title="Satisfactory Planner", layout="wide")


@st.cache_resource(show_spinner="Chargement du Docs.json…")
def load_repo(docs_path: str) -> Repository:
    # Toutes les recettes sont parsées (alternates incluses) ; l'activation se fait
    # ensuite via repo.with_recipes_enabled selon la sélection de l'utilisateur.
    return Repository.from_docs(docs_path, enable_alternates=True)


def _produced_items(repo: Repository) -> dict[str, str]:
    """Nom affiché -> clé, pour les items produits par une recette activée."""
    keys = {o for r in repo.enabled_recipes() for o in r.outputs if o in repo.items}
    return {repo.items[k].name: k for k in keys}


def _plan_table(plan) -> list[dict]:
    rows = []
    for s in sorted(plan.steps, key=lambda s: s.recipe.name):
        rows.append({
            "Recette": s.recipe.name,
            "Machines": s.machines,
            "Horloge": s.clock_label(),
            "Débit/min": round(s.output_rate, 2),
            "Puissance MW": round(s.power_mw, 2),
            "Sloops": s.somersloops or "",
        })
    return rows


def _sankey_figure(plan) -> go.Figure:
    data = build_sankey(plan)
    return go.Figure(
        go.Sankey(
            node={"label": data.labels, "pad": 14, "thickness": 16},
            link={"source": data.source, "target": data.target, "value": data.value},
        )
    )


def render() -> None:
    st.title("🏭 Satisfactory Planner")

    sb = st.sidebar
    sb.header("Paramètres")
    docs_path = sb.text_input("Docs.json", DOCS_DEFAULT)

    try:
        repo = load_repo(docs_path)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Impossible de charger {docs_path} : {exc}")
        st.stop()

    # Sélection granulaire des recettes alternatives (vide = standard uniquement).
    alt_by_name = {r.name: k for k, r in repo.recipes.items() if r.is_alternate}
    chosen_alt = sb.multiselect(
        "Recettes alternatives autorisées", sorted(alt_by_name), default=[],
        help="Choisis individuellement les alternatives à autoriser. "
        "Vide = recettes standard uniquement.",
    )
    work = repo.with_recipes_enabled([alt_by_name[n] for n in chosen_alt])
    # Liste d'items cible depuis le catalogue COMPLET (toutes recettes) : stable quand
    # on (dé)coche des alternatives, donc la sélection n'est pas réinitialisée. Le
    # solveur utilise `work` (recettes activées) pour calculer le plan.
    item_catalog = _produced_items(repo)

    realize_labels = {
        "Uniforme (min puissance)": "uniform",
        "Max à 100 % + reste": "max100",
        "Overclock (≤ 250 %)": "overclock",
    }
    realize = realize_labels[sb.selectbox(
        "Réalisation machines", list(realize_labels), index=1,  # défaut : max100
        help=(
            "Comment réaliser un nombre fractionnaire de machines :\n\n"
            "• **Uniforme** : ceil(x) machines, toutes à la même horloge x/ceil(x). "
            "Minimise la puissance (courbe convexe), sans Power Shard.\n\n"
            "• **Max à 100 %** : floor(x) machines à 100 % + 1 au reliquat. "
            "Plus de machines pleines, puissance légèrement supérieure.\n\n"
            "• **Overclock** : le moins de machines possible en surcadençant jusqu'à "
            "250 %. Coûte des Power Shards, puissance fortement accrue."
        ),
    )]

    tab_plan, tab_map, tab_loc = st.tabs(
        ["🏭 Planificateur", "🗺️ Carte gisements", "📍 Localisation"]
    )
    with tab_plan:
        _planner_tab(work, sb, realize, item_catalog)
    with tab_map:
        _map_tab(repo)
    with tab_loc:
        _locate_tab(repo)


def _planner_tab(repo: Repository, sb, realize: str, items: dict[str, str]) -> None:
    mode = sb.radio(
        "Mode", ["Direct (forward)", "Inverse (max output)"], index=0, key="planner_mode"
    )
    item_name = sb.selectbox(
        "Item cible", sorted(items), index=None, placeholder="Choisis un item cible…",
        key="planner_target",
    )
    if item_name is None:
        st.info("Choisis un **item cible** dans la barre latérale pour calculer un plan.")
        st.session_state.pop("plan_demand", None)
        return
    target_key = items[item_name]

    custom = load_custom_sources(DEFAULT_CUSTOM_PATH)
    custom_caps: dict[str, float] = {}
    if custom:
        use_custom = sb.checkbox(
            "Utiliser mes sources perso comme entrées disponibles",
            value=False, key="use_custom_sources",
            help="Le solveur peut consommer ces items (jusqu'au débit posé) au lieu "
            "de les fabriquer ; la localisation les utilisera comme sources.",
        )
        if use_custom:
            for s in custom:
                custom_caps[s.item] = custom_caps.get(s.item, 0.0) + s.rate_per_min
    custom_caps.pop(target_key, None)  # on ne « fournit » pas l'item cible lui-même
    external_items = set(custom_caps)  # items à marquer 🏭 (carré bleu) dans les graphes

    plan = None
    try:
        if mode.startswith("Direct"):
            rate = sb.number_input(
                "Débit voulu (/min)", min_value=0.1, value=60.0, step=10.0, key="fwd_rate"
            )
            objective = sb.selectbox(
                "Objectif", OBJECTIVES, key="fwd_objective",
                help=(
                    "Critère que le solveur minimise :\n\n"
                    "• **min_raw** : minimise l'extraction totale de ressources brutes.\n\n"
                    "• **min_power** : minimise la puissance (Σ machines × puissance de base).\n\n"
                    "• **min_machines** : minimise le nombre de machines."
                ),
            )
            sloops = sb.number_input(
                "Budget Somersloops", min_value=0, value=0, step=1, key="fwd_sloops"
            )
            plan = solve_forward(
                repo, {target_key: rate}, objective=objective,
                available=custom_caps or None, realize_strategy=realize,
            )
            if sloops > 0:
                allocate_somersloops(plan, repo, int(sloops))
        else:
            source = sb.radio(
                "Source des bruts", ["Gisements de la carte", "Saisie manuelle"], index=0,
                key="inv_source",
                help="Carte : Σ débit max des gisements disponibles (onglet Carte). "
                "Manuelle : déclare toi-même les bruts et leurs débits.",
            )
            if source.startswith("Gisements"):
                nodes = load_nodes()
                states = load_states(map_view.DEFAULT_STATE_PATH)
                available = available_caps(nodes, states)
                if available:
                    st.caption("Bruts disponibles (gisements de la carte, /min) :")
                    st.dataframe(
                        [{"Brut": repo.items[k].name if k in repo.items else k,
                          "/min": round(v, 1)}
                         for k, v in sorted(available.items(),
                                            key=lambda kv: repo.items[kv[0]].name
                                            if kv[0] in repo.items else kv[0])],
                        use_container_width=True, hide_index=True,
                    )
            else:
                raws = sorted(
                    (k for k, it in repo.items.items() if it.is_raw),
                    key=lambda k: repo.items[k].name,
                )
                raw_names = {repo.items[k].name: k for k in raws}
                chosen = sb.multiselect("Bruts disponibles", sorted(raw_names), key="inv_raws")
                available = {}
                for name in chosen:
                    available[raw_names[name]] = sb.number_input(
                        f"{name} (/min)", min_value=0.0, value=480.0, step=60.0, key=name
                    )
            if not available:
                st.info("Aucun brut disponible : configure des gisements (carte) "
                        "ou passe en saisie manuelle.")
                st.stop()
            plan = solve_max_output(
                repo, target_key, {**available, **custom_caps}, realize_strategy=realize
            )
            st.metric(f"Sortie max — {item_name}", f"{plan.targets[target_key]:.2f} /min")
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    # Demande (bruts requis) exposée à l'onglet Localisation (Phase 6).
    st.session_state["plan_demand"] = {
        "raws": dict(plan.raw_consumed), "names": dict(plan.item_names),
    }

    # --- Plan ---
    st.subheader("Plan de production")
    st.metric("Puissance totale", f"{plan.power_total_mw:.2f} MW")
    st.dataframe(_plan_table(plan), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        if plan.raw_consumed:
            st.caption("Bruts consommés (/min)")
            st.dataframe(
                [{"Brut": plan.item_names.get(k, k), "/min": round(v, 2)}
                 for k, v in sorted(plan.raw_consumed.items())],
                use_container_width=True, hide_index=True,
            )
    with col2:
        if plan.byproducts:
            st.caption("Sous-produits (surplus, /min)")
            st.dataframe(
                [{"Item": plan.item_names.get(k, k), "/min": round(v, 2)}
                 for k, v in sorted(plan.byproducts.items())],
                use_container_width=True, hide_index=True,
            )

    # --- Vue globale (chaîne complète) ---
    st.subheader("Chaîne complète")
    st.caption("Vue d'ensemble (1 nœud par étape) : bruts → intermédiaires → produit "
               "final. Le détail se lit étape par étape ci-dessous.")
    render_dot(build_plan_graph(plan, repo, external_items).to_dot(), height=540)

    # --- Sankey ---
    st.subheader("Flux (Sankey)")
    st.plotly_chart(_sankey_figure(plan), use_container_width=True)

    # --- Distribution par étape ---
    st.subheader("Distribution par étape")
    c1, c2, c3 = st.columns([2, 2, 1])
    tier = c1.select_slider("Tier de tapis", options=[1, 2, 3, 4, 5, 6], value=3)
    layout = "linear" if c2.selectbox(
        "Disposition du détail", ["Équilibré", "Linéaire"],
        help="Équilibré : arbre de fusion (2 machines par groupeur, lignes parallèles). "
        "Linéaire : cascade le long d'un tronçon.",
    ) == "Linéaire" else "balanced"
    capacity = game_constants.BELTS[tier - 1].capacity_per_min
    expand_all = c3.checkbox("Tout déplier", value=False)
    st.caption(
        f"Capacité Mk.{tier} = {capacity:g}/min — les sorties des machines se "
        "regroupent via des groupeurs ⊕."
    )

    # Détail tapis (regroupement) par étape.
    gathers = []
    for step in plan.steps:
        machine = repo.machines.get(step.recipe.machine)
        mname = machine.name if machine else step.recipe.machine
        item_name = plan.item_names.get(step.main_output, step.main_output)
        graph = build_step_belt(step, repo, plan.item_names, capacity, layout,
                                external_items=external_items)
        gathers.append((step, item_name, mname, graph))

    # Vue d'ensemble.
    st.dataframe(
        [{
            "Item": item_name,
            "Machine": mname,
            "Nb": step.machines,
            "Horloge": step.clock_label(),
            "Débit/min": round(step.output_rate, 2),
            "Groupeurs": g.count("merger_2") + g.count("merger_3"),
            "Charge max/min": round(max((e.rate for e in g.edges), default=0), 2),
            "⚠ capacité": "oui" if g.over_capacity_edges() else "",
        } for step, item_name, mname, g in gathers],
        use_container_width=True, hide_index=True,
    )

    # Vue locale (dépliable par étape).
    for step, item_name, mname, graph in gathers:
        title = (
            f"{item_name} — {mname} ×{step.machines} @ {step.clock_label()}, "
            f"{step.output_rate:g}/min"
        )
        with st.expander(title, expanded=expand_all):
            # Vue compacte : entrées -> bloc machine -> sorties (lisible).
            render_dot(
                build_step_io(step, repo, plan.item_names,
                              external_items=external_items).to_dot(),
                height=360,
            )
            # Détail tapis (regroupement, 1 nœud/machine) sur demande.
            if st.checkbox("Détail tapis (regroupement)", key=f"belt_{step.recipe.key}"):
                render_dot(graph.to_dot(), height=540)
                st.text(graph.report())
                d1, d2 = st.columns(2)
                d1.download_button(
                    "⬇ DOT", graph.to_dot(), f"{step.recipe.key}.dot",
                    key=f"dot_{step.recipe.key}",
                )
                d2.download_button(
                    "⬇ JSON", graph.to_json(), f"{step.recipe.key}.json",
                    key=f"json_{step.recipe.key}",
                )


def _map_tab(repo: Repository) -> None:
    """Onglet carte des gisements (§5bis) : visualisation + toggle disponibilité."""
    nodes = load_nodes()
    states = load_states(map_view.DEFAULT_STATE_PATH)
    # Noms propres des ressources (depuis Docs.json) ; libellés de repli sinon.
    fallback = {"Desc_Geyser_C": "Geyser"}
    names = {
        n.resource: (
            repo.items[n.resource].name if n.resource in repo.items
            else fallback.get(n.resource, n.resource)
        )
        for n in nodes
    }

    st.subheader("Carte des gisements")
    custom = load_custom_sources(DEFAULT_CUSTOM_PATH)
    # Noms d'items (catalogue) pour l'ajout de sources perso + tooltips 🏭.
    item_names = {repo.items[k].name: k for k in repo.items}
    cs_names = {**names, **{k: repo.items[k].name for k in repo.items}}

    map_mode = st.radio(
        "Mode carte", ["Disponibilité gisements", "➕ Ajouter une source"],
        horizontal=True, key="map_mode",
    )

    # Filtre d'affichage par ressource (noms propres).
    by_name = {names[k]: k for k in names}
    chosen = st.multiselect(
        "Ressources affichées", sorted(by_name), default=sorted(by_name),
        help="Décoche pour masquer une ressource sur la carte et dans les plafonds.",
        key="map_visible",
    )
    visible = {by_name[n] for n in chosen}

    shown = [n for n in nodes if n.resource in visible]
    avail_count = sum(1 for n in shown if (states.get(n.id) or NodeState()).available)
    st.caption(f"{len(shown)} gisements affichés ({avail_count} disponibles).")

    if map_mode.startswith("➕"):
        c1, c2 = st.columns([3, 1])
        sel_name = c1.selectbox("Item de la source", sorted(item_names), key="cs_item")
        rate = c2.number_input("Débit (/min)", min_value=0.1, value=20.0, step=10.0,
                               key="cs_rate")
        pos = map_view.render_placement(nodes, states, cs_names, visible, custom)
        if pos is not None and sel_name:
            custom = add_source(custom, item_names[sel_name], rate, pos[0], pos[1])
            save_custom_sources(custom, DEFAULT_CUSTOM_PATH)
            st.rerun()
        if custom:
            st.caption("Sources personnalisées :")
            for s in custom:
                nm = repo.items[s.item].name if s.item in repo.items else s.item
                lc, rc = st.columns([5, 1])
                lc.write(f"🏭 {nm} — {s.rate_per_min:g}/min @ ({s.x:.0f}, {s.y:.0f})")
                if rc.button("🗑", key=f"del_{s.id}"):
                    custom = remove_source(custom, s.id)
                    save_custom_sources(custom, DEFAULT_CUSTOM_PATH)
                    st.rerun()
    else:
        map_view.render(nodes, states, names, visible, custom_sources=custom)

    caps = available_caps(shown, states)
    if caps:
        st.caption("Plafonds d'extraction par ressource (gisements disponibles, /min) :")
        st.dataframe(
            [{"Ressource": names.get(k, k), "Débit max /min": round(v, 1)}
             for k, v in sorted(caps.items(), key=lambda kv: names.get(kv[0], kv[0]))],
            use_container_width=True, hide_index=True,
        )


def _locate_tab(repo: Repository) -> None:
    """Onglet localisation d'usine (§5ter) : où construire selon les bruts requis."""
    st.subheader("📍 Localisation d'usine")
    demand_state = st.session_state.get("plan_demand")
    if not demand_state or not demand_state["raws"]:
        st.info(
            "Calcule d'abord un plan (onglet **Planificateur**) avec un item cible : "
            "la localisation place l'usine au plus près des **bruts requis** par le plan."
        )
        return

    raws, names = demand_state["raws"], demand_state["names"]
    st.caption("Bruts requis par le plan (/min) : " + ", ".join(
        f"{names.get(k, k)} {v:g}" for k, v in sorted(raws.items())
    ))

    nodes = load_nodes()
    states = load_states(map_view.DEFAULT_STATE_PATH)
    custom = load_custom_sources(DEFAULT_CUSTOM_PATH)
    sources = build_sources(nodes, states, raws.keys(), custom_sources=custom)
    results = locate_factory(raws, sources, n_alternatives=3)
    if not results:
        st.warning("Aucun gisement disponible pour les bruts requis (vérifie l'onglet Carte).")
        return

    idx = 0
    if len(results) > 1:
        idx = st.radio(
            "Site candidat", list(range(len(results))), horizontal=True,
            format_func=lambda i: f"#{i + 1} — coût {results[i].cost:,.0f}",
        )
    res = results[idx]

    c1, c2 = st.columns(2)
    c1.metric("Coût de transport (Σ débit×distance)", f"{res.cost:,.0f}")
    c2.caption(f"Position usine (monde) : x={res.site[0]:.0f}, y={res.site[1]:.0f}")
    if res.shortfalls:
        st.warning("⚠ Capacité insuffisante : " + ", ".join(
            f"{names.get(k, k)} −{v:g}/min" for k, v in res.shortfalls.items()
        ))

    # Transport (§5quater) : mode recommandé par liaison.
    def _reco(pick):
        item = repo.items.get(pick.source.item)
        is_fluid = bool(item and item.is_fluid)
        stack = item.stack_size if item else 100
        return recommend(is_fluid, pick.flow, pick.dist_m, stack)

    recos = {p.source.id: _reco(p) for p in res.picks}
    link_colors = {sid: _MODE_HEX[o.mode] for sid, o in recos.items()}
    map_view.render_siting(res, names, link_colors)
    st.caption("Mode de transport : " + " · ".join(
        f"{emoji} {name}" for _, name, emoji in _MODE_LEGEND
    ))

    st.caption("Gisements retenus & transport conseillé :")
    st.dataframe(
        [{"Ressource": names.get(p.source.item, p.source.item),
          "Débit /min": round(p.flow, 1), "Distance (m)": round(p.dist_m),
          "Transport": recos[p.source.id].name,
          "Unités": f"{recos[p.source.id].units} {recos[p.source.id].unit_label}",
          "Gisement": p.source.id}
         for p in sorted(res.picks, key=lambda p: p.dist_m)],
        use_container_width=True, hide_index=True,
    )

    with st.expander("🗺️ Carte de décision (mode gagnant selon distance × débit)"):
        st.caption("Modèle de coût approximatif (calibrable). Solides, pile = 100.")
        dists = [50, 250, 750, 2000, 5000, 12000]
        rates = [1200, 780, 480, 240, 120, 60]
        grid = decision_grid([float(d) for d in dists], [float(r) for r in rates])
        st.dataframe(
            [{"Débit \\ Dist (m)": f"{r}/min",
              **{f"{d} m": grid[i][j] for j, d in enumerate(dists)}}
             for i, r in enumerate(rates)],
            use_container_width=True, hide_index=True,
        )


_MODE_HEX = {"belt": "#27ae60", "pipe": "#2980b9", "truck": "#e67e22",
             "train": "#8e44ad", "drone": "#16a085"}
_MODE_LEGEND = [("belt", "Tapis", "🟢"), ("pipe", "Pipeline", "🔵"),
                ("truck", "Camion", "🟠"), ("train", "Train", "🟣"),
                ("drone", "Drone", "🟦")]


render()
