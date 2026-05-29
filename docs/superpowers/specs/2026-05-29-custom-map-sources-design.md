# Design ③ — Sources personnalisées sur la carte (factory output)

Date : 2026-05-29
Statut : validé (implémentation en 3 phases avec checkpoints)

## Objectif

Permettre à l'utilisateur de **poser sur la carte des sources d'un item manufacturé**
(ex. « ici, une usine produit 20 plastique/min »), persistées, et de les utiliser :
1. comme **entrées disponibles** pour le solveur (le plan cesse de fabriquer cet item
   en interne, jusqu'au débit déclaré) ;
2. comme **sources** dans la localisation d'usine (l'usine est placée en tenant compte
   de ces points, au même titre que les gisements de bruts).

C'est le couplage « `factory_output` / clusters d'entrée » annoncé « à venir » (README
Phase 6, spec §5ter).

## Contraintes / principes

- Persistance par projet dans un JSON à la racine (`custom_sources.json`), comme
  `nodes_state.json`. `nodes.json` (statique) n'est pas touché.
- Cœur (solveur/siting) sans dépendance UI ; logique testable hors Streamlit.
- Comportement existant des bruts **inchangé** (aucun test cassé).
- L'interaction clic-carte (st_folium) n'est pas testable via `AppTest` (composant) :
  on factorise la **logique** en fonctions pures testées, l'UI ne fait que les câbler.

## Composants & interfaces

### A. Données & persistance — `nodes/custom.py` (nouveau)
```python
class CustomSource(BaseModel):
    id: str            # identifiant stable (généré)
    item: str          # clé d'item (ex. "Desc_Plastic_C")
    rate_per_min: float
    x: float           # coords monde (cm), comme les gisements
    y: float
    label: str = ""    # libellé optionnel

def load_custom_sources(path) -> list[CustomSource]      # [] si absent
def save_custom_sources(sources, path) -> None
def add_source(sources, item, rate, x, y, label="") -> list[CustomSource]   # pur : renvoie une nouvelle liste + id généré
def remove_source(sources, source_id) -> list[CustomSource]                 # pur
```
`DEFAULT_CUSTOM_PATH = "custom_sources.json"`. ID = `f"cs_{item}_{n}"` (n = 1 + max
index existant pour cet item) → stable et lisible, sans horloge/aléa.

### B. Carte — `ui/map_view.py` + `ui/app.py` (`_map_tab`)
- `latlng_to_world(lat, lng) -> (x, y)` : inverse de `world_to_latlng` (`x=lng*_SCALE`,
  `y=-lat*_SCALE`).
- `build_folium_map(...)` : nouvel argument optionnel `custom_sources` → ajoute un
  marqueur **🏭** distinct (DivIcon) par source, tooltip « item — débit/min ».
- `_map_tab` : radio **mode** en haut — « Disponibilité gisements » (actuel) /
  « ➕ Ajouter une source ». En mode ajout :
  - selectbox *item* (noms via `repo.items`) + number_input *débit/min* ;
  - la carte renvoie `last_clicked` ; à un **nouveau** clic → `latlng_to_world` →
    `add_source(...)` → `save_custom_sources` → `st.rerun()` ;
  - **liste** des sources existantes avec bouton **🗑 Supprimer** (→ `remove_source`).
  - En mode « Disponibilité », clics = toggle gisement (comportement actuel inchangé).

### C. Solveur — `solver/lp_model.py` + `solver/modes.py`
- `build_forward` : généraliser `available`. Pour un item **non-brut** présent dans
  `available` (et non-cible), ajouter `net_expr(ik) >= -available[ik]` (consommable
  jusqu'au cap). Les bruts gardent leur traitement actuel ; un item hors `available`
  garde `net >= 0`.
- `solve_forward` : `consumed_keys = model.raw_keys + [k for k in available
  if k in repo.items and not repo.items[k].is_raw]` → `_make_plan` reporte ces
  entrées externes dans `plan.raw_consumed` (consommation nette).
- `solve_max_output` : déjà compatible (`consumed_keys = list(available)`).
- Effet : `plan.raw_consumed` = bruts **+** entrées externes consommées.

### D. Planificateur — `ui/app.py` (`_planner_tab`)
- Charger les sources perso ; agréger `custom_caps = {item: Σ rate_per_min}`.
- Case à cocher **« Utiliser mes sources perso comme entrées disponibles »**
  (`key="use_custom_sources"`), visible si des sources existent.
- Si cochée : fusionner `custom_caps` dans le dict `available` passé à `solve_forward`
  (mode Direct, sinon `None`) **et** à `solve_max_output` (mode Inverse, en plus des
  bruts carte/manuels).

### E. Localisation — `siting/sources.py` + `ui/app.py` (`_locate_tab`)
- `build_sources(nodes, states, items_needed, *, belt_capacity=None,
  custom_sources=None)` : après les gisements, ajouter chaque `CustomSource` dont
  `item ∈ items_needed` comme `Source(item, x, y, capacity_per_min=rate_per_min,
  kind="factory_output", id=cs.id)`.
- `_locate_tab` : charger les sources perso ; `demand = plan.raw_consumed` (inclut
  désormais les entrées externes) ; `build_sources(..., custom_sources=...)`. Le reste
  (locate_factory, carte, transport) fonctionne tel quel ; les liaisons depuis une
  source `factory_output` apparaissent comme les autres.

## Flux de données
`custom_sources.json` → `_planner_tab` (agrège `custom_caps`, coche) → `solve_*`
(`available` += caps) → `plan.raw_consumed` (bruts + externes) → `_locate_tab`
(demande + `build_sources(custom_sources)`) → `locate_factory` → carte.

## Gestion d'erreurs
- Source perso d'un item que le plan ne consomme pas → simplement ignorée par la
  localisation (pas dans `items_needed`).
- Débit ≤ 0 ou item non choisi à l'ajout → bouton/clic sans effet (validation).
- Cap externe ≥ besoin → l'item disparaît du plan (0 machine) ; pénurie gérée par
  `shortfalls` côté localisation si la position manque de capacité.

## Tests
- **Solveur** (`tests/test_solver.py`) : `solve_forward` avec une entrée externe
  non-brute (ex. item intermédiaire fourni) → le plan le consomme, `raw_consumed`
  l'inclut, et l'extraction de bruts amont diminue vs sans la source.
- **Persistance** (`tests/test_custom_sources.py`) : `add_source`/`remove_source`
  (pur) + round-trip `save`/`load`.
- **Siting** (`tests/test_sources.py` ou `test_siting.py`) : `build_sources` inclut
  une `CustomSource` (kind `factory_output`) quand son item est demandé, l'exclut sinon.
- **Conversion** (`tests/test_map_view.py`) : `latlng_to_world` ∘ `world_to_latlng` = identité.
- **AppTest** (`tests/test_app.py`) : le mode « Ajouter une source » s'affiche sans
  exception ; une source présente dans `custom_sources.json` (fixture/tmp) apparaît
  dans la liste. (Le clic carte lui-même n'est pas simulable via AppTest.)

## Phasage (checkpoints : `uv run pytest -q` vert entre chaque)
- **③-1** : A (données/persistance) + B (carte : ajout/affichage/suppression).
- **③-2** : C (solveur) + D (planificateur : caps externes).
- **③-3** : E (localisation).

## Hors périmètre
- Couplage géographique dans le LP (la distance n'entre pas dans l'objectif LP).
- Empaquetage fluides pour le transport (déjà hors périmètre Phase 7).
- Édition de la position d'une source existante (supprimer + reposer).
