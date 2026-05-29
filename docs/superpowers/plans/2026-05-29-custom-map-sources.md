# Sources personnalisées sur la carte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser des sources d'items manufacturés sur la carte, utilisables comme entrées disponibles du solveur et comme sources de localisation d'usine.

**Architecture:** Un modèle `CustomSource` persisté en JSON ; l'onglet Carte gagne un mode « Ajouter une source » (clic = position) ; le solveur `build_forward` accepte des entrées non-brutes ; le planificateur injecte les caps des sources dans `available` ; la localisation ajoute ces sources aux candidats.

**Tech Stack:** Python 3.12, pydantic, Streamlit, folium/streamlit-folium, OR-Tools.

> **Note git :** projet **non versionné**. Les « commit » sont remplacés par un
> **checkpoint** : `uv run pytest -q` doit passer. `uv` est sur le PATH (terminal neuf).
> Raccourci utilisé ci-dessous : `UV="$HOME/AppData/Roaming/Python/Python311/Scripts/uv.exe"`.

> **Spec :** [docs/superpowers/specs/2026-05-29-custom-map-sources-design.md](../specs/2026-05-29-custom-map-sources-design.md)

---

## File Structure

- Create: `src/satisfactory_planner/nodes/custom.py` — modèle `CustomSource`, persistance, `add_source`/`remove_source`.
- Create: `tests/test_custom_sources.py`, `tests/test_sources.py`.
- Modify: `src/satisfactory_planner/ui/map_view.py` — `latlng_to_world`, marqueurs custom, `render_placement`, `render(..., custom_sources)`.
- Modify: `src/satisfactory_planner/solver/lp_model.py` — `build_forward` (entrées non-brutes).
- Modify: `src/satisfactory_planner/solver/modes.py` — `solve_forward` (consumed_keys).
- Modify: `src/satisfactory_planner/siting/sources.py` — `build_sources(..., custom_sources)`.
- Modify: `src/satisfactory_planner/ui/app.py` — `_map_tab` (UI ajout/liste), `_planner_tab` (case caps), `_locate_tab` (sources perso).
- Modify: `tests/test_map_view.py`, `tests/test_solver.py`, `tests/test_app.py`.

---

# PHASE ③-1 — Données + carte (CRUD)

## Task 1 : Modèle `CustomSource` + persistance

**Files:**
- Create: `src/satisfactory_planner/nodes/custom.py`
- Test: `tests/test_custom_sources.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

`tests/test_custom_sources.py` :
```python
from satisfactory_planner.nodes.custom import (
    CustomSource, add_source, load_custom_sources, remove_source, save_custom_sources,
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
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `$UV run pytest tests/test_custom_sources.py -q`
Expected: FAIL — `ModuleNotFoundError: ... nodes.custom`.

- [ ] **Step 3 : Écrire `nodes/custom.py`**

```python
"""Sources personnalisées (sorties d'usine) posées sur la carte (§5ter).

Persistées par projet dans un JSON (comme `nodes_state.json`). Une source déclare
qu'un item est disponible à un débit donné, à une position monde — utilisable comme
entrée du solveur et comme source de localisation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

DEFAULT_CUSTOM_PATH = "custom_sources.json"


class CustomSource(BaseModel):
    """Une source d'item manufacturé posée à la main sur la carte."""

    id: str
    item: str  # clé d'item, ex. "Desc_Plastic_C"
    rate_per_min: float
    x: float  # coords monde (cm), comme les gisements
    y: float
    label: str = ""


def load_custom_sources(path: str | Path) -> list[CustomSource]:
    """Charge la liste des sources (vide si le fichier n'existe pas)."""
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [CustomSource(**cfg) for cfg in data]


def save_custom_sources(sources: list[CustomSource], path: str | Path) -> None:
    """Sérialise la liste (dernier-écrit-gagne)."""
    data = [s.model_dump() for s in sources]
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_id(sources: list[CustomSource], item: str) -> str:
    prefix = f"cs_{item}_"
    n = 1 + max(
        (int(s.id[len(prefix):]) for s in sources
         if s.id.startswith(prefix) and s.id[len(prefix):].isdigit()),
        default=0,
    )
    return f"{prefix}{n}"


def add_source(sources: list[CustomSource], item: str, rate: float,
               x: float, y: float, label: str = "") -> list[CustomSource]:
    """Renvoie une nouvelle liste avec une source ajoutée (id généré, stable)."""
    new = CustomSource(
        id=_next_id(sources, item), item=item, rate_per_min=rate, x=x, y=y, label=label
    )
    return [*sources, new]


def remove_source(sources: list[CustomSource], source_id: str) -> list[CustomSource]:
    """Renvoie une nouvelle liste sans la source d'id `source_id`."""
    return [s for s in sources if s.id != source_id]
```

- [ ] **Step 4 : Lancer, vérifier que ça passe**

Run: `$UV run pytest tests/test_custom_sources.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5 : Exporter depuis le package `nodes`**

Dans `src/satisfactory_planner/nodes/__init__.py`, ajouter l'export (suivre le style des imports existants) :
```python
from .custom import (
    CustomSource,
    add_source,
    load_custom_sources,
    remove_source,
    save_custom_sources,
)
```
Et ajouter ces noms à `__all__` s'il existe dans ce fichier.

- [ ] **Step 6 : Checkpoint**

Run: `$UV run pytest -q && $UV run ruff check src tests`
Expected: tout vert.

---

## Task 2 : Conversion de coordonnées + marqueurs custom (map_view)

**Files:**
- Modify: `src/satisfactory_planner/ui/map_view.py`
- Test: `tests/test_map_view.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_map_view.py` :
```python
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
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `$UV run pytest tests/test_map_view.py -k "latlng or custom_sources" -v`
Expected: FAIL (`latlng_to_world` absent / `custom_sources` non accepté).

- [ ] **Step 3 : Ajouter `latlng_to_world`**

Dans `src/satisfactory_planner/ui/map_view.py`, juste après `world_to_latlng` :
```python
def latlng_to_world(lat: float, lng: float) -> tuple[float, float]:
    """Inverse de `world_to_latlng` : (lat, lng) folium -> (x, y) monde (cm)."""
    return (lng * _SCALE, -lat * _SCALE)
```

- [ ] **Step 4 : Dessiner les sources custom dans `build_folium_map`**

Modifier la signature et ajouter le rendu. Remplacer l'en-tête de `build_folium_map` :
```python
def build_folium_map(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
):
```
par :
```python
def build_folium_map(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    custom_sources=None,
):
```
Puis, juste avant `return fmap` de `build_folium_map`, ajouter :
```python
    for cs in (custom_sources or []):
        clat, clng = world_to_latlng(cs.x, cs.y)
        nm = (names or {}).get(cs.item, cs.item)
        folium.Marker(
            location=[clat, clng],
            icon=folium.DivIcon(
                html='<div style="font-size:20px;line-height:20px;'
                'transform:translate(-50%,-50%)">🏭</div>',
                icon_size=(20, 20), icon_anchor=(0, 0),
            ),
            tooltip=f"{nm} — {cs.rate_per_min:g}/min (source perso)",
        ).add_to(fmap)
```

- [ ] **Step 5 : Lancer, vérifier que ça passe**

Run: `$UV run pytest tests/test_map_view.py -k "latlng or custom_sources" -v`
Expected: PASS.

- [ ] **Step 6 : Ajouter `render_placement` + `custom_sources` à `render`**

Dans `map_view.py`, remplacer l'en-tête de `render` :
```python
def render(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    state_path: str = DEFAULT_STATE_PATH,
) -> None:
```
par :
```python
def render(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    state_path: str = DEFAULT_STATE_PATH,
    custom_sources=None,
) -> None:
```
et dans `render`, remplacer l'appel `build_folium_map(nodes, states, names, visible)` par
`build_folium_map(nodes, states, names, visible, custom_sources)`.

Puis ajouter une nouvelle fonction à la fin du fichier :
```python
def render_placement(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    custom_sources=None,
) -> tuple[float, float] | None:
    """Carte en mode placement : renvoie (x, y) monde du dernier clic NEUF, sinon None."""
    import streamlit as st
    from streamlit_folium import st_folium

    st.caption("Clique sur la carte pour positionner la source à ajouter.")
    result = st_folium(
        build_folium_map(nodes, states, names, visible, custom_sources),
        height=600, use_container_width=True, returned_objects=["last_clicked"],
    )
    clicked = (result or {}).get("last_clicked")
    if not clicked:
        return None
    key = (round(clicked["lat"], 4), round(clicked["lng"], 4))
    if st.session_state.get("_last_place_click") == key:
        return None
    st.session_state["_last_place_click"] = key
    return latlng_to_world(clicked["lat"], clicked["lng"])
```

- [ ] **Step 7 : Checkpoint**

Run: `$UV run pytest tests/test_map_view.py -q && $UV run ruff check src/satisfactory_planner/ui/map_view.py`
Expected: vert.

---

## Task 3 : UI ajout/liste/suppression dans l'onglet Carte

**Files:**
- Modify: `src/satisfactory_planner/ui/app.py` (`_map_tab`, imports)
- Test: `tests/test_app.py`

- [ ] **Step 1 : Écrire le test AppTest (mode ajout sans exception)**

Ajouter à `tests/test_app.py` :
```python
def test_app_map_add_source_mode_runs():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    r = next((r for r in at.radio if r.label == "Mode carte"), None)
    assert r is not None  # le sélecteur de mode carte existe
    r.set_value("➕ Ajouter une source").run()
    assert not at.exception
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `$UV run pytest tests/test_app.py::test_app_map_add_source_mode_runs -q`
Expected: FAIL (radio « Mode carte » absent → `r is None`).

- [ ] **Step 3 : Importer les helpers custom dans `app.py`**

Dans les imports de `src/satisfactory_planner/ui/app.py`, ajouter (groupe `nodes`,
à côté de `from satisfactory_planner.nodes import (...)`) les symboles :
```python
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
```
(adapter à la liste existante : conserver `NodeState, available_caps, load_nodes,
load_states` et ajouter `DEFAULT_CUSTOM_PATH, add_source, load_custom_sources,
remove_source, save_custom_sources`. Ne PAS importer `CustomSource` : `add_source`
le construit en interne, un import direct serait inutilisé — F401.)

- [ ] **Step 4 : Réécrire `_map_tab` avec le mode ajout**

Remplacer le corps de `_map_tab` à partir de la ligne `st.subheader("Carte des gisements")`
jusqu'à l'appel `map_view.render(...)` inclus par :
```python
    st.subheader("Carte des gisements")
    custom = load_custom_sources(DEFAULT_CUSTOM_PATH)
    # Noms d'items (catalogue) pour l'ajout de sources perso + tooltips.
    item_names = {repo.items[k].name: k for k in repo.items}
    cs_tooltip_names = {**names, **{k: repo.items[k].name for k in repo.items}}

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
    available = sum(1 for n in shown if (states.get(n.id) or NodeState()).available)
    st.caption(f"{len(shown)} gisements affichés ({available} disponibles).")

    if map_mode.startswith("➕"):
        c1, c2 = st.columns([3, 1])
        sel_name = c1.selectbox("Item de la source", sorted(item_names), key="cs_item")
        rate = c2.number_input("Débit (/min)", min_value=0.1, value=20.0, step=10.0,
                               key="cs_rate")
        pos = map_view.render_placement(shown, states, cs_tooltip_names, visible, custom)
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
        map_view.render(shown, states, names, visible, custom_sources=custom)
```

> **Bornes du remplacement** : remplacer depuis `st.subheader("Carte des gisements")`
> jusqu'à **et y compris** l'ancienne ligne `map_view.render(nodes, states, names, visible)`.
> Ne PAS toucher à la ligne suivante `caps = available_caps(shown, states)` ni au bloc
> `if caps:` : ils restent en place (et `shown`/`states` sont bien définis ci-dessus).

- [ ] **Step 5 : Lancer le test AppTest**

Run: `$UV run pytest tests/test_app.py::test_app_map_add_source_mode_runs -q`
Expected: PASS.

- [ ] **Step 6 : Vérification manuelle (clic carte non testable via AppTest)**

Run: `$UV run streamlit run src/satisfactory_planner/ui/app.py`
Onglet **Carte gisements** → mode **➕ Ajouter une source** → choisir un item + débit →
cliquer sur la carte : un marqueur 🏭 apparaît, listé dessous ; **🗑** le supprime.
(`custom_sources.json` apparaît à la racine.)

- [ ] **Step 7 : Checkpoint ③-1**

Run: `$UV run pytest -q && $UV run ruff check src tests`
Expected: tout vert.

---

# PHASE ③-2 — Solveur + planificateur

## Task 4 : `build_forward` accepte des entrées non-brutes

**Files:**
- Modify: `src/satisfactory_planner/solver/lp_model.py`
- Modify: `src/satisfactory_planner/solver/modes.py`
- Test: `tests/test_solver.py`

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_solver.py` (imports `Item, Machine, Recipe, Repository, solve_forward`
déjà présents ou à compléter au besoin) :
```python
def test_forward_uses_external_nonraw_input():
    from satisfactory_planner.model.entities import Item, Machine, Recipe
    from satisfactory_planner.model.repository import Repository
    from satisfactory_planner.solver import solve_forward

    items = {
        "Ore": Item(key="Ore", name="Ore", is_raw=True),
        "Mid": Item(key="Mid", name="Mid"),
        "Out": Item(key="Out", name="Out"),
    }
    recipes = {
        "R1": Recipe(key="R1", name="R1", machine="M", duration_s=60.0,
                     inputs={"Ore": 1.0}, outputs={"Mid": 1.0}),
        "R2": Recipe(key="R2", name="R2", machine="M", duration_s=60.0,
                     inputs={"Mid": 1.0}, outputs={"Out": 1.0}),
    }
    repo = Repository(items=items, recipes=recipes,
                      machines={"M": Machine(key="M", name="M", base_power_mw=1.0)},
                      enabled={"R1", "R2"})

    base = solve_forward(repo, {"Out": 10.0})
    assert base.raw_consumed.get("Ore") == 10.0

    coupled = solve_forward(repo, {"Out": 10.0}, available={"Mid": 4.0})
    assert coupled.raw_consumed.get("Ore") == 6.0   # 4 Mid externes -> 6 Ore
    assert coupled.raw_consumed.get("Mid") == 4.0    # entrée externe consommée
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `$UV run pytest tests/test_solver.py::test_forward_uses_external_nonraw_input -q`
Expected: FAIL (`Ore` = 10.0 au lieu de 6.0, `Mid` absent : `available` ignoré pour les non-bruts).

- [ ] **Step 3 : Généraliser `build_forward`**

Dans `src/satisfactory_planner/solver/lp_model.py`, dans `build_forward`, remplacer le
bloc de boucle :
```python
    raw_keys: list[str] = []
    for ik in item_keys:
        is_raw = items[ik].is_raw if ik in items else False
        if ik in targets:
            solver.Add(net_expr(ik) >= targets[ik])
        elif ik in FREE_RAWS:
            continue  # illimité : aucune contrainte, hors objectif min_raw
        elif is_raw:
            raw_keys.append(ik)
            if available and ik in available:
                solver.Add(net_expr(ik) >= -available[ik])
        else:
            solver.Add(net_expr(ik) >= 0)  # intermédiaire : pas de consommation nette
```
par :
```python
    raw_keys: list[str] = []
    for ik in item_keys:
        is_raw = items[ik].is_raw if ik in items else False
        if ik in targets:
            solver.Add(net_expr(ik) >= targets[ik])
        elif ik in FREE_RAWS:
            continue  # illimité : aucune contrainte, hors objectif min_raw
        elif is_raw:
            raw_keys.append(ik)
            if available and ik in available:
                solver.Add(net_expr(ik) >= -available[ik])
        elif available and ik in available:
            # Entrée externe déclarée (item non-brut, ex. source perso) :
            # consommable jusqu'au cap, comme un brut capé.
            solver.Add(net_expr(ik) >= -available[ik])
        else:
            solver.Add(net_expr(ik) >= 0)  # intermédiaire : pas de consommation nette
```

- [ ] **Step 4 : Reporter les entrées externes dans `consumed_keys` (`solve_forward`)**

Dans `src/satisfactory_planner/solver/modes.py`, dans `solve_forward`, remplacer :
```python
    return _make_plan(model, recipes, repo, targets, model.raw_keys, realize_strategy)
```
par :
```python
    external_keys = [
        k for k in (available or {})
        if k in repo.items and not repo.items[k].is_raw and k not in targets
    ]
    consumed_keys = model.raw_keys + external_keys
    return _make_plan(model, recipes, repo, targets, consumed_keys, realize_strategy)
```

- [ ] **Step 5 : Lancer, vérifier que ça passe**

Run: `$UV run pytest tests/test_solver.py::test_forward_uses_external_nonraw_input -q`
Expected: PASS.

- [ ] **Step 6 : Checkpoint (non-régression solveur)**

Run: `$UV run pytest tests/test_solver.py tests/test_somersloop.py -q && $UV run ruff check src/satisfactory_planner/solver`
Expected: tout vert (les bruts et le reste inchangés).

---

## Task 5 : Case « entrées disponibles » dans le planificateur

**Files:**
- Modify: `src/satisfactory_planner/ui/app.py` (`_planner_tab`)

- [ ] **Step 1 : Injecter les caps des sources perso dans `available`**

Dans `_planner_tab`, juste après la ligne `target_key = items[item_name]` (et avant
`plan = None`), ajouter le chargement + la case :
```python
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
```

- [ ] **Step 2 : Fusionner `custom_caps` dans les appels solveur**

Dans la branche Direct, remplacer :
```python
            plan = solve_forward(
                repo, {target_key: rate}, objective=objective, realize_strategy=realize
            )
```
par :
```python
            plan = solve_forward(
                repo, {target_key: rate}, objective=objective,
                available=custom_caps or None, realize_strategy=realize,
            )
```
Dans la branche Inverse, remplacer (forme multi-lignes exacte) :
```python
            plan = solve_max_output(
                repo, target_key, available, realize_strategy=realize
            )
```
par :
```python
            plan = solve_max_output(
                repo, target_key, {**available, **custom_caps}, realize_strategy=realize
            )
```

- [ ] **Step 2b : Garder l'item cible hors de ses propres caps**

Toujours dans `_planner_tab`, retirer la cible des caps (on ne « fournit » pas l'item
qu'on cherche à produire). Placer cette ligne **après le bloc `if custom:`** (donc
`custom_caps` est défini, vide ou non) et **avant** `plan = None` :
```python
    custom_caps.pop(target_key, None)
```

- [ ] **Step 3 : Vérifier la non-régression UI**

Run: `$UV run pytest tests/test_app.py -q`
Expected: PASS (8+ tests ; la case n'apparaît que si `custom_sources.json` contient des sources, donc sans effet sur les tests existants).

- [ ] **Step 4 : Vérification manuelle**

Run: `$UV run streamlit run src/satisfactory_planner/ui/app.py`
Pose une source « Plastic 20/min » (onglet Carte), reviens au Planificateur, cible un
item qui consomme du plastique (ex. *Circuit Board*), coche **« Utiliser mes sources
perso… »** → le plan ne fabrique plus le plastique (ou moins) et « Plastic » apparaît
dans **Bruts consommés**.

- [ ] **Step 5 : Checkpoint ③-2**

Run: `$UV run pytest -q && $UV run ruff check src tests`
Expected: tout vert.

---

# PHASE ③-3 — Localisation

## Task 6 : `build_sources` inclut les sources perso

**Files:**
- Modify: `src/satisfactory_planner/siting/sources.py`
- Test: `tests/test_sources.py` (création)

- [ ] **Step 1 : Écrire les tests qui échouent**

`tests/test_sources.py` :
```python
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
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `$UV run pytest tests/test_sources.py -q`
Expected: FAIL (`build_sources` n'accepte pas `custom_sources`).

- [ ] **Step 3 : Étendre `build_sources`**

Dans `src/satisfactory_planner/siting/sources.py`, remplacer l'en-tête :
```python
def build_sources(
    nodes, states: dict[str, NodeState], items_needed: Iterable[str],
    *, belt_capacity: float | None = None,
) -> list[Source]:
```
par :
```python
def build_sources(
    nodes, states: dict[str, NodeState], items_needed: Iterable[str],
    *, belt_capacity: float | None = None, custom_sources=None,
) -> list[Source]:
```
Puis, juste avant `return out`, ajouter :
```python
    for cs in (custom_sources or []):
        if cs.item not in wanted or cs.rate_per_min <= 0:
            continue
        out.append(Source(
            item=cs.item, x=cs.x, y=cs.y,
            capacity_per_min=cs.rate_per_min, kind="factory_output", id=cs.id,
        ))
```

- [ ] **Step 4 : Lancer, vérifier que ça passe**

Run: `$UV run pytest tests/test_sources.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5 : Checkpoint**

Run: `$UV run pytest -q && $UV run ruff check src/satisfactory_planner/siting`
Expected: vert.

---

## Task 7 : `_locate_tab` utilise les sources perso

**Files:**
- Modify: `src/satisfactory_planner/ui/app.py` (`_locate_tab`)

- [ ] **Step 1 : Charger et passer les sources perso**

Dans `_locate_tab`, remplacer :
```python
    nodes = load_nodes()
    states = load_states(map_view.DEFAULT_STATE_PATH)
    sources = build_sources(nodes, states, raws.keys())
```
par :
```python
    nodes = load_nodes()
    states = load_states(map_view.DEFAULT_STATE_PATH)
    custom = load_custom_sources(DEFAULT_CUSTOM_PATH)
    sources = build_sources(nodes, states, raws.keys(), custom_sources=custom)
```

- [ ] **Step 2 : Vérifier la non-régression**

Run: `$UV run pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 3 : Vérification manuelle (bout en bout)**

Run: `$UV run streamlit run src/satisfactory_planner/ui/app.py`
1. Onglet Carte → pose « Plastic 20/min » quelque part.
2. Planificateur → cible un item consommant du plastique, coche « Utiliser mes sources perso… ».
3. Onglet **📍 Localisation** : « Plastic » figure dans les bruts requis, et la source
   perso 🏭 apparaît parmi les gisements retenus avec une liaison de transport.

- [ ] **Step 4 : Checkpoint ③-3 (final)**

Run: `$UV run pytest -q && $UV run ruff check src tests`
Expected: tout vert.
```
