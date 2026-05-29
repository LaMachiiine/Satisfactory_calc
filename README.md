# Satisfactory Planner

Calculateur & distributeur de production pour *Satisfactory* (1.1) : calcul de
ratios par programmation linéaire **et** génération du réseau logique de
distribution (répartiteurs / groupeurs) avec gestion de la capacité des tapis.

Spécification complète : [`DOC/specs_calculateur_distributeur_satisfactory.md`](DOC/specs_calculateur_distributeur_satisfactory.md).

## Statut des phases

| Phase | Contenu | État |
|-------|---------|------|
| 0 | Données : parser `Docs.json` → entités, constantes de jeu, tests débits | ✅ fait |
| 1 | Cœur LP : `solve_forward` (min_raw, OR-Tools GLOP), réalisation machines/horloge/puissance, CLI `forward` | ✅ fait |
| 2 | Modes avancés : `solve_max_output`, min_power/min_machines, alternatives, Somersloop | ✅ fait |
| 3 | Distributeur : arbre /2 /3, manifold, capacité, tiers, export DOT/JSON | ✅ fait |
| 4 | UI Streamlit, Sankey, équilibreur à retour (N non factorisables) | ✅ fait |
| 5 | Gisements & carte : `nodes.json`, débit max par pureté/tier, plafonds d'extraction, onglet carte (toggle dispo/occupé) | ✅ fait |
| 6 | Localisation d'usine : sources (gisements), médiane géométrique pondérée (Weiszfeld), sélection sous capacité, alternatives, onglet carte | ✅ fait |
| 7 | Transport inter-sites : profils/formules par mode, coût approximatif, recommandation par liaison, carte de décision | ✅ fait |

Les phases 0–7 sont implémentées (cœur LP, distributeur, UI, gisements & carte,
localisation d'usine, transport inter-sites).

## Installation

Le projet utilise [uv](https://docs.astral.sh/uv/) :

```bash
uv sync --extra dev          # cœur + outils de test
uv sync --extra dev --extra ui   # + dépendances UI (streamlit, plotly)
uv run pytest                # lance les tests
```

## Interface web (Phase 4)

UI Streamlit exposant tout le cœur (modes direct/inverse, objectifs, alternatives,
Somersloop, plan + Sankey + graphes de distribution Graphviz) :

```bash
uv run --extra ui streamlit run src/satisfactory_planner/ui/app.py
```

**Défauts & options** : mode **Inverse (max output)** par défaut, réalisation **« Max à
100 % + reste »** par défaut. En inverse, la **source des bruts** est par défaut
**« Gisements de la carte »** (Σ `available_caps` des gisements disponibles), avec une
option **« Saisie manuelle »**. Les **recettes alternatives** se choisissent une à une
(multiselect ; vide = recettes standard uniquement) au lieu d'un activage global.

> **Déploiement** : le backend OR-Tools n'est pas compatible Vercel (serverless).
> Héberger l'app sur **Streamlit Community Cloud** ou **Hugging Face Spaces**
> (gratuit, serveur long-running). `data/Docs.json` doit être présent côté hôte.

## Données du jeu (`Docs.json`)

`data/Docs.json` (≈9.6 Mo) est la source canonique des recettes, au **format
original du jeu** : `<Satisfactory>/CommunityResources/Docs/Docs-en-US.json`
(tableau JSON UTF-16, ingrédients en chaînes sérialisées Unreal). N'importe quel
`Docs.json` officiel (1.0 / 1.1) peut être déposé tel quel — le parser le lit
directement, ce qui donne les **bons noms de recettes** et les **données
Somersloop** (`mProductionShardSlotSize`).

Générer le cache normalisé :

```bash
uv run planner build-cache data/Docs.json        # -> data/recipes.json
uv run planner info data/Docs.json               # statistiques
```

`data/Docs.json` est conservé en local ; `data/recipes.json` est généré (ignoré).

## Mode direct (Phase 1)

```bash
# « Je veux N unités/min de X » -> plan de production
uv run planner forward "Iron Plate" 20
uv run planner forward "Modular Frame" 10 --alternates
uv run planner forward "Modular Frame" 10 --objective min_power   # min_raw | min_power | min_machines
uv run planner forward "Iron Rod" 30 --somersloops 4              # amplification Somersloop
uv run planner forward "Iron Rod" 25 --realize max100             # uniform | max100 | overclock
```

**Réalisation machines (`--realize`)** : `uniform` (défaut) = `ceil(x)` machines
toutes à `x/ceil(x)` → **min-puissance**, sans Power Shard ; `max100` = `floor(x)`
machines à 100 % + 1 au reliquat ; `overclock` = le moins de machines possible en
surcadençant jusqu'à 250 % (coûte des Power Shards, puissance ↑↑).

## Mode inverse (Phase 2)

```bash
# « J'ai ces bruts -> production max de la cible »
uv run planner max "Reinforced Iron Plate" --available "Iron Ore=480"
uv run planner max "Iron Ingot" --available "Iron Ore=70,Water=100" --alternates
```

Sortie : tableau (recette, machines, horloge %, débit/min, puissance), puissance
totale, bruts consommés, sous-produits en surplus, et section Somersloops si
amplification.

## Distribution (Phase 3)

Ajouter `--distribute` à `forward` ou `max` pour générer, par étape du plan, le
graphe logique de répartiteurs/groupeurs :

```bash
uv run planner forward "Screw" 700 --distribute --belt 3
uv run planner forward "Screw" 700 --distribute --belt 3 --out-dir dist/   # écrit .dot/.json
```

- `--belt T` : tier de tapis 1..6 (capacité 60/120/270/480/780/1200). Sert à
  annoter le tier conseillé par tronçon et à signaler les dépassements.
- `--layout` : disposition du **détail tapis** par étape — `balanced` (défaut :
  arbre de fusion, 2 machines par groupeur, lignes parallèles) ou `linear` (cascade
  le long d'un tronçon).
- Chaque arête est annotée du tier de tapis le moins cher la couvrant ; les arêtes
  en dépassement de capacité sont signalées.
- `--out-dir` écrit un `<recette>.dot` (visualisable via `dot -Tpng`) et `.json`
  par étape, plus un `plan.dot`/`plan.json` global ; sinon un résumé texte est affiché.

Vues produites :
- **Chaîne complète** (`plan.dot`) : toutes les étapes en un seul graphe (1 nœud
  par étape), sens de production (bruts → produit final), arêtes étiquetées par item.
- **Schéma complet** (`build_full_belt`, bibliothèque) : toute l'usine **au niveau
  machine** dans un seul graphe. Disponible en biblio/export DOT mais **pas affiché
  dans l'UI** : pour un gros plan il devient illisible. L'UI privilégie le **détail
  tapis par étape** (lisible) + la **chaîne complète** en vue d'ensemble.
- **Par étape** : vue **compacte I/O** (entrées avec débits → bloc « machine ×N @
  horloge » → sorties), lisible quel que soit le nombre de machines ; et un
  **détail tapis** complet à la demande — entrées → **répartiteurs** → machines
  (1 nœud par machine, **horloge individuelle**) → **groupeurs** → sortie, débits
  par machine proportionnels à leur horloge.

## Gisements & carte (Phase 5)

`data/nodes.json` (**594 gisements** : position, type, pureté, forme, `kind`) est
intégré, régénérable depuis les données communautaires via `scripts/gen_nodes.py` :

- **459 gisements à foreuse** (`kind="node"`) — minerais solides + nœuds de pétrole ;
- **118 puits de ressource** (`kind="well"`) — **eau, azote, puits de pétrole** sous
  pression (satellites d'un *Fracking Core*, champ `core`) ;
- **17 geysers** (`kind="geyser"`) — énergie géothermique (sans ressource).

Sources : `data/MapInfo.json` (0xjc/SatisfactoryLP, onglets `resource_nodes` +
`resource_wells`) et `data/geysers.ts` (LancelotP). Régénérer :

```bash
uv run python scripts/gen_nodes.py            # -> data/nodes.json
uv run python scripts/fetch_map_background.py # -> data/map_background.jpg (fond du jeu)
```

- **Débit d'extraction** (§5bis.3) : `base_pureté(30/60/120) × foreuse(Mk1×1/Mk2×2/Mk3×4)
  × horloge/100 × (2 si Somersloop)`. Défaut : **horloge 250 %** (overclock max), Mk.1.
  Les **puits** (`node_extraction_rate`) ignorent foreuse/Somersloop (extracteurs
  uniformes : base pureté × horloge du pressuriseur) ; les **geysers** ont un débit nul.
- **État par projet** : `nodes_state.json` (disponible, foreuse, horloge, Somersloop),
  persisté ; les gisements occupés sont exclus du solveur.
- **Plafonds solveur** : `available_caps(nodes, states)` = Σ débit_max des gisements
  disponibles par ressource → alimente `solve_max_output(..., available=…)` (§5bis.4).
  Les puits comptent dans leur ressource (eau/azote/pétrole) ; les geysers sont exclus.
- **Onglet carte** (UI, style satisfactory-calculator) : **fond de carte du jeu**
  (tuiles `gameLayer` de satisfactory-calculator assemblées par
  `scripts/fetch_map_background.py` → `data/map_background.jpg`, ImageOverlay),
  marqueurs cliquables portant l'**icône de la ressource** entourée d'un anneau
  **coloré par pureté** (vert/orange/rouge ; geyser = violet), **noms propres** des
  ressources, **filtre d'affichage par ressource**, clic = bascule disponible/occupé
  (persisté). Pile : `folium` / `streamlit-folium` (extra `ui`). **Projection** : les
  tuiles SCIM couvrent les bornes jouables **élargies de 1/8** (`extraBackgroundSize`) ;
  on projette `lat = -y/6400` (nord en haut, +Y = sud en jeu) et `lng = x/6400`, bornes
  `MAP_BOUNDS` correspondantes (CRS.Simple).

## Localisation d'usine (Phase 6)

Onglet **📍 Localisation** : à partir des **bruts requis par le plan courant**
(`plan.raw_consumed`), place l'usine au plus près des gisements.

- **Sources** (`siting/sources.py`) : gisements **disponibles** produisant un brut
  requis, capacité = débit max d'extraction.
- **Médiane géométrique pondérée** (`siting/weber.py`, Weiszfeld) : position
  `P* = argmin Σ flux×‖P−source‖`, distance **2D en mètres** (coords/100).
- **Sélection sous capacité** + **Lloyd** (`siting/locate.py`) : par item, gisements
  les plus proches jusqu'à couvrir le débit (dernier partiel) ; on alterne
  sélection ↔ Weber jusqu'à stabilité, depuis plusieurs amorces → **alternatives**
  classées par coût. Pénurie signalée si la capacité est insuffisante.
- **Carte** : pin usine 📍, gisements retenus, lignes usine→sources ; sélecteur
  d'alternatives, tableau (débit routé, distance), coût total.

> Couplage LP **décorrélé** (le plan fixe la production ; la localisation place
> ensuite). Sources `manual_input` / `factory_output` et couplage distance↔LP : à venir.

## Transport inter-sites (Phase 7)

Pour chaque liaison `gisement → usine` (issue de la Phase 6), recommander le **mode
de transport** (`transport/`).

- **Profils** (`transport/constants.py`) : tapis (1200/min), pipeline (600 m³/min,
  fluides), camion (48 slots), train (32 slots/wagon **ou 1600 m³ en wagon-citerne**),
  drone (9 slots). Vitesses, temps d'animation et **coûts calibrables** (score relatif).
- **Débit unitaire** (`recommend.unit_rate`) : fixe pour tapis/pipe ; pour les
  véhicules `slots × pile × 60 / aller-retour`, l'aller-retour dépendant de la
  distance (trains/drones/camions ↓ avec la distance).
- **Coût** = `setup + coût/m × distance + (coût/unité + complexité) × n_unités`.
  `recommend()` renvoie le mode faisable le moins cher ; `evaluate()` la liste
  classée ; `decision_grid()` le mode gagnant par cellule distance×débit.
- **Fluides** → **pipeline** ou **train** (wagons-citernes, 1600 m³/wagon, sans
  empaquetage) ; tapis/camions/drones nécessiteraient un empaquetage (à venir).
  **Eau** : transport rarement nécessaire (brut illimité, voir solveur).
- **UI** : onglet **📍 Localisation** enrichi — colonne *Transport* + *Unités* par
  liaison, **lignes colorées par mode** sur la carte, et **carte de décision**.

> Coûts **approximatifs/calibrables** : les frontières exactes entre modes dépendent
> des constantes (à affiner). Conception de réseau multi-gares/hubs : à venir.

## Structure

```
src/satisfactory_planner/
├── data/         # docs_parser.py (Docs.json → entités), game_constants.py
├── model/        # entities.py (Item/Recipe/Machine/Belt), repository.py
├── solver/       # lp_model · modes · realize · result · somersloop (LP, Phases 1-2)
├── distribution/ # graph · tree · manifold · balancer · capacity  (distributeur, Phase 3)
├── nodes/        # data · extraction · state (gisements & extraction, Phase 5)
├── siting/       # weber · sources · locate (localisation d'usine, Phase 6)
├── transport/    # constants · recommend (sélection de mode inter-sites, Phase 7)
├── api.py        # façade publique (§7)
└── ui/           # cli.py · app.py (Streamlit) · sankey.py · map_view.py (carte)
scripts/          # gen_nodes.py (nodes.json) · fetch_map_background.py (fond du jeu)
data/             # Docs.json + recipes.json (cache) + nodes.json + sources carte
                  #   (MapInfo.json, geysers.ts, map_background.jpg, icons/)
tests/            # tests + fixtures (Docs.json, nodes.json)
```

> Écart assumé vs §6 de la spec : le `recipes.json` généré et le `Docs.json`
> d'entrée vivent dans `data/` à la racine (et non dans le package), pour garder
> les artefacts hors du code importable.

## Notes de format `Docs.json` (format original du jeu)

- Tableau JSON **UTF-16** de groupes `{NativeClass, Classes:[...]}` ; chaque
  classe a `ClassName` et ses champs en clé directe.
- Recette (`FGRecipe`) : `mManufactoringDuration`, `mIngredients`/`mProduct`
  (**chaînes sérialisées** `((ItemClass="…Desc_X_C'",Amount=N),…)`), `mProducedIn`.
- Machine (`FGBuildableManufacturer*`) : `mPowerConsumption`,
  `mPowerConsumptionExponent`, `mProductionShardSlotSize` (slots Somersloop).
- **Fluides** : `Amount` stocké en m³ × 1000 → divisé par `FLUID_SCALE`.
- Une recette n'est retenue que si elle est produite dans une machine connue
  (recettes à la main / build gun / établi écartées).
- `is_alternate` ⇔ clé préfixée `Recipe_Alternate_` **ou** nom affiché « Alternate: … »
  (certaines alternatives 1.1, ex. *Pure Aluminum Ingot*, n'ont pas le préfixe de
  classe) ; débit/min = `qté × 60 / durée`.

## Notes de modélisation (solveur)

- **`min_raw`** minimise l'**extraction** de bruts (variables `extract_i ≥ −net_i`),
  pas `−net_i` : sinon l'objectif serait non borné dès qu'une recette produit un
  brut en sous-produit (ex. eau).
- **Synthèse de bruts écartée** : les ressources brutes sont **extraites**, jamais
  fabriquées. Les recettes dont la **sortie principale est un brut** (Converter :
  SAM Ingot + minerai → autre minerai ; dépaquetage eau/pétrole) sont **toujours
  exclues** — sinon le mode inverse « synthétiserait » p. ex. du Caterium Ore au
  lieu de le miner. Les recettes produisant un brut en simple **sous-produit**
  (ex. Aluminum Scrap → ferraille + eau) restent disponibles.
- **Eau = brut illimité** : `Desc_Water_C` (ensemble `FREE_RAWS` dans `lp_model`) est
  disponible partout sans limite et **exclu de `min_raw`** (l'eau du jeu est gratuite,
  l'optimiseur ne doit pas la fuir). Elle reste **recyclée** : le bilan net réinjecte
  les sous-produits d'eau dans les recettes qui en consomment ; seul le **vrai surplus**
  (produit > consommé) est du rebut (montré « à évacuer » dans le graphe).
- **Somersloop** (§4.5) : amplification `amp = 1 + sloops/(machines·slots)`
  (plein → ×2 sortie), puissance `× amp^e` (e = `mProductionBoostPowerConsumptionExponent`
  lu depuis `Docs.json`, =2 en 1.0/1.1 → plein ×4). Allouée en post-solveur,
  glouton, sur les étapes produisant la cible (amplifier un intermédiaire ne
  ferait que du surplus).
