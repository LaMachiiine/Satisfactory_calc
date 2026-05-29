# Design — Mode Direct par défaut + persistance item/réglages au changement d'alternatives

Date : 2026-05-29
Statut : validé (l'utilisateur a demandé l'implémentation directe)

Deux petits ajustements de l'UI Streamlit (`ui/app.py`). Pas de nouvelle dépendance.

## ① Mode « Direct » par défaut

La radio « Mode » démarre sur Inverse (`index=1`). Passer à **Direct** (`index=0`).

## ② Garder l'item cible + les réglages quand on change les recettes alternatives

**Problème** : la liste « Item cible » est construite depuis les recettes **activées**
(`_produced_items(work)`). Cocher/décocher une alternative change le jeu de recettes
activées, donc potentiellement les options de la liste → Streamlit voit un widget
différent et **réinitialise** la sélection (et l'utilisateur perd son plan).

**Fix** :
1. **Liste d'items stable** : alimenter la liste depuis le **catalogue complet**
   (`_produced_items(repo)` sur le repo de base, qui a toutes les recettes activées —
   `load_repo(... enable_alternates=True)`), indépendant de la sélection d'alternatives.
   Le repo **filtré** (`work`) reste utilisé pour **résoudre** le plan.
2. **Clés stables** sur les widgets du planificateur (`planner_mode`, `planner_target`,
   `fwd_rate`, `fwd_objective`, `fwd_sloops`, `inv_source`, `inv_raws`) pour que
   Streamlit conserve leurs valeurs à travers le re-run déclenché par le changement
   d'alternatives.

**Résultat** : item + réglages conservés ; comme Streamlit re-exécute le script à
chaque changement, **le plan se recalcule automatiquement** avec le nouveau jeu de
recettes. Cas limite : item produit uniquement par une alternative désactivée →
`solve_*` lève `ValueError` → déjà capturé et affiché (`except ValueError`).

## Architecture / interfaces

- `render()` : calcule `item_catalog = _produced_items(repo)` (base) et le passe à
  `_planner_tab(work, sb, realize, item_catalog)`.
- `_planner_tab(repo, sb, realize, items)` : utilise `items` (catalogue) pour la liste
  déroulante, `repo` (= `work`) pour résoudre ; ajoute les clés ci-dessus ; `Mode`
  passe à `index=0`.

## Tests (`tests/test_app.py`, harnais `AppTest`)

- `test_app_defaults_are_direct_and_max100` (remplace la version « inverse ») : Mode = Direct.
- `test_app_inverse_defaults_to_map_deposits` : bascule d'abord en Inverse, puis vérifie
  « Source des bruts » = Gisements.
- `test_app_target_options_stable_across_alternates` : les options « Item cible » sont
  identiques avant/après avoir coché une alternative.
- `test_app_keeps_target_when_toggling_alternates` : l'item sélectionné est conservé
  après avoir coché une alternative.

## Hors périmètre

Le couplage distance↔LP et les sources « factory output » (③) : design séparé.
