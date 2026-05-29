# Spécification technique — Calculateur & distributeur Satisfactory

Outil Python de planification de production pour *Satisfactory* (1.1), couvrant le calcul de ratios par programmation linéaire **et** la génération du réseau logique de distribution (répartiteurs / groupeurs) avec gestion de la capacité des tapis.

---

## 1. Objectifs & périmètre

L'outil doit répondre à trois usages, à partir d'une même base de données de recettes :

1. **Mode direct (forward).** « Je veux *N* unités/min de l'item X » → nombre de machines par recette, ressources brutes consommées, puissance totale, sous-produits.
2. **Mode inverse (max-output).** « J'ai ces ressources en entrée (ex. 480 minerai de fer/min, 300 cuivre/min) → quelle est la **production maximale** de l'item cible que je peux en tirer ? » Le solveur maximise la sortie sous contrainte des entrées disponibles.
3. **Optimisation par recettes alternatives.** Possibilité d'activer tout ou partie des recettes alternatives ; le solveur choisit automatiquement la combinaison qui optimise l'objectif (max sortie, min ressources, min puissance, min machines).

À cela s'ajoutent quatre modules complémentaires :

- **Distributeur de capacité** (§5) : pour chaque liaison producteur → consommateurs, générer l'arbre de répartiteurs/groupeurs (/2, /3), avec le débit sur chaque tronçon, le repli en manifold pour les *N* non factorisables, et la gestion des lignes parallèles quand le débit dépasse la capacité d'un tapis.
- **Onglet carte & gisements** (§5bis) : afficher tous les gisements (positions, type, pureté) depuis des **données statiques**, avec un toggle manuel disponible/occupé par gisement qui alimente le solveur. Suivi d'occupation **manuel**, pas de lecture de l'état de la partie.
- **Recherche de clusters & localisation d'usine** (§5ter) : trouver les sources les plus proches et la position d'usine qui minimise la distance de transport, avec possibilité de poser des « clusters d'entrée » de n'importe quel item là où sont déjà des usines.
- **Transport inter-sites** (§5quater) : recommander le mode de transport (tapis / camions / trains / drones / pipelines) selon distance et débit, en consommant les liaisons produites par la localisation d'usine.

**Hors périmètre (volontairement) :**
- Le placement physique sur grille et le routage spatial des tapis. La sortie du distributeur est un **graphe logique**, pas un plan de construction.
- **L'import de la sauvegarde de partie (`.sav`).** On ne lit pas le binaire Unreal Engine. L'occupation des gisements est gérée à la main via l'onglet carte (§5bis), ce qui évite la fragilité du parsing liée aux versions du jeu.

---

## 2. Stack technique & dépendances

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Langage | Python ≥ 3.11 | Écosystème scientifique, lisibilité |
| Solveur | **OR-Tools** (`pywraplp`, GLOP/CBC) ou `PuLP` + CBC | OR-Tools gère LP continu **et** MILP entier, rapide, sans installation de solveur externe |
| Modèle de données | `pydantic` v2 / `dataclasses` | Validation, sérialisation JSON |
| Graphe | structure maison + export **DOT (graphviz)** ; `networkx` optionnel | Sortie « par graphe » sans rendu obligatoire |
| Parsing données jeu | module dédié lisant `Docs.json` | Source canonique du jeu |
| Gestion projet | **uv** (`uv sync`, `uv run`) | venv + dépendances reproductibles |
| UI | CLI `argparse` (réalisée) puis `Streamlit` | Prototypage rapide |

Principe : le **cœur** (modèle + solveur + distributeur) n'a aucune dépendance UI ; les interfaces sont des couches au-dessus.

---

## 3. Sources de données & modèle de données

### 3.1 Source canonique

Le fichier `Docs.json` livré avec le jeu (`<Satisfactory>/CommunityResources/Docs/Docs-<locale>.json`) contient toutes les recettes, durées, machines, puissances et exposants. C'est la source à parser ; aucune saisie manuelle des recettes n'est nécessaire (sauf le nombre de gisements par type, qui n'est pas dans le fichier).

À défaut du jeu, l'export communautaire [`dmryabov/satisfactory-docs-files`](https://github.com/dmryabov/satisfactory-docs-files) fournit un JSON propre au format `{GameVersion, Classes:[...]}`, déjà utilisé par l'implémentation. Voir les notes de format en §3.4.

Champs utiles côté recette : ingrédients, produits, durée de fabrication, bâtiment(s) de production. Côté machine : puissance de base et exposant de puissance (surcadençage), nombre de slots Somersloop.

### 3.2 Schéma normalisé

```python
class Item(BaseModel):
    key: str                 # identifiant stable (ex. "Desc_IronIngot_C")
    name: str                # nom affiché localisé
    is_fluid: bool
    is_raw: bool             # extrait d'un gisement (minerai, pétrole, eau...)

class Recipe(BaseModel):
    key: str
    name: str
    machine: str             # ex. "Build_SmelterMk1_C"
    duration_s: float        # durée d'un cycle à 100 %
    inputs:  dict[str, float]   # item_key -> quantité par cycle
    outputs: dict[str, float]   # item_key -> quantité par cycle
    is_alternate: bool
    # débit/min à 100 % = quantité * 60 / duration_s
    def rate_per_min(self, item_key: str) -> float: ...

class Machine(BaseModel):
    key: str
    name: str
    base_power_mw: float
    power_exponent: float = 1.321928   # exposant surcadençage des bâtiments de prod
    somersloop_slots: int = 0

class Belt(BaseModel):
    tier: int                # 1..6
    capacity_per_min: float  # 60, 120, 270, 480, 780, 1200
```

### 3.3 Recettes alternatives

Une recette alternative est une `Recipe` ordinaire avec `is_alternate=True` produisant un item déjà produit par une recette standard, avec un ratio différent. **Aucun traitement spécial dans le solveur** : il suffit de l'inclure (ou non) dans le pool de recettes candidates. « Activer toutes les alternatives » = passer l'ensemble complet au solveur.

### 3.4 Notes de format `Docs.json` (implémentation)

Tirées du parsing réel de l'export dmryabov :

- Recette : `Properties.mManufactoringDuration`, `mIngredients` / `mProduct` au format `[{ItemClass:{Name}, Amount}]`, et `mProducedIn` au format `[{Name}]`.
- **Fluides** : `Amount` est stocké en m³ × 1000 → diviser par une constante `FLUID_SCALE` (1000).
- Une recette n'est retenue que si elle est produite dans une **machine connue** (recettes à la main / build gun / établi écartées).
- `is_alternate` ⇔ nom de classe préfixé `Recipe_Alternate_`.
- Débit/min à 100 % = `quantité × 60 / durée_cycle_s`.

> **Qualité des libellés (export dmryabov)** : les `mDisplayName` de recettes sont corrompus (plusieurs recettes partagent un nom erroné) ; les **valeurs numériques restent correctes**. Contournement retenu : libeller chaque recette par le nom de son **item produit** (fiable), suffixé `(alt: …)` pour les alternatives. Brancher le vrai `Docs.json` du jeu redonnerait des noms corrects.

---

## 4. Modèle d'optimisation (le solveur)

### 4.1 Variables

Pour chaque recette candidate *r* : une variable continue `x_r ≥ 0` = nombre de machines-équivalent tournant la recette *r* à 100 %. Une valeur fractionnaire est autorisée à ce stade (réalisée plus tard en machines entières + horloge, §4.5).

On note `rate(r, i)` le débit net/min de l'item *i* pour une machine de la recette *r* à 100 % : positif si *r* produit *i*, négatif si *r* consomme *i*.

### 4.2 Bilan par item (contrainte commune à tous les modes)

Pour chaque item *i*, on définit le flux net :

```
net_i = Σ_r  x_r * rate(r, i)
```

- **Intermédiaires** (ni cible, ni brut) : `net_i ≥ 0` — on ne consomme pas plus qu'on ne produit. (Mettre `= 0` pour interdire tout surplus, ou `≥ 0` pour le tolérer.)
- **Bruts** (`is_raw`) : la consommation est bornée par la disponibilité, `net_i ≥ -avail_i`.
- **Cible(s)** : selon le mode (ci-dessous).

### 4.3 Mode direct (forward)

```
Contraintes :
    net_target ≥ demande_target           (objectif de production atteint)
    net_i ≥ 0                              ∀ intermédiaire i
    net_i ≥ -avail_i                       ∀ brut i   (avail = +∞ si non borné)

Objectif (au choix, paramétrable) :
    min  Σ_{i brut}  (-net_i)              # minimiser les ressources brutes
  ou min Σ_r x_r * power(r)                # minimiser la puissance
  ou min Σ_r x_r                           # minimiser le nombre de machines
```

### 4.4 Mode inverse (maximisation de sortie sous contrainte d'entrées)

C'est le mode « j'ai ces ressources, fais-en le maximum ».

```
Données :  cap_i  = débit max disponible de chaque ressource d'entrée fournie

Contraintes :
    consommation_i ≤ cap_i   ⇔   net_i ≥ -cap_i     ∀ entrée fournie i
    net_i ≥ 0                                        ∀ intermédiaire i
    (les autres bruts non fournis : cap = 0, donc net_i ≥ 0 → interdits)

Objectif :
    max  net_target
```

Le solveur explore alors toutes les recettes activées (standard + alternatives) pour transformer au mieux les entrées disponibles en l'item cible. Variante multi-cible : maximiser une combinaison pondérée `Σ w_t · net_t`, ou les points AWESOME.

### 4.5 Réalisation : machines entières, horloge, Somersloop

Le `x_r` continu donne le **ratio idéal**. Pour le rendre constructible :

- **Sous-cadençage exact (recommandé) :** `machines_r = ceil(x_r)`, puis horloge = `x_r / machines_r × 100 %` (≤ 100 %, pas de Power Shard requis, débit pile-poil).
- **Sur-cadençage :** garder `floor` ou un entier choisi et monter l'horloge jusqu'à 250 % max (coûte des Power Shards).

Puissance réalisée d'une recette :

```
power_r = base_power(machine_r) * machines_r * (clock/100) ** 1.321928
```

(Les **générateurs** scalent linéairement : exposant 1.0, puissance et carburant proportionnels à l'horloge.)

**Somersloop (amplification) :** multiplicateur de sortie `amp ∈ {1.0 … 2.0}` selon les slots utilisés, **sans** augmenter les entrées. Modélisation : soit une variable par recette avec `outputs *= amp`, soit une étape post-solveur qui place un budget de Somersloops sur les recettes au plus fort gain. Coût : puissance jusqu'à ×4 du facteur d'amplification ; une machine pleinement amplifiée **et** à 250 % consomme ≈ 13,431× sa puissance de base. Ressource finie (106 dans la 1.0) → la traiter comme un budget à allouer, pas comme illimitée.

### 4.6 Sous-produits & boucles

La formulation par bilan net gère **nativement** les sous-produits (ex. résidu d'huile lourde) et les boucles de recyclage (plastique/caoutchouc réinjectés) : ce sont juste des items avec des `rate(r,i)` de signes opposés sur plusieurs recettes. Pour éviter les sous-produits inutiles, ajouter une petite pénalité sur les surplus dans l'objectif, ou autoriser un « puits » (sink) explicite pour les items dont on accepte la perte.

---

## 5. Module distributeur de capacité

C'est la couche originale, en aval du solveur.

### 5.1 Entrée / sortie

```python
def build_distribution(
    item_key: str,
    total_rate: float,        # débit total à distribuer (objets/min)
    n_consumers: int,         # nombre de machines consommatrices
    per_consumer_rate: float, # débit requis par machine
    belt_capacity: float,     # capacité du tier de tapis retenu
    strategy: str = "auto",   # "tree" | "manifold" | "auto"
) -> DistributionGraph: ...
```

`DistributionGraph` : nœuds typés (`source`, `splitter_2`, `splitter_3`, `merger_2`, `merger_3`, `machine`) et arêtes portant un débit. Exports : DOT (graphviz), JSON, et résumé textuel (compte de répartiteurs/groupeurs, charge max d'arête, alertes capacité, tier de tapis conseillé par tronçon).

### 5.2 Stratégie « arbre équilibré » (N factorisable en 2 et 3)

Un répartiteur divise en 2 ou 3 flux **égaux**. Donc une division propre en *N* flux égaux n'est possible que si `N = 2^a · 3^b`.

```
build_tree(parent, rate, n):
    si n == 1:
        relier parent -> machine (débit = rate)
        retour
    f = 3 si n % 3 == 0 sinon 2 si n % 2 == 0 sinon ÉCHEC
    sp = nouveau répartiteur (1 -> f)
    relier parent -> sp (débit = rate)
    pour chaque branche en 1..f:
        build_tree(sp, rate / f, n / f)
```

Greedy par 3 d'abord → minimise la profondeur et le nombre de répartiteurs. Si la factorisation échoue (N contient un facteur premier ≠ 2,3 : 5, 7, 11…), basculer en manifold.

### 5.3 Stratégie « manifold » (universelle, tout N)

Tronçon unique le long des machines ; à chaque machine, un répartiteur 1→2 prélève la part de la machine et laisse passer le reste. `N−1` répartiteurs (la dernière machine prend le résidu). S'auto-équilibre par contre-pression en régime permanent. Contrainte : le **tronçon de tête** porte `total_rate`, donc doit respecter la capacité du tapis.

```
manifold(source, total, n, q):
    prev = source ; reste = total
    pour i en 1..n-1:
        sp = répartiteur 1->2
        relier prev -> sp (débit = reste)
        relier sp -> machine_i (débit = q)
        reste -= q ; prev = sp
    relier prev -> machine_n (débit = reste)   # = q
```

### 5.4 Gestion de la capacité des tapis (le « distributeur de capacité »)

Avant de distribuer, contrôler chaque débit contre la capacité du tapis :

1. **Lignes parallèles en amont.** Si `total_rate > belt_capacity`, il faut `P = ceil(total_rate / belt_capacity)` lignes parallèles depuis la source. Deux cas :
   - **Tree :** répartir les `n_consumers` en `P` sous-groupes équilibrés, un arbre par ligne ; si les groupes ne sont pas égaux, signaler et proposer le tier supérieur.
   - **Manifold :** `P` manifolds parallèles, chacun nourrissant `n_consumers / P` machines.
2. **Arêtes internes.** Toute arête dont le débit dépasse `belt_capacity` est marquée ; le générateur insère un dédoublement ou conseille un tier supérieur pour ce tronçon.
3. **Groupeurs.** Apparaissent (a) pour recombiner plusieurs producteurs vers un même groupe de machines, (b) en miroir de l'arbre de répartiteurs (`merge_tree`, dual exact du `build_tree`), (c) pour le rééquilibrage à retour des *N* « moches » (optionnel, avancé).
4. **Sélection du tier de tapis par tronçon.** Pour chaque arête, retenir le **tier le moins cher** dont la capacité ≥ débit du tronçon, pour économiser les matériaux (un tronçon à 40/min n'a pas besoin d'un Mk.5).

### 5.5 Cas des *N* non factorisables, proprement

Pour un *N* contenant 5, 7, etc., trois options offertes à l'utilisateur :
- **Manifold** (défaut, simple, toujours valable).
- **Équilibreur à retour** : produire le plus petit `2^a·3^b ≥ N` sorties, puis réinjecter le surplus via groupeurs jusqu'au ratio exact (réseau plus complexe, à implémenter en phase ultérieure).
- **Sur-débit assumé** : `N` sorties via un arbre plus large, certaines machines partiellement alimentées (à éviter en général).

---

## 5bis. Module gisements & carte interactive

Onglet permettant de visualiser les gisements du monde et de gérer leur disponibilité à la main, sans aucune lecture de sauvegarde.

### 5bis.1 Données statiques (intégrées, pas d'import)

Positions, type, pureté et forme des gisements sont fixes et ne dépendent pas de la partie. On intègre `data/nodes.json` (donnée communautaire ouverte) ; schéma :

```python
class ResourceNode(BaseModel):
    id: str                 # identifiant stable du gisement
    resource: str           # item_key extrait (ex. "Desc_OreIron_C")
    purity: str             # "impure" | "normal" | "pure"
    form: str               # "solid" | "liquid"
    x: float; y: float; z: float   # coordonnées monde (unités UE, cm)
```

Repères de volume (monde 1.0, indicatif) : fer ≈ 39 impurs / 42 normaux / 46 purs, cuivre ≈ 13 / 29 / 13, charbon ≈ 15 / 31 / 16, etc.

### 5bis.2 État de disponibilité (par projet, persisté)

`nodes.json` n'est pas modifié ; un fichier séparé `project/nodes_state.json` porte la configuration par gisement :

```python
class NodeState(BaseModel):
    available: bool = True      # False = occupé / réservé, exclu du solveur
    miner_tier: int = 1         # 1..3 (impacte le débit max)
    clock: float = 100.0        # 1..250 (%)
    somersloop: bool = False
```

Toggle d'un clic sur la carte → bascule `available`. Dernier-écrit-gagne, sauvegarde immédiate.

### 5bis.3 Débit d'extraction par gisement

```
base_par_pureté (Mineur Mk.1) : impure 30 / normal 60 / pure 120  (objets/min)
multiplicateur de tier        : Mk.1 ×1, Mk.2 ×2, Mk.3 ×4
débit_max = base × tier × (clock/100) × (2 si somersloop sinon 1)
plafonné par la capacité du tapis retenu
```

Un nœud pur + Mk.3 + surcadençage atteint 780–1200/min → déclenche directement les lignes parallèles du distributeur (§5.4).

### 5bis.4 Intégration au solveur

Chaque gisement **disponible** devient une recette d'extraction plafonnée par son `débit_max`. En mode inverse, l'ensemble des gisements disponibles d'un type fournit le plafond d'entrée total de cette ressource. Objectifs additionnels : minimiser le nombre de gisements occupés, privilégier les nœuds purs, ou pondérer par la distance si un point d'usine est fourni.

### 5bis.5 Rendu de la carte

Fond de carte (image du monde, donnée communautaire) + marqueurs cliquables projetés depuis les coordonnées monde via une transformation affine (bornes monde → pixels). Pile recommandée : **Leaflet** ; en contexte Python/Streamlit, `streamlit-folium` gère des marqueurs cliquables renvoyant l'événement à Python. Code couleur par pureté, opacité réduite pour les gisements occupés.

---

## 5ter. Module recherche de clusters & localisation d'usine

À partir des ressources requises par un plan, trouver les **sources** les plus proches et la **position d'usine** qui minimise la distance de transport. Réutilise les coordonnées de `nodes.json` et la carte (§5bis).

### 5ter.1 Problème

Deux décisions couplées : (1) **sélection** — pour chaque item requis, choisir des sources dont la capacité cumulée ≥ débit demandé ; (2) **localisation** — choisir la position d'usine `P` minimisant le coût de transport. Type *capacitated facility location* ; petites instances → solvable exactement ou par heuristique rapide.

### 5ter.2 Sources (gisements ∪ usines ∪ entrées manuelles)

```python
class Source(BaseModel):
    item: str               # item_key fourni
    x: float; y: float; z: float
    capacity_per_min: float
    kind: str               # "node" | "factory_output" | "manual_input"
```

- `node` : gisement disponible (capacité = débit max d'extraction).
- `factory_output` : surplus d'une usine sauvegardée, à sa position.
- `manual_input` : **pin posé par l'utilisateur** déclarant « ici, item X dispo à R/min ». Permet de poser des clusters d'entrée de n'importe quel item là où sont les usines.

### 5ter.3 Objectif

Distance euclidienne sur les coordonnées monde (cm ; afficher en m via /100). Deux métriques :

- **(défaut) Distance de transport pondérée** : `min Σ_s (débit_routé_s × dist(s, P))` — la plus juste (longueur de tapis × débit ≈ coût réel).
- **(alternative) Compacité du cluster** : minimiser le diamètre du groupe retenu.

### 5ter.4 Algorithme

1. **Pré-clustering** des sources par item (DBSCAN / grille) → régions denses, élague les candidats.
2. **Candidats de site** : centroïdes de clusters + positions de gisements proches.
3. **Pour chaque candidat** : sélectionner les sources par distance croissante jusqu'à couvrir la demande de chaque item (glouton / min-cost flow respectant les capacités) → coût.
4. **Raffinement continu** : recalculer la position optimale comme **médiane géométrique pondérée** (point de Weber) via **Weiszfeld** ; re-sélectionner si la position bouge, itérer (style Lloyd).

Exact possible en MILP CP-SAT avec sites candidats discrets ; le glouton + Weber suffit en pratique.

### 5ter.5 Couplage avec le solveur

- **Décorrélé (défaut)** : le LP fixe la production (quels items sont importés) ; le module spatial place et sélectionne ensuite. Rapide, suffisant.
- **Couplé (avancé, ultérieur)** : coût d'import dépendant de la distance dans le LP, pour arbitrer « fabriquer sur place vs importer de loin ».

### 5ter.6 Sortie

Position(s) d'usine, sources retenues par item (débit routé + distance), coût de transport total, clusters alternatifs classés. Rendu sur la carte (§5bis) : clusters surlignés, pin d'usine, lignes vers les sources.

---

## 5quater. Module transport inter-sites (sélection de mode)

Pour chaque liaison `source → usine` (produite par §5ter), recommander **le mode de transport** selon distance et débit, et dimensionner l'infrastructure. Couche en aval de la localisation d'usine.

### 5quater.1 Profils des modes

| Mode | Débit | Distance idéale | Particularités |
|------|-------|-----------------|----------------|
| Tapis | tier × n (60→1200/min) | courte | aucune énergie, coût ~linéaire en distance |
| Camions/tracteurs | moyen | moyenne | trajets enregistrés, carburant, peu d'infra |
| Trains | très élevé | moyenne–longue | coût fixe élevé amorti, débit dépendant de la taille de pile |
| Drones | faible | longue | ignorent le terrain, logistique de batteries |
| Pipelines | 300/600 m³/min | fluides | headlift + pompes ; ou empaqueter le fluide |

### 5quater.2 Formules de débit par mode

```
Tapis     : capacité_tier × n_tapis
Train     : taille_pile × 32 × n_wagons / durée_aller-retour    (wagon = 32 slots, 1600 m³ fluide)
Drone     : 9 × taille_pile / durée_aller-retour                (9 slots ; aller-retour min ≈ 102 s : 51 s décollage + 51 s atterrissage)
Camion    : inventaire × taille_pile × trajets/min
```

La taille de pile vient du `Docs.json` déjà parsé. La durée d'aller-retour dépend de la distance, de la vitesse du véhicule et des temps d'animation.

### 5quater.3 Modèle de coût & sélection

Pour chaque liaison `(item, débit, distance)` : pour chaque mode applicable, calculer faisabilité (un fluide ne va pas sur tapis sans empaquetage), nombre d'unités `ceil(débit / débit_unitaire)`, et coût total = matériaux (fixe + variable × distance) + énergie + poids « complexité ». Recommander le mode de coût minimal, en exposant le détail (nombre de wagons/drones/tapis, coût amorti par item) et l'écart avec les alternatives — d'où le « opti ou non ».

### 5quater.4 Carte de décision

Précalculer, pour une taille de pile donnée, le mode gagnant sur tout le plan (distance × débit) → régions colorées. Outil d'intuition : courte distance → tapis ; fort débit moyenne/longue distance → trains ; distance moyenne faible débit → camions ; longue distance faible débit → drones. Les frontières exactes sortent du modèle de coût.

### 5quater.5 Conception de réseau (avancé, ultérieur)

Quand plusieurs liaisons partagent une zone, une seule ligne de train multi-gares ou un hub de drones peut battre le point-à-point → problème de conception de réseau (arbre de Steiner / localisation de hubs). À garder pour plus tard ; les §5quater.1–4 couvrent l'essentiel.

### 5quater.6 Données nécessaires

Un `transport_constants.py` (vitesses, capacités, slots, temps d'animation, coûts de construction par mode), calibré une fois. Les fluides suivent une carte de décision séparée (pipelines, ou empaquetage pour réutiliser les autres modes).

---

## 6. Architecture logicielle

```
src/satisfactory_planner/
├── data/
│   ├── docs_parser.py      # Docs.json -> schéma normalisé
│   └── game_constants.py   # tapis, pipes, exposants, Somersloop, mineurs, transport
├── model/
│   ├── entities.py         # Item, Recipe, Machine, Belt (pydantic)
│   └── repository.py       # chargement, filtres (activer/désactiver alternatives)
├── solver/
│   ├── lp_model.py         # construction des variables/contraintes
│   ├── modes.py            # forward, max_output, objectifs
│   ├── realize.py          # machines entières, horloge, Somersloop, puissance
│   └── result.py           # structure de plan (steps, puissance, bruts, sous-produits)
├── distribution/
│   ├── graph.py            # DistributionGraph + export DOT/JSON
│   ├── tree.py             # arbre équilibré /2 /3
│   ├── manifold.py         # repli manifold
│   └── capacity.py         # lignes parallèles, tiers, groupeurs
├── nodes/
│   ├── data.py             # chargement nodes.json (statique)
│   ├── state.py            # nodes_state.json (disponibilité, persistance)
│   └── extraction.py       # débit_max par gisement (pureté/tier/clock/sloop)
├── siting/
│   ├── sources.py          # Source unifiée (node | factory_output | manual_input)
│   ├── clustering.py       # pré-clustering DBSCAN / grille
│   ├── selection.py        # sélection sous capacité (glouton / min-cost flow)
│   └── weber.py            # médiane géométrique pondérée (Weiszfeld)
├── transport/
│   ├── modes.py            # profils & formules de débit par mode
│   └── select.py           # modèle de coût, recommandation, carte de décision
├── api.py                  # façade publique
└── ui/
    ├── cli.py              # CLI (argparse)
    ├── app.py              # streamlit (optionnel)
    └── map_view.py         # onglet carte (Leaflet / streamlit-folium)

data/                       # à la racine : Docs.json (entrée) + recipes.json (cache généré) + nodes.json
```

Responsabilités : `data` ne connaît que le format jeu ; `model` est pur ; `solver` ne dépend que de `model` (+ `nodes` pour les recettes d'extraction) ; `distribution` ne dépend que de `model` ; `nodes` est autonome ; `siting` dépend de `nodes` (sources) ; `transport` dépend de `siting` (liaisons) et de `model` (tailles de pile) ; `ui` orchestre via `api`. Écart assumé : le `Docs.json` d'entrée et le `recipes.json` généré vivent dans `data/` à la racine (hors du package importable), pas dans le package.

---

## 7. API publique (signatures cibles)

```python
# Chargement
repo = Repository.from_docs("Docs-en-US.json", enable_alternates=True)
repo = repo.with_recipes_enabled(["Recipe_Alternate_..."])   # filtre fin

# Mode direct
plan = solve_forward(
    repo, targets={"Desc_ModularFrame_C": 10},
    objective="min_raw",            # min_raw | min_power | min_machines
    available={"Desc_OreIron_C": 480},  # bornes optionnelles
)

# Mode inverse : maximiser la sortie avec les entrées disponibles
plan = solve_max_output(
    repo, target="Desc_ModularFrame_C",
    available={"Desc_OreIron_C": 480, "Desc_OreCopper_C": 240},
)

# plan -> liste de (recette, x, machines, horloge, puissance), bruts, sous-produits
plan.summary()        # tableau lisible
plan.power_total_mw   # puissance totale

# Distribution pour une étape du plan
for step in plan.steps:
    g = build_distribution(
        item_key=step.main_output, total_rate=step.output_rate,
        n_consumers=step.machines, per_consumer_rate=step.per_machine_rate,
        belt_capacity=270, strategy="auto",
    )
    g.to_dot("etape.dot")     # rendu via `dot -Tpng` si souhaité
    g.report()                # répartiteurs, groupeurs, charges, alertes
```

---

## 8. Interfaces utilisateur

- **CLI (phase 1).** `planner forward "Modular Frame" 10 --objective min_power` et `planner max "Modular Frame" --iron 480 --copper 240 --alternates all`. Sortie : tableau du plan + fichiers DOT par étape.
- **Streamlit (phase 3, optionnel).** Sélection de l'item, des entrées disponibles, cases à cocher des recettes alternatives, choix de l'objectif ; affichage du plan + diagramme de Sankey + graphes de distribution. Aucun rendu de placement.

---

## 9. Formats de sortie

1. **Plan de production** : par recette, `x` idéal, machines entières, horloge %, puissance, bruts consommés, sous-produits.
2. **Graphe de distribution** : DOT (visualisable hors outil), JSON (réutilisable), résumé textuel. Annotations par arête : débit, tier de tapis conseillé, alerte si > capacité.
3. **Diagramme de Sankey** (optionnel) : pour la vue d'ensemble des flux du plan.

---

## 10. Constantes de jeu à respecter

| Élément | Valeur |
|--------|--------|
| Tapis Mk.1 → Mk.6 | 60 / 120 / 270 / 480 / 780 / 1200 objets/min |
| Mineur (impure / normal / pure) | Mk.1 : 30 / 60 / 120 — Mk.2 : 60 / 120 / 240 — Mk.3 : 120 / 240 / 480 objets/min (×clock, plafonné par le tapis) |
| Pipelines Mk.1 / Mk.2 | 300 / 600 m³/min |
| Débit machine | `quantité_produite × 60 / durée_cycle_s` |
| Surcadençage — production | linéaire avec l'horloge (max 250 %, 3 Power Shards) |
| Surcadençage — puissance (prod.) | `base × (horloge/100) ^ 1.321928` |
| Surcadençage — générateurs | linéaire (exposant 1.0) |
| Répartiteur / groupeur | division/fusion équitable, ~2000/min interne → limité par le tapis |
| Somersloop | sortie ×1.25 → ×2.0 sans hausse d'entrée ; puissance jusqu'à ×4 ; full amp + 250 % ≈ ×13,431 puissance de base ; 106 disponibles |
| Wagon de fret | 32 emplacements (1600 m³ fluide) ; débit train = taille_pile × 32 × n_wagons / aller-retour |
| Drone | 9 emplacements ; aller-retour min ≈ 102 s (51 s décollage + 51 s atterrissage) ; 4 batteries/trajet + 1/km ; longue portée, faible débit |

---

## 11. Bases open source à réutiliser

- **`Zistack/Satisfactory-Optimizer`** (Python, `scipy.optimize.linprog`) — meilleure base pour le modèle de données et la formulation LP ; gère déjà l'exposant de puissance et l'allocation de Somersloops. Point de départ recommandé pour le cœur.
- **`chwthewke/satisfactory-tools`** (Scala) — référence de complétude : choix automatique des recettes, horloges, puissance, sous-produits, sources/destinations. À lire comme cahier des charges fonctionnel.
- **`Sankeyfactory`** (TypeScript) — référence pour la conversion `Docs.json` → format pratique et la représentation en graphe (Sankey).
- **`marci07iq/factory-calculator`** — a déjà des opérations de split de nœuds et de hubs de regroupement dans un graphe de flux ; utile pour la couche distribution.

Aucun de ces outils ne génère le réseau de répartiteurs/groupeurs avec gestion de capacité : c'est la valeur ajoutée du présent outil.

---

## 12. Feuille de route par phases

**Phase 0 — données. ✅ fait.** Parser `Docs.json` → cache normalisé. Charger constantes de jeu. Tests : débits de quelques recettes connues (lingot de fer 30/min, etc.).

**Phase 1 — cœur LP. ✅ fait.** Modèle + `solve_forward` (objectif min_raw, OR-Tools GLOP). Réalisation machines/horloge/puissance. CLI `forward`. Validation contre un calculateur existant.

**Phase 2 — modes avancés.** `solve_max_output` (mode inverse), objectifs min_power / min_machines, activation des recettes alternatives, sous-produits & boucles, Somersloop.

**Phase 3 — distributeur.** Arbre /2 /3, manifold, capacité & lignes parallèles, sélection de tier, export DOT/JSON. Branchement sur chaque étape du plan.

**Phase 4 — UI & polish.** Streamlit, Sankey, sauvegarde des plans, équilibreur à retour pour les *N* moches.

**Phase 5 — gisements & carte.** Intégrer `data/nodes.json`, débit max par gisement (pureté/tier/clock/sloop), gisements disponibles comme recettes d'extraction dans le solveur, onglet carte interactif (marqueurs cliquables, toggle dispo/occupé, persistance `nodes_state.json`).

**Phase 6 — recherche de clusters & localisation d'usine.** Module `siting/` : sources unifiées (gisement / sortie d'usine / entrée manuelle), pré-clustering, sélection sous capacité, médiane géométrique (Weiszfeld), rendu carte. Couplage LP décorrélé d'abord.

**Phase 7 — transport inter-sites.** Module `transport/` : profils et formules par mode, modèle de coût, recommandation par liaison, carte de décision. Consomme les liaisons de la Phase 6. Conception de réseau multi-gares en option ultérieure.

**Hors feuille de route (décidé) :** import de sauvegarde `.sav`. Remplacé par la gestion manuelle de la disponibilité des gisements (Phase 5).

---

## 13. Tests & validation

- **Unitaires données** : débits/min recalculés == valeurs wiki sur un échantillon.
- **Unitaires solveur** : cas à solution connue (ratios « propres ») ; cohérence du bilan net (∑ entrées = ∑ sorties + bruts).
- **Mode inverse** : vérifier que la sortie max ne dépasse jamais ce que les entrées permettent ; non-régression quand on ajoute une alternative (la sortie max ne doit jamais diminuer).
- **Distributeur** : pour tout *N* factorisable, somme des débits feuilles == débit source, et aucune arête > capacité après application des lignes parallèles ; pour *N* premier, repli manifold correct.
- **Gisements** : débit max recalculé par pureté/tier/clock == valeurs attendues ; un gisement marqué occupé n'apparaît jamais dans la solution ; plafond d'entrée d'une ressource == somme des débits des gisements disponibles.
- **Clusters & localisation** : sur sources synthétiques à optimum connu, la médiane géométrique converge vers le point attendu ; la sélection couvre la demande sans dépasser les capacités ; ajouter une entrée manuelle proche ne fait jamais augmenter le coût optimal.
- **Transport** : débit par mode recalculé == formules (train = pile×32×wagons/aller-retour, drone = 9×pile/aller-retour) ; le mode recommandé est bien celui de coût minimal parmi les modes faisables ; un fluide n'est jamais affecté à un tapis sans empaquetage.
- **Bout en bout** : un cas complet (ex. 10 Cadres modulaires/min) du plan jusqu'aux graphes de distribution, comparé à une construction manuelle.
