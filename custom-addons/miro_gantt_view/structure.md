# Structure du module `miro_gantt_view`

Module Odoo 17 qui ajoute un type de vue **"Miro Gantt"** — une vue interactive de type diagramme de Gantt pour la planification de tâches dans le backend Odoo.

> Ce document décrit l'arborescence réelle du module. Pour le détail des liaisons entre fichiers (qui importe quoi), voir `README.md` §3.

---

## Vue d'ensemble de l'architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CÔTÉ SERVEUR (Python)                                          │
│  ir_ui_view_inherit.py   ─── enregistre le type "miro_gantt"    │
│  ir_actions_inherit.py   ─── autorise "miro_gantt" dans les     │
│                              actions fenêtre                    │
└────────────────────────┬────────────────────────────────────────┘
                         │  Chargement des assets (web.assets_backend)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  CÔTÉ CLIENT (JavaScript / OWL)                                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  QUATUOR DE VUE (pattern Odoo 17)                        │   │
│  │  ArchParser → Model → Controller → Renderer              │   │
│  │  Enregistré via view_registry.js                         │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │  COMPOSANTS UI (6 dossiers)                              │   │
│  │  header | popover | sidebar | taskbar | dialogs |        
│  │  date_range                                              │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │  UTILITAIRES PURS (11 modules dans utils/)                │   │
│  │  drag_and_drop | position_compute | group_by | row |     
│  │  chart_row | config | grid | ...                         │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │  TEMPLATES QWeb (8 fichiers XML)                         │   │
│  │  controller | renderer | header | sidebar | popover |    │   │
│  │  dialogs | date_range | taskbar                          │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │  STYLES (1 fichier SCSS, ~1410 lignes)                   │   │
│  │  utils/scss/miro_gantt.scss                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arbre des fichiers

```
miro_gantt_view/
├── __init__.py                              # Point d'entrée Python → importe models/
├── __manifest__.py                          # Métadonnées du module (nom, version, assets)
├── README.md                                # Vue d'ensemble, graphe d'appels, maintenance
├── structure.md                             # Ce fichier
├── i18n/
│   └── fr.po                                # Traductions françaises (JS _t + modèles)
├── models/
│   ├── __init__.py                          # Importe les 2 extensions de modèles
│   ├── ir_ui_view_inherit.py                # Ajoute "miro_gantt" au champ `type` de ir.ui.view
│   └── ir_actions_inherit.py                # Ajoute "miro_gantt" au view_mode de ir.actions.act_window.view
├── tests/                                   # Tests Python (TransactionCase)
│   ├── __init__.py
│   └── test_ir_models.py                    # Vérifie les 2 fichiers ci-dessus + _is_qweb_based_view
└── static/
    ├── description/
    │   └── icon.png                         # Icône du module dans Odoo Apps
    ├── src/
    │   ├── arch_parser.js                   # GanttArchParser — parse le XML <miro_gantt>
    │   ├── view_registry.js                 # Assemble le quatuor et l'enregistre dans le registry Odoo
    │   ├── components/
    │   │   ├── header/
    │   │   │   ├── header.js                # Données d'en-tête (colonnes majeures/mineures) + tri
    │   │   │   └── header.xml               # Templates Header, HeaderSidebar
    │   │   ├── popover/
    │   │   │   ├── popover.js               # Composant OWL du popover de détail (Éditer/Supprimer)
    │   │   │   ├── popover.xml              # Templates Popover, ChartPopover
    │   │   │   ├── popover_template.js      # Mini moteur de template custom (t-esc/t-if/t-raw)
    │   │   │   └── chart_popover.js         # Popover de la ligne de totaux (tâches par colonne)
    │   │   ├── dialogs/
    │   │   │   ├── drag_confirm_dialog.js   # Confirmation drag/resize (dates éditables) avant écriture
    │   │   │   └── drag_confirm_dialog.xml  # Template DragConfirmDialog
    │   │   ├── date_range/
    │   │   │   ├── date_range_input.js      # Champs date début→fin liés (DateTimePicker range)
    │   │   │   └── date_range_input.xml     # Template DateRangeInput
    │   │   ├── sidebar/
    │   │   │   ├── sidebar.js               # Barre latérale gauche sticky (noms, avatars, "+") + redim.
    │   │   │   └── sidebar.xml              # Templates HeaderSidebar, SidebarBody
    │   │   └── taskbar/
    │   │       ├── taskbar.js               # Point d'entrée du rendu DOM du Gantt (renderGantt, onBarClick)
    │   │       ├── taskbar.xml              # Templates DateGrid, GroupRow, TaskBandPill
    │   │       ├── taskbar_rendering.js     # Rendu des lignes sidebar/colonnes/bandes (pills)
    │   │       └── taskbar_visibility.js    # Masque les lignes hors viewport (optimisation scroll)
    │   ├── controller/
    │   │   ├── controller.js                # Layout + SearchBar + pager + dialogs création/édition
    │   │   └── controller.xml               # Template Gantt.Controller
    │   ├── model/
    │   │   ├── model.js                     # Classe GanttModel : setup/load/notify
    │   │   ├── records.js                   # RPC search_read, mapping, résolution M2M/couleurs/avatars, CRUD
    │   │   └── groups.js                    # Groupement, tri, ordre de session, contexte de création
    │   ├── renderer/
    │   │   ├── renderer.js                  # Composant OWL racine (~718 lignes), orchestre le rendu
    │   │   ├── renderer.xml                 # Template Gantt.Renderer (toolbar, scroll, ligne de totaux)
    │   │   ├── renderer_dom.js              # Feedback flottant, highlight, lookup de bande
    │   │   ├── renderer_drag.js             # startDrag/onDrag, dateFromColIndex, appelle onBarClick
    │   │   ├── renderer_drop_indicator.js   # Indicateur bleu de dépôt pendant le drag
    │   │   ├── renderer_layout.js           # computeFullLayout : lignes + lignes vides (sans données)
    │   │   ├── renderer_navigation.js       # Dropdown de périodes, formatage date, scroll/zoom
    │   │   └── renderer_utils.js            # Expressions readonly, largeur colonne, signature cache
    │   └── utils/                           # Logique pure, indépendante d'OWL
    │       ├── scss/
    │       │   └── miro_gantt.scss          # Thème complet (~1410 lignes)
    │       ├── autoscroll.js                # Défilement auto près des bords pendant un drag
    │       ├── chart_row.js                 # Ligne de totaux : comptage par colonne + graphique barres
    │       ├── config.js                    # Constantes : ROW_HEIGHT, ZOOM_CONFIG, SIDEBAR_*, couleurs...
    │       ├── dates.js                     # hasTime / parseDate (datetime UTC ou date seule)
    │       ├── drag_and_drop.js             # Moteur complet du drag & drop + ouverture DragConfirmDialog
    │       ├── error_message.js             # Extraction d'un message lisible depuis une erreur RPC
    │       ├── ghost.js                     # Élément "fantôme" + badges de dates pendant le drag
    │       ├── grid.js                      # Rendu de la grille de fond (colonnes de dates, ligne "today")
    │       ├── group_by.js                  # groupRecords, computeRowLayout, flattenGroups
    │       ├── position_compute.js          # Maths date ↔ pixel (aucune dépendance interne)
    │       └── row.js                       # buildTaskRowData, attachTaskRowEvents (drag/click/resize)

```
*(L'ancienne suite JS `static/tests/` a été retirée ; voir § Tests ci-dessous.)*

---

## Fichiers Python

### `__manifest__.py`

Déclare le module Odoo :

- **Nom** : "Miro Gantt View"
- **Version** : `17.0.1.0.0`
- **Licence** : Other proprietary
- **Dépendance unique** : `web`
- **Assets** : charge tous les fichiers JS/XML dans `web.assets_backend` (inclut `web/static/lib/Chart/Chart.js` v4 pour la ligne de totaux), le SCSS via `utils/**/*.scss` ; la section `web.qunit_suite_tests` est commentée

### `models/ir_ui_view_inherit.py`

Étend `ir.ui.view` pour ajouter `"miro_gantt"` au champ `type` (sélection). Override `_is_qweb_based_view` pour que le type soit traité comme QWeb — c'est ce qui permet à Odoo de charger et rendre le composant OWL côté client.

### `models/ir_actions_inherit.py`

Étend `ir.actions.act_window.view` pour ajouter `("miro_gantt", "Miro Gantt")` au champ `view_mode` (sélection, cascade). Permet aux actions fenêtre de référencer des vues miro_gantt.

### `tests/test_ir_models.py`

`TransactionCase` taggé `post_install` qui vérifie que les deux fichiers ci-dessus font bien leur travail (présence de `"miro_gantt"` dans les deux sélections, comportement de `_is_qweb_based_view` pour `miro_gantt` et pour `form`).

---

## Le quatuor de vue (côté client)

Le pattern standard Odoo 17 pour un type de vue personnalisé :

### 1. `arch_parser.js` — Analyseur d'architecture (310 lignes)

Parse le nœud XML `<miro_gantt>` dans l'arch de la vue. Extrait et valide les attributs de configuration :

- `date_start`, `date_end` (champs obligatoires)
- `colored_by` (coloration par champ)
- `default_group_by`, `default_filter`, `available_filters` (zooms autorisés)
- `zoom` (niveau de zoom par défaut), `default_title`, `sidebar_label_field`, `taskbar_label_field`
- `sidebar_column_fields` (colonnes dynamiques affichables dans la sidebar, remplaçant les colonnes fixes start/end/status/duration/progress)
- Attributs de comportement (`editable`, etc.)

### 2. `model/model.js` — Modèle de données (216 lignes)

Étend `Model` d'Odoo (`export class GanttModel extends Model`). Classe wrapper déléguant aux sous-modules :

- **`model/records.js`** — Chargement RPC (`search_read`), parsing dates/couleurs/noms, résolution dotted paths, M2M, avatars, CRUD (`deleteTaskBar`, `openFormView`)
- **`model/groups.js`** — Groupement, tri, ordre de session, contexte de création par groupe
- **`model/model.js`** — Classe avec `setup()`, `load()`, et wrappers fins vers les deux modules ci-dessus

### 3. `controller/controller.js` — Contrôleur (214 lignes)

Composant OWL qui gère :

- Le `Layout` (barre supérieure, breadcrumb)
- La `SearchBar` (filtres et groupements)
- Le `usePager` (pagination)
- Les actions de suppression avec confirmation
- Le routage URL (synchronisation du zoom/position avec l'URL)

### 4. `renderer/renderer.js` — Rendu principal (718 lignes)

Composant OWL déléguant aux sous-modules extraits :

- **`renderer_utils.js`** — Readonly eval, calcul colonne, init focus, cleanup
- **`renderer_drop_indicator.js`** — Indicateur bleu, highlight cellule, queries DOM groupes
- **`renderer_drag.js`** — Drag-and-drop, sélection cellules, contexte création
- **`renderer_dom.js`** — Feedback label, highlight records, lookup bandes
- **`renderer_layout.js`** — Layout lignes, insertions cell-create, signature inputs
- **`renderer_navigation.js`** — Options période, formatage date, zoom/scroll
- **`utils/chart_row.js`** — Ligne de totaux globale (graphique barres + popover des tâches par colonne)
- **`renderer.js`** — Classe avec `setup()`, délègue le rendu DOM réel à `components/taskbar/taskbar.js` (`renderGantt`), inclut `DateRangeInput`/`DateTimeInput`/`Dropdown` dans la toolbar, et ouvre le popover de totaux via `usePopover` (`ChartPopover`).

---

## Composants UI (`components/`)

| Dossier        | Fichier                         | Rôle                                                                                                                                        |
| -------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `header/`      | `header.js` (134 l.)            | Construit les données d'en-tête (colonnes majeures/mineures) et attache les événements de tri                                               |
| `popover/`     | `popover.js` (158 l.)           | Composant OWL du popover de détail (clic sur une pill) : boutons Éditer/Supprimer, wrapper `toFormat`                                       |
| `popover/`     | `popover_template.js` (325 l.)  | Petit moteur de template XML pour le corps du popover personnalisé (`t-esc`, `t-if`, `t-raw`)                                               |
| `popover/`     | `chart_popover.js` (112 l.)     | Popover de la ligne de totaux : liste lecture seule des tâches couvrant une colonne, groupées comme la sidebar (repliable + compteurs)     |
| `dialogs/`     | `drag_confirm_dialog.js` (167 l.)| Confirmation du drag/resize avant écriture ORM : `DateTimeInput` (dd/MM/yyyy HH:mm), modes move/resize/resize-start, réparsing du texte saisi |
| `date_range/`  | `date_range_input.js` (38 l.)   | Champs début→fin liés (DateTimePicker `range` d'Odoo) utilisés dans la toolbar                                                              |
| `sidebar/`     | `sidebar.js` (329 l.)           | Barre latérale gauche sticky : noms d'enregistrements/groupes, avatars, bouton "+", redimensionnement (poignée `o_gantt_view_sidebar_resize`) |
| `taskbar/`     | `taskbar.js` (260 l.)           | **Point d'entrée du rendu DOM du Gantt** : `renderGantt`, `onBarClick`, poignée de redimensionnement sidebar, câble `records.js` et `popover.js` |
| `taskbar/`     | `taskbar_rendering.js` (170 l.) | Rendu des lignes sidebar, colonnes Gantt et bandes (pills)                                                                                 |
| `taskbar/`     | `taskbar_visibility.js` (96 l.) | Optimisation scroll : masque les lignes hors du viewport visible                                                                           |

---

## Modules utilitaires (`utils/`)

| Fichier               | Lignes | Rôle                                                                                                                                |
| --------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `config.js`           | 322    | Constantes centrales : `ROW_HEIGHT`, `BAR_HEIGHT`, `LANE_*`, `NAME_PANEL_WIDTH`, `SIDEBAR_*`, `ZOOM_CONFIG`, `COLOR_PALETTE`, `TOTALS_BAR_COLOR_*`, helpers avatars/layout |
| `position_compute.js` | 345    | Maths date→pixel : colonnes, positionnement des barres, intervalles de déplacement, limites de la grille. Aucune dépendance interne |
| `grid.js`             | 71     | Rendu de la grille de fond : `renderDateColumns`, `buildColumnData` (surlignage aujourd'hui/jours off)                              |
| `row.js`              | 200    | `buildTaskRowData`, `attachTaskRowEvents` (drag/click/resize d'une pill), `buildGroupRowData`                                       |
| `group_by.js`         | 530    | Logique de groupement : normalisation des valeurs, arbre de groupes, aplatissement, tri, `assignPillLevels`                         |
| `drag_and_drop.js`    | 508    | Moteur complet du drag & drop : déplacement/copie, cross-group, écriture ORM, ouverture `DragConfirmDialog`, rollback visuel          |
| `chart_row.js`        | 357    | Ligne de totaux globale : `computeGlobalColumnTotals`, `buildPopoverGroupTree`, `renderTotalsRow` (graphique Chart.js barres)        |
| `dates.js`            | 48     | `hasTime` / `parseDate` : normalisation datetime UTC ou date seule à minuit locale, invalide → epoch                                 |
| `ghost.js`            | 192    | Élément "fantôme" semi-transparent + badges de dates pendant un drag/resize                                                         |
| `autoscroll.js`       | 88     | Défilement automatique du conteneur quand on traîne près des bords supérieur/inférieur                                              |
| `error_message.js`    | 43     | Extrait un message utilisateur lisible depuis une erreur RPC Odoo                                                                   |

> Le positionnement du popover est 100% natif (`@web/core/popover`) : l'heure de l'heuristique
> custom (`getBestPopoverPosition`) est révolue. La position (`right`) et l'habillage
> (`popoverClass 'o_cw_popover'`, style calendrier) sont portés par `renderer._popoverOptions`
> dans `renderer/renderer.js`.

---

## Templates QWeb

| Fichier                                      | Templates                         | Utilisé par                                    |
| -------------------------------------------- | --------------------------------- | ---------------------------------------------- |
| `controller/controller.xml`                  | `Gantt.Controller`                | `controller.js`                                |
| `renderer/renderer.xml`                      | `Gantt.Renderer` (toolbar, ligne de totaux) | `renderer.js`                     |
| `components/header/header.xml`               | `Header`, `HeaderSidebar`         | `header.js`, `sidebar.js`                      |
| `components/sidebar/sidebar.xml`             | `SidebarBody`                     | `sidebar.js`                                   |
| `components/taskbar/taskbar.xml`             | `DateGrid`, `GroupRow`, `TaskBandPill` | `taskbar.js`, `taskbar_rendering.js`       |
| `components/popover/popover.xml`             | `Popover`, `ChartPopover`         | `popover.js`, `chart_popover.js`               |
| `components/dialogs/drag_confirm_dialog.xml` | `DragConfirmDialog`               | `drag_confirm_dialog.js`                       |
| `components/date_range/date_range_input.xml` | `DateRangeInput`                  | `date_range_input.js`                          |

---

## Flow de chargement

```
1. Odoo lit __manifest__.py
   │
2. Charge les assets (JS, XML, SCSS) dans web.assets_backend
   │
3. view_registry.js enregistre le type "miro_gantt"
   │  dans le registry des vues Odoo (ArchParser, Model, Controller, Renderer)
   │
4. Quand une action act_window référence view_mode="miro_gantt" :
   │
   ├─→ arch_parser.js          ─── analyse le <miro_gantt> XML
   ├─→ model/model.js          ─── fetch les données via RPC (search_read)
   ├─→ controller/controller.js ─── assemble Layout + SearchBar + Renderer
   └─→ renderer/renderer.js    ─── rend la grille Gantt interactive
        │
└─▶ components/taskbar/taskbar.js (renderGantt) ─── rendu DOM impératif
                ├─ header.js       ─── en-tête avec colonnes temps
                ├─ taskbar_rendering.js ─── grille de fond + barres
                ├─ sidebar.js      ─── noms des enregistrements + redimensionnement
                ├─ utils/chart_row.js ─── ligne de totaux (barres) + popover récap
                └─ utils/drag_and_drop.js ─── glisser-déplacer → dialogs/drag_confirm_dialog.js
```

---

## SCSS

`utils/scss/miro_gantt.scss` (~1410 lignes) contient l'intégralité du thème :

- Variables et mixins (couleurs, bordures, z-index)
- Styles des barres de tâches (`.o_gantt_view_pill`) avec couleurs dynamiques
- Grille CSS (colonnes temps + lignes enregistrements)
- Barre latérale sticky + poignée de redimensionnement (`.o_gantt_view_sidebar_resize`, z-index géré)
- Ligne de totaux (`.o_gantt_view_totals_row`, `.o_gantt_view_totals_row_scroll`)
- Popover et tooltips
- États de drag (fantôme, copie)
- Ligne "aujourd'hui" et surlignage des jours off
- Responsive (scroll horizontal sur petits écrans)

---

## Tests

| Emplacement                       | Type                                           | Détail                                                                                                                                                                                                                                                                                  |
| --------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_ir_models.py`         | Python (`TransactionCase`, tag `post_install`) | Vérifie l'ajout de `"miro_gantt"` aux sélections `view_mode`/`type` et le comportement de `_is_qweb_based_view`                                                                                                                                                                         |

> La suite JS QUnit (`static/tests/*.js`, `web.qunit_suite_tests`) a été **retirée** ; la section correspondante
> est commentée dans `__manifest__.py`. Seuls les tests Python restent actifs.

Voir `README.md` §6 pour la commande de lancement et la marche à suivre pour ajouter un test.
