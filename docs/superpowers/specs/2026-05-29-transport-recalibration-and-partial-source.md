# Design ⑤⑥ — Recalibrage transport + source partielle séparée

Date : 2026-05-29
Statut : validé (implémentation TDD)

## ⑤ Recalibrage de la recommandation de transport

### Problème (diagnostic)
1. Le coût de distance n'est **pas** multiplié par le nombre de lignes :
   `cost = setup + cost_per_m·dist + (cost_per_unit+complexity)·units`. Or *N* tapis
   parallèles sur une longue distance coûtent ~*N*×. Résultat : gros débit longue
   distance en tapis paraît anormalement bon marché.
2. `cost_per_m` du **train** (4.0) > **tapis** (2.0) + gros `setup` → le train ne peut
   jamais rattraper le tapis quand la distance croît → **jamais recommandé**. Le
   **camion** est de même écrasé par le **drone** (`cost_per_m`=0.2, débit non pénalisé).

### Solution
1. **Flag `continuous: bool`** sur `ModeProfile` : `True` pour tapis et pipeline
   (infrastructure continue → lignes parallèles), `False` pour camion/train/drone
   (véhicules sur une route/voie unique).
2. **Coût de distance ×lignes pour l'infra continue** dans `evaluate` :
   `dist_cost = cost_per_m · dist_m · (units if p.continuous else 1)`.
   (Inchangé pour les véhicules : la voie/route est posée une fois ; les unités
   ajoutent du coût véhicule via `cost_per_unit`.)
3. **Recalibrage** des profils (`solid`/`fluid` inchangés) :

   | mode  | continuous | setup | cost_per_m | cost_per_unit | complexity |
   |-------|-----------|-------|-----------|---------------|-----------|
   | belt  | True      | 0     | 1.5       | 0             | 15        |
   | pipe  | True      | 50    | 2.0       | 0             | 15        |
   | truck | False     | 400   | 0.6       | 300           | 80        |
   | train | False     | 2500  | 0.4       | 200           | 30        |
   | drone | False     | 700   | 0.1       | 600           | 50        |

### Résultat (grille de décision, solides, pile 100)
```
 rate\dist   50m    250m   750m   2000m  5000m  12000m
 1200/min   belt   belt   belt   truck  truck  train
  780/min   belt   belt   belt   truck  truck  train
  480/min   belt   belt   belt   truck  truck  drone
  240/min   belt   belt   belt   truck  drone  drone
  120/min   belt   belt   belt   drone  drone  drone
   60/min   belt   belt   belt   truck  drone  drone
```
tapis (court) · camion (moyen) · train (long + gros débit) · drone (long + faible débit).
Fluides : pipeline (court/moyen) · train wagon-citerne (long).

### Tests (`tests/test_transport.py`)
- Le coût tapis **scale avec les lignes** : `evaluate` d'un débit > 1200 sur une longue
  distance coûte plus cher que le même débit ≤ 1200 (units 2 vs 1, distance ×2).
- **Train gagne** en long + gros débit (ex. 1200/min @ 12000 m → `recommend().mode == "train"`).
- **Camion gagne** en distance moyenne (ex. 480/min @ 2000 m → "truck").
- **Drone gagne** en long + faible débit (ex. 120/min @ 5000 m → "drone").
- **Tapis gagne** en courte distance (ex. 1200/min @ 250 m → "belt").
- Fluide longue distance → "train" ; fluide court → "pipe".

## ⑥ Source partielle séparée (Chaîne complète)

Quand un item est **à la fois** fourni en externe (source perso) **et** produit en
interne (cap externe < besoin), `build_plan_graph` **scinde** chaque arête entrante
de cet item :
- fraction externe `frac = min(1, débit_externe / besoin_total)` où
  `débit_externe = plan.raw_consumed[item]` (les entrées externes y figurent) et
  `besoin_total = consumed[item]` ;
- arête depuis le **carré bleu 🏭** (`custom_source`) au débit `rate·frac` ;
- arête depuis l'**étape productrice** au débit `rate·(1−frac)`.

Cas limites : entièrement externe (pas de producteur interne) → 1 arête depuis 🏭
(comportement ④ actuel) ; non externe → inchangé. Les **vues par étape** gardent le
marqueur 🏭 binaire (la scission n'a de sens qu'au niveau global).

### Tests (`tests/test_plan_graph.py`)
- Item partiellement externe (ex. Mid produit 6/min, fourni 4/min, consommé 10/min) :
  le graphe contient **un nœud `custom_source`** ET une arête depuis l'étape
  productrice ; débits scindés ≈ 4 (🏭) et ≈ 6 (interne).

## Hors périmètre
- Frontières exactes de la grille (calibrage subjectif, ajustable ensuite).
- Empaquetage fluides (tapis/camion/drone pour fluides) : déjà hors périmètre.
