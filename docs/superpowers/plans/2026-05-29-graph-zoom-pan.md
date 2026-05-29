# Graphes zoomables (zoom/pan) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre tous les graphes Graphviz de l'onglet plan zoomables/déplaçables (molette = zoom, glisser = pan) dans l'UI Streamlit, hors-ligne.

**Architecture:** Le DOT existant (`.to_dot()`) est rendu en SVG **dans le navigateur** par `viz-standalone.js` (@viz-js/viz, wasm inclus), puis rendu interactif par `svg-pan-zoom`. Libs vendorisées : la lourde (`viz-standalone.js`) est servie une fois via le *static file serving* de Streamlit (cache navigateur), la légère (`svg-pan-zoom`) est inlinée. Un helper `render_dot()` remplace `st.graphviz_chart(...)`.

**Tech Stack:** Python 3.12, Streamlit (`components.v1.html`), @viz-js/viz, svg-pan-zoom. Aucune nouvelle dépendance Python, aucun binaire `dot`.

> **Note git :** ce projet **n'est pas un dépôt git**. Les étapes « commit » sont
> remplacées par un **checkpoint** : `uv run pytest -q` doit passer. (`uv` est sur
> le PATH ; utiliser un terminal neuf.)

> **Spec :** [docs/superpowers/specs/2026-05-29-graph-zoom-pan-design.md](../specs/2026-05-29-graph-zoom-pan-design.md)

---

## File Structure

- Create: `src/satisfactory_planner/ui/static/vendor/viz-standalone.js` (vendorisé)
- Create: `src/satisfactory_planner/ui/static/vendor/svg-pan-zoom.min.js` (vendorisé)
- Create: `.streamlit/config.toml` (active le static file serving)
- Create: `src/satisfactory_planner/ui/graph_view.py` (`_read_vendor`, `build_graph_html`, `render_dot`)
- Create: `tests/test_graph_view.py`
- Modify: `src/satisfactory_planner/ui/app.py` (3 appels `st.graphviz_chart` → `render_dot`)

---

## Task 1 : Vendoriser les libs JS

**Files:**
- Create: `src/satisfactory_planner/ui/static/vendor/svg-pan-zoom.min.js`
- Create: `src/satisfactory_planner/ui/static/vendor/viz-standalone.js`

- [ ] **Step 1 : Créer le dossier et télécharger les libs** (Internet requis ici ; au runtime, plus aucun réseau)

Run :
```bash
mkdir -p src/satisfactory_planner/ui/static/vendor
curl -L -o src/satisfactory_planner/ui/static/vendor/svg-pan-zoom.min.js \
  https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.2/dist/svg-pan-zoom.min.js
curl -L -o src/satisfactory_planner/ui/static/vendor/viz-standalone.js \
  https://cdn.jsdelivr.net/npm/@viz-js/viz@3/lib/viz-standalone.js
```

- [ ] **Step 2 : Vérifier les tailles** (la min.js ~30 Ko, viz-standalone ~2–3 Mo)

Run :
```bash
ls -l src/satisfactory_planner/ui/static/vendor/
```
Expected : `svg-pan-zoom.min.js` > 10 Ko et `viz-standalone.js` > 1 Mo. Si un fichier
fait quelques centaines d'octets, c'est une page d'erreur HTML → vérifier l'URL.

- [ ] **Step 3 : Vérifier que viz-standalone expose le global `Viz`**

Run :
```bash
grep -c "viz" src/satisfactory_planner/ui/static/vendor/viz-standalone.js
```
Expected : nombre > 0 (présence du code Viz). Noter au passage la version réelle
résolue par jsdelivr (en tête de fichier) pour traçabilité.

---

## Task 2 : Activer le static file serving de Streamlit

**Files:**
- Create: `.streamlit/config.toml`

- [ ] **Step 1 : Créer `.streamlit/config.toml`**

Contenu exact :
```toml
[server]
enableStaticServing = true
```

- [ ] **Step 2 : Vérifier le contenu**

Run :
```bash
cat .streamlit/config.toml
```
Expected : les 2 lignes ci-dessus. Streamlit servira alors
`src/satisfactory_planner/ui/static/` (dossier voisin de l'entrypoint `app.py`)
à l'URL `app/static/...`.

---

## Task 3 : Module `graph_view.py` — `_read_vendor` + `build_graph_html`

**Files:**
- Create: `src/satisfactory_planner/ui/graph_view.py`
- Test: `tests/test_graph_view.py`

- [ ] **Step 1 : Écrire les tests qui échouent**

`tests/test_graph_view.py` :
```python
import json

from satisfactory_planner.ui.graph_view import _read_vendor, build_graph_html

DOT = "digraph {\n a -> b;\n}"


def test_build_graph_html_embeds_dot_json_encoded():
    # Le DOT est injecté en JSON (guillemets et sauts de ligne échappés).
    html = build_graph_html(DOT, height=400)
    assert json.dumps(DOT) in html


def test_build_graph_html_references_viz_static_and_inits_panzoom():
    html = build_graph_html(DOT)
    assert "app/static/vendor/viz-standalone.js" in html  # lib lourde servie en statique
    assert "Viz.instance()" in html                       # rendu DOT -> SVG
    assert "svgPanZoom(" in html                          # zoom/pan initialisé


def test_build_graph_html_respects_height():
    assert "height:400px" in build_graph_html(DOT, height=400)


def test_build_graph_html_inlines_svg_pan_zoom():
    # La lib légère est inlinée (pas servie séparément).
    html = build_graph_html(DOT)
    assert _read_vendor("svg-pan-zoom.min.js")[:60] in html


def test_vendored_files_present_and_nontrivial():
    assert len(_read_vendor("svg-pan-zoom.min.js")) > 10_000
    assert len(_read_vendor("viz-standalone.js")) > 1_000_000
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run : `uv run pytest tests/test_graph_view.py -v`
Expected : FAIL — `ModuleNotFoundError: ... graph_view` (le module n'existe pas).

- [ ] **Step 3 : Écrire `graph_view.py` (sans `render_dot` pour l'instant)**

`src/satisfactory_planner/ui/graph_view.py` :
```python
"""Rendu de graphes Graphviz zoomables/déplaçables dans l'UI Streamlit.

Le DOT (issu des fonctions ``distribution/*`` via ``.to_dot()``) est rendu en SVG
**dans le navigateur** par viz-standalone (@viz-js/viz, wasm inclus), puis rendu
zoomable/déplaçable par svg-pan-zoom. Libs vendorisées dans ``static/vendor`` :
- ``viz-standalone.js`` : lourde, servie via le static file serving de Streamlit
  (mise en cache par le navigateur, partagée entre composants) ;
- ``svg-pan-zoom.min.js`` : légère, inlinée dans le HTML du composant.

Aucune dépendance réseau au runtime, aucun binaire ``dot`` requis.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

_VENDOR_DIR = Path(__file__).parent / "static" / "vendor"
# URL servie par Streamlit (enableStaticServing) ; même origine que l'iframe srcdoc.
_VIZ_STATIC_URL = "app/static/vendor/viz-standalone.js"


@functools.lru_cache(maxsize=None)
def _read_vendor(name: str) -> str:
    """Contenu d'un fichier vendorisé de ``static/vendor`` (mis en cache)."""
    return (_VENDOR_DIR / name).read_text(encoding="utf-8")


def build_graph_html(dot: str, height: int = 540) -> str:
    """HTML autonome rendant ``dot`` en SVG zoomable/déplaçable.

    Fonction pure (n'importe pas ``streamlit``) -> testable sans serveur.
    """
    svg_pan_zoom = _read_vendor("svg-pan-zoom.min.js")
    dot_js = json.dumps(dot)  # échappe guillemets / sauts de ligne
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; }}
  #wrap {{ width:100%; height:{height}px; border:1px solid #ddd;
           border-radius:6px; overflow:hidden; background:#fff; }}
  #graph, #graph svg {{ width:100%; height:100%; }}
  #err {{ color:#b00; font:13px sans-serif; padding:8px; }}
</style></head>
<body>
  <div id="wrap"><div id="graph"></div></div>
  <div id="err"></div>
  <script src="{_VIZ_STATIC_URL}"></script>
  <script>{svg_pan_zoom}</script>
  <script>
    var DOT = {dot_js};
    function fail(m) {{ document.getElementById('err').textContent =
      'Graphe non rendu : ' + m + ' (static serving activé ?)'; }}
    if (typeof Viz === 'undefined') {{
      fail('viz-standalone.js introuvable');
    }} else {{
      Viz.instance().then(function(viz) {{
        var svg = viz.renderSVGElement(DOT);
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        document.getElementById('graph').appendChild(svg);
        svgPanZoom(svg, {{ controlIconsEnabled:true, fit:true, center:true,
                           minZoom:0.1, maxZoom:20 }});
      }}).catch(function(e) {{ fail(String(e)); }});
    }}
  </script>
</body></html>"""
```

- [ ] **Step 4 : Lancer les tests, vérifier qu'ils passent**

Run : `uv run pytest tests/test_graph_view.py -v`
Expected : PASS (5 tests).

- [ ] **Step 5 : Checkpoint**

Run : `uv run pytest -q`
Expected : toute la suite passe.

---

## Task 4 : `render_dot` + intégration dans `app.py`

**Files:**
- Modify: `src/satisfactory_planner/ui/graph_view.py` (ajout `render_dot`)
- Modify: `src/satisfactory_planner/ui/app.py`
- Test: `tests/test_graph_view.py` (ajout d'un test `render_dot`)

- [ ] **Step 1 : Écrire le test `render_dot` (capture l'appel components.html)**

Ajouter à `tests/test_graph_view.py` :
```python
def test_render_dot_passes_html_and_height_to_components(monkeypatch):
    import streamlit.components.v1 as components

    captured = {}

    def fake_html(html, **kwargs):
        captured["html"] = html
        captured["kwargs"] = kwargs

    monkeypatch.setattr(components, "html", fake_html)

    from satisfactory_planner.ui.graph_view import render_dot

    render_dot("digraph { a -> b; }", height=300)
    assert "svgPanZoom(" in captured["html"]
    assert "a -> b" in captured["html"]
    assert captured["kwargs"]["height"] == 312  # height + 12 px (bordure)
```
(Pré-requis : `streamlit` installé via l'extra `ui` — déjà le cas.)

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run : `uv run pytest tests/test_graph_view.py::test_render_dot_passes_html_and_height_to_components -v`
Expected : FAIL — `ImportError: cannot import name 'render_dot'`.

- [ ] **Step 3 : Ajouter `render_dot` à `graph_view.py`**

Ajouter à la fin de `src/satisfactory_planner/ui/graph_view.py` :
```python
def render_dot(dot: str, *, height: int = 540) -> None:
    """Affiche ``dot`` comme graphe zoomable/déplaçable dans Streamlit."""
    import streamlit.components.v1 as components

    # +12 px pour la bordure/marge interne du conteneur.
    components.html(build_graph_html(dot, height), height=height + 12, scrolling=False)
```

- [ ] **Step 4 : Lancer le test, vérifier qu'il passe**

Run : `uv run pytest tests/test_graph_view.py::test_render_dot_passes_html_and_height_to_components -v`
Expected : PASS.

- [ ] **Step 5 : Importer `render_dot` dans `app.py`**

Dans `src/satisfactory_planner/ui/app.py`, après le bloc d'imports
`from satisfactory_planner.siting import ...` (vers la ligne 25), ajouter :
```python
from satisfactory_planner.ui.graph_view import render_dot
```

- [ ] **Step 6 : Remplacer l'appel « Chaîne complète » (~ligne 236)**

Remplacer :
```python
    st.graphviz_chart(build_plan_graph(plan, repo).to_dot())
```
par :
```python
    render_dot(build_plan_graph(plan, repo).to_dot(), height=540)
```

- [ ] **Step 7 : Remplacer l'appel « vue compacte I/O » (~ligne 290)**

Remplacer :
```python
            st.graphviz_chart(build_step_io(step, repo, plan.item_names).to_dot())
```
par :
```python
            render_dot(build_step_io(step, repo, plan.item_names).to_dot(), height=360)
```

- [ ] **Step 8 : Remplacer l'appel « détail tapis » (~ligne 293)**

Remplacer :
```python
                st.graphviz_chart(graph.to_dot())
```
par :
```python
                render_dot(graph.to_dot(), height=540)
```

- [ ] **Step 9 : Vérifier qu'il ne reste plus de `graphviz_chart`**

Run : `grep -n "graphviz_chart" src/satisfactory_planner/ui/app.py`
Expected : aucune sortie.

- [ ] **Step 10 : Checkpoint (tests + lint)**

Run :
```bash
uv run pytest -q
uv run ruff check src/satisfactory_planner/ui/graph_view.py src/satisfactory_planner/ui/app.py
```
Expected : tests OK, ruff sans erreur.

---

## Task 5 : Vérification manuelle (zoom réel dans le navigateur)

**Files:** aucun (validation runtime).

- [ ] **Step 1 : Lancer l'app** (terminal neuf, depuis la racine projet)

Run : `uv run streamlit run src/satisfactory_planner/ui/app.py`

- [ ] **Step 2 : Générer un plan et vérifier le zoom**

Calculer un plan (ex. inverse « Reinforced Iron Plate »). Dans « Chaîne complète » :
- le graphe s'affiche dans un cadre ;
- **molette** = zoom, **glisser** = pan, **boutons +/−/reset** présents (coin du cadre).

- [ ] **Step 3 : Vérifier les autres graphes**

Déplier une étape : la « vue compacte » et le « Détail tapis » sont zoomables de
la même façon.

- [ ] **Step 4 : Si le cadre est vide / message d'erreur**

Le message « static serving activé ? » indique que `app/static/vendor/viz-standalone.js`
n'a pas été servi. Vérifier : (a) `.streamlit/config.toml` présent à la racine et
lancement depuis la racine ; (b) fichier présent dans `src/satisfactory_planner/ui/static/vendor/`.
Ouvrir directement `http://localhost:8501/app/static/vendor/viz-standalone.js` : doit
renvoyer le JS. **Repli** si l'URL diffère selon la version de Streamlit : inliner la
lib en lisant `_read_vendor("viz-standalone.js")` dans un `<script>` au lieu du
`<script src=...>` (zéro config, payload plus lourd) — voir la variante de la spec.

- [ ] **Step 5 : Checkpoint final**

Run : `uv run pytest -q`
Expected : toute la suite passe.
```
