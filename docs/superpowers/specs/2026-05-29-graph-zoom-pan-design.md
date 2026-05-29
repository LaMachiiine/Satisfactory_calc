# Design — Graphes zoomables (zoom/pan) dans l'UI Streamlit

Date : 2026-05-29
Statut : validé (en attente de relecture utilisateur avant plan d'implémentation)

## Problème

Les graphes Graphviz de l'UI sont rendus par `st.graphviz_chart(...)`, qui n'offre
**aucun zoom ni pan**. Sur un gros plan, la « Chaîne complète » (et le « Détail
tapis ») devient minuscule et illisible. L'utilisateur veut pouvoir zoomer/déplacer.

Portée validée : **tous les graphes** de l'onglet plan (chaîne complète, vue
compacte I/O par étape, détail tapis), via un helper réutilisable.

## Contraintes

- **Hors-ligne obligatoire** : aucune dépendance réseau au runtime. Les libs JS
  sont vendorisées dans le repo (téléchargées une fois, commitées).
- **Pas de binaire système** : on ne dépend pas du binaire Graphviz `dot` (rendu
  DOT→SVG fait côté navigateur). Compatible Streamlit Community Cloud / HF Spaces.
- **Pas de nouvelle dépendance Python** (les libs sont des fichiers JS statiques).
- **Performant avec « tous les graphes »** : la grosse lib (~2,7 Mo) ne doit pas
  être renvoyée N fois par re-render.

## Approche retenue

Approche A — rendu DOT→SVG **dans le navigateur** + zoom/pan, libs vendorisées.

- Renderer : `viz-standalone.js` (@viz-js/viz), fichier autonome avec le wasm
  Graphviz inclus → `Viz.instance().then(viz => viz.renderSVGElement(dot))`.
- Zoom/pan : `svg-pan-zoom.min.js` (molette = zoom, glisser = pan, boutons +/−/reset,
  `fit` + `center` au chargement).
- **Chargement de la grosse lib** : via le *static file serving* de Streamlit
  (`enableStaticServing = true`), donc téléchargée **une seule fois** et mise en
  cache par le navigateur, partagée entre tous les iframes de composants. Servie
  par le serveur local → fonctionne hors-ligne. Le glue + `svg-pan-zoom` (léger)
  sont inlinés dans le HTML du composant.

Variante écartée (mais documentée) : tout inliner — zéro config mais payload lourd
si le plan a beaucoup d'étapes.

## Composants & interfaces

### `src/satisfactory_planner/ui/static/vendor/`
Fichiers vendorisés (commités) :
- `viz-standalone.js` — @viz-js/viz, renderer Graphviz autonome.
- `svg-pan-zoom.min.js` — zoom/pan SVG.

Servis par Streamlit à l'URL relative `app/static/vendor/<fichier>` (même origine
que l'iframe `srcdoc` du composant → pas de CORS).

### `.streamlit/config.toml` (racine projet, commité)
```toml
[server]
enableStaticServing = true
```

### `src/satisfactory_planner/ui/graph_view.py` (nouveau module)

- `_read_vendor(name: str) -> str` : lit `static/vendor/<name>` (chemin relatif au
  module), avec cache (`functools.lru_cache`). Sert au glue inliné (svg-pan-zoom) et
  aux tests d'existence.
- `build_graph_html(dot: str, height: int) -> str` : **fonction pure** (n'importe
  pas `streamlit`). Retourne un document HTML autonome :
  - `<script src="app/static/vendor/viz-standalone.js">` (lib lourde, servie/cachée) ;
  - `<script>` inline : contenu de `svg-pan-zoom.min.js` ;
  - conteneur `<div>` dimensionné à `height` ;
  - glue : injecte le DOT via `JSON.stringify(dot)`, rend le SVG via Viz, l'insère,
    fixe `width/height: 100%`, puis `svgPanZoom(svg, {controlIconsEnabled:true,
    fit:true, center:true, minZoom:0.1, maxZoom:20})` ;
  - gestion d'erreur visible si la lib n'a pas chargé (message « static serving ? »).
- `render_dot(dot: str, *, height: int = 540, key: str | None = None) -> None` :
  importe `streamlit` en lazy, appelle `st.components.v1.html(build_graph_html(dot,
  height), height=height, scrolling=False)`.

### `src/satisfactory_planner/ui/app.py` (intégration)
Remplacer les 3 appels `st.graphviz_chart(x.to_dot())` par `render_dot(...)` :
- Chaîne complète (~ligne 236) : `render_dot(build_plan_graph(plan, repo).to_dot(),
  height=540, key="plan")`.
- Vue compacte I/O par étape (~ligne 290) : `render_dot(build_step_io(...).to_dot(),
  height=360, key=f"io_{step.recipe.key}")`.
- Détail tapis (~ligne 293) : `render_dot(graph.to_dot(), height=540,
  key=f"belt_{step.recipe.key}")`.

Les boutons de téléchargement DOT/JSON et le reste de l'onglet sont inchangés.

## Flux de données

`plan` → `build_*_graph(...)` (existant) → `.to_dot()` (string DOT, existant) →
`render_dot(dot)` → `build_graph_html(dot, height)` → `st.components.v1.html(...)` →
iframe : Viz rend le SVG, svg-pan-zoom ajoute zoom/pan.

Aucun changement au modèle de graphe ni aux fonctions `distribution/*`.

## Gestion d'erreurs

- Lib viz absente / non chargée (static serving désactivé) : le composant affiche un
  message lisible plutôt qu'un cadre vide.
- DOT vide : Viz rend un SVG vide ; acceptable.

## Tests (`tests/test_graph_view.py`, style `test_map_view.py`, sans serveur)

- `build_graph_html(dot, h)` : contient le DOT JSON-encodé ; référence
  `app/static/vendor/viz-standalone.js` ; inline le contenu de svg-pan-zoom ;
  appelle `svgPanZoom(` ; respecte `height`.
- `_read_vendor("svg-pan-zoom.min.js")` et `_read_vendor("viz-standalone.js")`
  renvoient un contenu non-trivial (fichiers vendorisés présents).
- (Optionnel) `render_dot` est importable sans le serveur (streamlit en lazy).

## Hors périmètre

- Onglet carte (déjà interactif via folium).
- Sankey (plotly, déjà zoomable).
- Refonte du modèle de graphe / styles Graphviz.
