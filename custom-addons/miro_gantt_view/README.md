# Miro Gantt View

Module Odoo 17 — vue Gantt interactive (drag-and-drop, redimensionnement, groupement, zoom multi-niveaux), construite avec OWL.

**Auteur :** A. M. Herijaona
**Version :** `17.0.1.0.0` · **Licence :** Other proprietary · **Dépendance :** `web`

## Fonctionnalités

- Timeline Gantt interactive avec rendu DOM impératif optimisé (pas de vdom OWL pour les lignes/pills, cf. §3c).
- Drag-and-drop pour déplacer/redimensionner les tâches, avec auto-scroll et rollback visuel en cas d'échec RPC.
- Zoom multi-niveaux : Jour, Semaine, Mois, Année (`ZOOM_CONFIG` dans `config.js`).
- Groupement configurable (`default_group_by`), avec persistance de l'ordre des groupes en session.
- Coloration personnalisée des barres (`colored_by`) et visualisation de la progression.
- Popover de détail au clic sur une tâche, rendu **100% natif core/popover** (style calendrier `o_cw_popover`) avec header (ribbon + titre), corps personnalisable et footer (Éditer / Supprimer).
- Architecture extensible pour des modules métier tiers (héritage des composants OWL et des fonctions utilitaires).

## Installation

1. Copier `miro_gantt_view/` dans un répertoire d'addons Odoo 17.
2. Redémarrer le serveur puis activer le mode développeur.
3. Installer le module depuis **Apps** (aucune dépendance hors `web`).
4. Déclarer une vue avec `<miro_gantt date_start="..." date_end="..." .../>` et `view_mode="miro_gantt"` sur l'action fenêtre correspondante.

---

## 1. Vue d'ensemble de l'architecture

```
view_registry.js                 ← Point d'entrée : enregistre "miro_gantt" dans le registry Odoo
   │
   ├── arch_parser.js             ← Parse le XML <miro_gantt> → config (dates, groupes, couleurs, popover...)
   ├── controller/controller.js   ← Search bar, pager, dialogs de création/édition
   ├── model/model.js             ← Chargement des données, groupes, CRUD
   └── renderer/renderer.js       ← Composant OWL racine du rendu, orchestre tout le reste
```

Le module suit strictement le pattern MVC d'Odoo (**ArchParser → Model → Controller → Renderer**), avec la logique déportée dans des fonctions utilitaires pures autant que possible (`utils/`), pour rester testable indépendamment d'OWL.

---

## 2. Détail par dossier

### `static/src/` — racine

| Fichier            | Rôle                                                                                                                                                |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `view_registry.js` | Enregistre le type de vue `miro_gantt`. Assemble `GanttArchParser`, `GanttModel`, `GanttController`, `GanttRenderer` et les passe au registry Odoo. |
| `arch_parser.js`   | Parse le XML de l'arch (`<miro_gantt>`) : dates de début/fin, champ de groupement, couleurs, droits (create/edit/delete), template du popover.      |

### `controller/`

| Fichier         | Rôle                                                                                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `controller.js` | Composant OWL. Affiche `Layout` (search bar Odoo), le pager, et ouvre `FormViewDialog` / `ConfirmationDialog` pour créer, éditer, supprimer un enregistrement. |

### `model/`

| Fichier      | Rôle                                                                                                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `model.js`   | Classe `GanttModel` (étend le `Model` d'Odoo). Orchestre `load()` : fetch → map → résolution → tri → groupes → notify. Protège contre les races via un compteur `_loadVersion`. |
| `records.js` | Fonctions pures : `fetchRecords` (RPC `search_read`), `mapRecord`, `resolveRelatedColors`, `resolveM2MNames`, `resolveAvatarModels`, `deleteTaskBar`, `openFormView`.           |
| `groups.js`  | Fonctions pures : `buildGroups`, `toggleGroup`, `sortRecords`, `persistGroupOrder`, `buildGroupContext`.                                                                        |

### `renderer/`

| Fichier                      | Rôle                                                                                                                                                                                                     |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `renderer.js`                | Composant OWL racine du rendu. Gère l'état (zoom, sidebar, scroll, option affichage ligne de totaux), câble les hooks OWL (`useEffect`, `onWillUnmount`), synchro du scroll de la ligne de totaux, et **délègue** le rendu DOM réel à `taskbar.js`, le drag à `drag_and_drop.js` et la ligne de totaux à `chart_row.js`. |
| `renderer_utils.js`          | Fonctions pures : expressions readonly, largeur de colonne, signature des inputs (cache de rendu).                                                                                                       |
| `renderer_dom.js`            | DOM impératif : feedback flottant pendant le drag, highlight d'un enregistrement, lookup de bande.                                                                                                       |
| `renderer_layout.js`         | `computeFullLayout` : calcule les lignes (y compris lignes vides pour le drag-to-create) en s'appuyant sur `computeRowLayout` (`group_by.js`).                                                           |
| `renderer_navigation.js`     | Dropdown de périodes, formatage de la date focus, scroll, zoom, filtres.                                                                                                                                 |
| `renderer_drag.js`           | `startDrag`, `onDrag`, `startCellSelection`, `onBarClick` — orchestre le drag au niveau composant, appelle `onBarClick` défini dans `taskbar.js`.                                                        |
| `renderer_drop_indicator.js` | Indicateur bleu affiché pendant le drag ; utilise `getTargetGroupKey` (`drag_and_drop.js`) et `getDateGridBounds` (`position_compute.js`).                                                               |

### `components/` — composants UI

| Fichier                         | Rôle                                                                                                                                                                                                                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `header/header.js`              | En-tête des colonnes (mois/années), utilise `NAME_PANEL_WIDTH` (`config.js`).                                                                                                                                                                                     |
| `sidebar/sidebar.js`            | Barre latérale gauche (noms, avatars, dates, bouton "+", redimensionnement par poignée). Appelle `buildHeaderData`/`attachHeaderEvents` de `header.js`, `buildSidebarBodyData` (`sidebar.js`).                                                                   |
| `taskbar/taskbar.js`            | **Point d'entrée du rendu DOM du Gantt.** Appelle `renderColumnHeader` (`header.js`), `renderRowHeaders`/`renderGanttColumns` (`taskbar_rendering.js`), `attachHorizontalRowVisibility` (`taskbar_visibility.js`), `deleteTaskBar`/`openFormView` (`records.js`). |
| `taskbar/taskbar_rendering.js`  | Rendu des lignes sidebar, des colonnes Gantt, des bandes (pills). Appelle `isDragTarget` (`drag_and_drop.js`), `ROW_HEIGHT` (`config.js`).                                                                                                                        |
| `taskbar/taskbar_visibility.js` | Optimisation scroll : masque les lignes hors du viewport visible + alignement du header sur le scroll horizontal.                                                                                                                                                 |
| `popover/popover.js`            | Composant OWL du popover de détail (clic sur une pill), rendu dans le wrapper **natif core/popover** (`.o_popover popover` bootstrap) : boutons Éditer/Supprimer, rendu de template custom via `popover_template.js`.                                             |
| `popover/popover_template.js`   | Moteur de template XML du corps du popover custom (`t-esc`, `t-if`, `t-raw`, expressions) et corps par défaut (`renderDefaultBody`).                                                                                                                              |
| `popover/chart_popover.js`      | Composant OWL du popover de la ligne de totaux (clic sur une colonne du graphique) : liste lecture seule des tâches couvrant cette colonne, groupées comme la sidebar (groupes repliables + compteurs), scroll interne. Rendu dans `o_cw_popover`.                  |
| `dialogs/drag_confirm_dialog.js`| Boîte de dialogue de confirmation du drag/resize (OWL `Dialog` + `DateTimeInput` dd/MM/yyyy HH:mm) : modes `move`/`resize`/`resize-start`, saisie de la nouvelle plage avant écriture ORM, réparsing du texte saisi comme source de vérité.                          |
| `date_range/date_range_input.js`| Deux champs date liés (début → fin) basés sur le `DateTimePicker` range d'Odoo : le choix d'un côté bascule automatiquement l'open picker sur l'autre côté, valeur `[start, end]`.                                                                               |

### `utils/` — logique pure, indépendante d'OWL

| Fichier               | Rôle                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.js`           | Constantes (`ROW_HEIGHT`, `BAR_HEIGHT`, `COLOR_PALETTE`, `ZOOM_CONFIG`, `NAME_PANEL_WIDTH`, largeur/min sidebar, couleurs du graphique de totaux `TOTALS_BAR_COLOR_*`...) et petits helpers (initiales avatar, `computeBandHeight`, `sidebarColsCss`). |
| `position_compute.js` | Maths date ↔ pixel : `getDateColIndex`, position/largeur d'une barre, `getDateGridBounds`, `getDragInterval`. Aucune dépendance interne — pur calcul.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `grid.js`             | `renderDateColumns`, `buildColumnData` (colonnes de la grille de dates). Utilise `getDateColIndex` (`position_compute.js`) et les constantes de `config.js`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `row.js`              | `buildTaskRowData`, `attachTaskRowEvents` (drag/click/resize d'une pill), `buildGroupRowData`. Utilise `getDateGridBounds` (`position_compute.js`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `chart_row.js`        | Ligne de totaux globaux : `computeGlobalColumnTotals` (compte par colonne visible sur toutes les tâches chargées), `buildPopoverGroupTree` (arbre de groupes pour le popover) et `renderTotalsRow` (graphique Chart.js type **bar** — une barre par colonne alignée sur `_columnWidthPx`, couleurs selon le zoom, marqueur pointillé sur la colonne du jour, clic sur une colonne = popover `ChartPopover` des tâches ; Chart.js v4 fourni via `web/static/lib/Chart/Chart.js` dans `web.assets_backend`, globale `Chart`, instance gardée sur `renderer._totalsChart` et détruite dans `cleanupRenderer`). La ligne n'a **pas** de barre de défilement propre : son contenu suit le scroll horizontal du corps (`scrollLeft` synchro dans le handler `scroll` de `renderer.js`). Le libellé côté sidebar (`renderer.js`, getter `_titleTotalsRowLabel`) affiche `Total <default_title> on <plage visible> : nb` — `nb` = nombre de taskbars réellement affichés (somme des `records` des bands de `_rowLayout`, plage visible + groupes repliés pris en compte). Utilise `getDateGridBounds` (`position_compute.js`), `formatFocusDate` (`renderer_navigation.js`) et `_t` (`@web/core/l10n/translation`). |
| `group_by.js`         | `groupRecords`, `computeRowLayout`, `flattenGroups`, `assignPillLevels`, `getRecordGroupKey`. Utilise `computeBandHeight` (`config.js`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `drag_and_drop.js`    | Moteur complet du drag & drop : déplacement/copie, cross-group, écriture ORM, undo, rollback visuel en cas d'échec. Ouvre `DragConfirmDialog` (`dialogs/`) pour valider la nouvelle plage avant écriture. Utilise `getRecordGroupKey` (`group_by.js`), `getDragInterval` (`position_compute.js`), `checkAutoScroll`/`stopAutoScroll` (`autoscroll.js`), helpers de `ghost.js`, `extractErrorMessage` (`error_message.js`). |
| `autoscroll.js`       | Défilement automatique pendant un drag proche des bords de la grille.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `ghost.js`            | Élément "fantôme" semi-transparent + badge de dates pendant un drag/resize.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `error_message.js`    | Extraction d'un message lisible depuis une erreur RPC Odoo.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `dates.js`            | Helpers date partagés : `hasTime` (une chaîne brute porte une heure ?) et `parseDate` (datetime UTC / date seule à minuit locale, invalide → epoch). Utilisés par `model/records.js` et le wrapper `toFormat` du popover (`popover/popover.js`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

---

## 3. Qui appelle qui — liaisons réelles entre fichiers

> Extrait directement des `import` du code (et non déduit) — c'est le graphe d'appel réel du module.

### a) Démarrage / assemblage de la vue

```
view_registry.js
   ├──▶ renderer/renderer.js            (GanttRenderer)
   ├──▶ arch_parser.js                  (GanttArchParser)
   ├──▶ controller/controller.js        (GanttController)
   └──▶ model/model.js                  (GanttModel)
```

### b) Chargement des données

```
model/model.js
   └──▶ model/records.js   (fetchRecords, mapRecord, resolveRelatedColors,
   |                         resolveM2MNames, resolveAvatarModels)
   └──▶ model/groups.js    (buildGroups, sortRecords, ...)
   └──▶ utils/config.js    (ZOOM_CONFIG)
```

### c) Rendu principal — **Renderer → Taskbar → sous-modules**

C'est le cœur de la question posée : **`taskbar.js` n'est pas appelé "dans" `renderer.js` au sens composant, il est _importé et invoqué comme fonction_ par `renderer.js`.**

```
renderer/renderer.js
   │
   ├──▶ components/taskbar/taskbar.js     import { renderGantt as _renderGantt }
   │        │                              → renderer.js appelle _renderGantt() à chaque rendu
   │        │
   │        ├──▶ components/header/header.js           (renderColumnHeader)
   │        ├──▶ components/taskbar/taskbar_rendering.js (renderRowHeaders, renderGanttColumns)
   │        │        └──▶ utils/drag_and_drop.js         (isDragTarget)
   │        │        └──▶ utils/config.js                (ROW_HEIGHT)
│        ├──▶ components/taskbar/taskbar_visibility.js (attachHorizontalRowVisibility)
    │        ├──▶ model/records.js                        (deleteTaskBar, openFormView)
   │
   ├──▶ utils/drag_and_drop.js             (onDrag, stopDrag)
   │        └──▶ components/dialogs/drag_confirm_dialog.js (DragConfirmDialog, avant écriture ORM)
   ├──▶ components/popover/popover.js        (GanttViewPopover)
   ├──▶ components/date_range/date_range_input.js (champ range toolbar, renderer.xml)
   ├──▶ utils/chart_row.js                  (renderTotalsRow → ligne de totaux)
   │        └──▶ components/popover/chart_popover.js (popover au clic sur une colonne)
   ├──▶ renderer/renderer_layout.js        (computeFullLayout)
   ├──▶ renderer/renderer_navigation.js    (navigation périodes/zoom)
   ├──▶ renderer/renderer_utils.js         (expressions, largeur colonne)
   └──▶ renderer/renderer_dom.js           (feedback, highlight)
```

**En résumé, pour répondre précisément à "Taskbar est appelé dans Renderer" :**
`renderer.js` fait `import { renderGantt as _renderGantt } from ".../taskbar/taskbar"` puis appelle `_renderGantt(...)` directement dans sa logique de rendu (pas via un `<Component/>` OWL classique, mais comme une fonction de rendu DOM impératif). C'est `taskbar.js` qui, à son tour, orchestre `header.js`, `taskbar_rendering.js`, `taskbar_visibility.js`, `records.js` et `popover.js`.

### d) Cycle de drag-and-drop

```
renderer/renderer_drag.js
   ├──▶ components/taskbar/taskbar.js      (onBarClick as _onBarClickUtil)
   └──▶ utils/ghost.js, utils/autoscroll.js, utils/drag_and_drop.js (indirect via renderer.js)

utils/drag_and_drop.js   (startDrag / onDrag / stopDrag — moteur complet)
   ├──▶ utils/group_by.js          (getRecordGroupKey)
   ├──▶ utils/position_compute.js  (getDragInterval)
   ├──▶ utils/autoscroll.js        (checkAutoScroll, stopAutoScroll)
   ├──▶ utils/ghost.js             (_formatDragDateRange, _formatDayCount)
   ├──▶ utils/error_message.js     (extractErrorMessage)
   └──▶ model (ORM write/copy)     → puis notify() vers renderer.js

renderer/renderer_drop_indicator.js
   ├──▶ utils/drag_and_drop.js      (getTargetGroupKey)
   └──▶ utils/position_compute.js   (getDateGridBounds)
```

### e) Clic sur une pill (popover de détail)

Le popover de détail utilise **strictement le core/popover natif** (`@web/core/popover`,
wrapper bootstrap `.o_popover popover`, flèche + animation natives) avec un
**habillage style calendrier** : `popoverClass 'o_cw_popover'` (largeur 448px,
card-header/card-footer, close `fc-close`), position `right` comme
`useCalendarPopover`. Le header affiche le statut (ribbon) + le titre du record.
Seule la classe `o_cw_popover` conserve les ajustements de corps (ellipsis,
scroll, close button).

```
components/taskbar/taskbar.js  → onBarClick()
   ├──▶ renderer/renderer.js   (_popoverOptions : popoverClass o_cw_popover, position 'right')
   └──▶ @web/core/popover/popover_hook.js   (usePopover → PopoverController → Popover)
            └──▶ components/popover/popover.js   (GanttViewPopover.open — composant OWL)
                     └──▶ components/popover/popover_template.js  (rendu du template custom, t-esc/t-raw)
```

### f) Dépendances "feuilles" (aucune dépendance interne)

Ces fichiers sont des utilitaires purs, sans import d'autres fichiers du module — les plus faciles à tester unitairement :

- `utils/position_compute.js`
- `utils/autoscroll.js`
- `utils/error_message.js`

---

## 4. Templates QWeb

| Fichier XML                      | Templates                                           | Utilisé par                          |
| -------------------------------- | --------------------------------------------------- | ------------------------------------ |
| `controller/controller.xml`      | `Gantt.Controller`                                  | `controller.js`                      |
| `renderer/renderer.xml`          | `Gantt.Renderer` (toolbar, scroll, ligne de totaux) | `renderer.js`                        |
| `components/header/header.xml`   | `Header`, `HeaderSidebar`                           | `header.js`, `sidebar.js`            |
| `components/sidebar/sidebar.xml` | `SidebarBody` (bandes/groupes/lignes vides)         | `sidebar.js`                         |
| `components/taskbar/taskbar.xml` | `DateGrid`, `GroupRow`, `TaskBandPill`              | `taskbar.js`, `taskbar_rendering.js` |
| `components/popover/popover.xml` | `Popover`, `ChartPopover`                           | `popover.js`, `chart_popover.js`     |
| `components/dialogs/drag_confirm_dialog.xml` | `DragConfirmDialog`                     | `drag_confirm_dialog.js`             |
| `components/date_range/date_range_input.xml` | `DateRangeInput`                         | `date_range_input.js`                |

---

## 5. Python (backend)

Le code Python est minimal : toute la logique métier est côté JS. Ces fichiers ne font qu'**enregistrer le type de vue** `miro_gantt` auprès d'Odoo.

| Fichier                        | Rôle                                                                                    |
| ------------------------------ | --------------------------------------------------------------------------------------- |
| `__manifest__.py`              | Métadonnées du module (nom, version `17.0.1.0.0`, dépendances, assets JS/XML/SCSS). Inclut Chart.js v4 (`web/static/lib/Chart/Chart.js`) dans `web.assets_backend`. |
| `__init__.py`                  | Importe `models`.                                                                       |
| `models/__init__.py`           | Importe les 2 fichiers d'héritage.                                                      |
| `models/ir_actions_inherit.py` | Ajoute `"miro_gantt"` au champ `view_mode` de `ir.actions.act_window`.                  |
| `models/ir_ui_view_inherit.py` | Ajoute `"miro_gantt"` au champ `type` de `ir.ui.view` + override `_is_qweb_based_view`. |

```
ir_actions_inherit.py                ir_ui_view_inherit.py
       │                                     │
       ▼                                     ▼
  view_mode += "miro_gantt"            type += "miro_gantt"
       │                                     │
       ▼                                     ▼
  Odoo autorise les actions            Odoo sait charger et rendre
  fenêtre avec cette vue               les vues de type miro_gantt (QWeb)
```

**Sans ces deux fichiers**, Odoo ne reconnaît pas `miro_gantt` comme type de vue valide et refuse de charger le module.

---

## 6. Maintenance

### Ajouter une fonction utilitaire

1. Créer/modifier un fichier dans `static/src/utils/`.
2. Exporter la fonction : `export function maFonction(...) { ... }`.
3. L'importer où nécessaire : `import { maFonction } from "@miro_gantt_view/utils/mon_fichier"`.

### Ajouter un composant UI

1. Créer un dossier dans `static/src/components/`.
2. Ajouter un fichier `.js` (classe OWL ou fonctions standalone).
3. Ajouter un fichier `.xml` (templates QWeb) et l'enregistrer dans les assets (`__manifest__.py`).

### Analyser le code

```bash
node analyze_code.mjs                               # tous les fichiers
node analyze_code.mjs ./static/src/utils/config.js  # un fichier
node analyze_code.mjs ./static/src/                 # un dossier
```

### Tests existants

| Emplacement               | Type                                           | Couverture                                                                                                                                                                                                                             |
| ------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_ir_models.py` | Python (`TransactionCase`, tag `post_install`) | Vérifie que `"miro_gantt"` est bien ajouté aux sélections `view_mode` (`ir.actions.act_window.view`) et `type` (`ir.ui.view`), et que `_is_qweb_based_view` renvoie `True` pour `miro_gantt` sans casser le comportement des autres types (`form`). |

> Le dossier `static/tests/` (ancienne suite QUnit JS) a été retiré. La section
> `web.qunit_suite_tests` de `__manifest__.py` est commentée. Seuls les tests
> Python ci-dessus sont actifs ; une suite JS (Hoot/QUnit) peut être réintroduite
> en recréant `static/tests/` et en dé-commentant l'entrée du manifest.

**Lancer les tests :**

- Python : `odoo-bin -d <db> --test-enable --test-tags miro_gantt_view -i miro_gantt_view --stop-after-init`

**Bonnes pratiques à suivre pour toute nouvelle fonction ajoutée dans `utils/` ou `model/` :** si une suite JS est réintroduite, créer un fichier `static/tests/test_<nom_du_module>.js` correspondant, en s'inspirant du pattern des tests unitaires sur fonctions pures (sans dépendance au DOM ni à OWL quand c'est possible).
