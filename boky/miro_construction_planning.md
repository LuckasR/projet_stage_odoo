# Équipes, cadences et planning de chantier (`miro_construction_planning`)

> Ce module transforme les métrés d'un chantier en un planning : à partir des métiers, des équipes types et de leurs cadences de production, il calcule pour chaque phase de travaux l'équipe, l'effectif, la durée et le coût de main-d'œuvre, puis ordonnance automatiquement toutes les phases dans le temps en respectant l'ordre de la structure, les délais techniques et le nombre d'équipes disponibles. Le résultat s'affiche dans un diagramme de Gantt modifiable et dans une analyse de la charge par métier.

| Fiche | |
|---|---|
| Nom technique | `miro_construction_planning` |
| Version | 17.0.1.0.0 |
| Catégorie | Services/Project |
| Dépend de | `miro_construction_project` (chantiers, éléments, phases), `miro_hr_paie` (coûts salariaux), `resource` (calendriers de travail), `miro_gantt_view` (vue Gantt) |
| Utilisé par | `miro_construction_journal` (et, à travers lui, `miro_construction_overview`) ; ses champs sont aussi lus par `miro_mobile_api` et `miro_ai_assistant` |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Dans le module de base `miro_construction_project`, un chantier est décomposé en **éléments** de structure (semelles, longrines, poteaux, poutres, dalles, murs), chacun portant ses quantités (m³ de béton, kg d'acier, m² de coffrage, m² de surface) et découpé en **phases** (coffrage, ferraillage, coulage, décoffrage, élévation…) générées à partir de **gabarits**. Il restait à répondre aux questions que se pose un conducteur de travaux avant de démarrer :

- **Combien de temps** va durer chaque phase, et avec **quelle équipe** ?
- **Combien coûte** la main-d'œuvre du chantier, métier par métier ?
- **Dans quel ordre** et **à quelles dates** enchaîner des centaines de phases, sachant qu'on ne coule pas une dalle avant d'avoir les poteaux, qu'on attend 7 jours avant de décoffrer, et qu'on n'a qu'une équipe de coffrage ?
- **Combien d'ouvriers** de chaque métier faut-il prévoir, et à quels moments y a-t-il un pic ?

Faire ce travail à la main sur un tableur est long et devient faux dès que les métrés changent. Le module automatise ce raisonnement à partir de la notion de **cadence** (quantité produite par une équipe en une heure), utilisée couramment dans le BTP.

## 2. Fonctionnalités

### 2.1 Métiers et coût horaire chargé

Le menu **Construction > Configuration > Métiers** liste les métiers du chantier (livrés : maçon, coffreur, ferrailleur, manœuvre, chef d'équipe, électricien, plombier). Pour chacun, l'utilisateur voit :

- le nombre d'**employés actuels** exerçant ce métier ;
- le **coût horaire calculé** : moyenne des coûts horaires chargés de ces employés (salaire ramené à l'heure + charges patronales, d'après leur fiche de paie) ;
- un **coût horaire de référence** saisissable à la main, qui remplace le calcul (métier sous-traité, ou pas encore d'employé) ;
- le **coût horaire chargé** finalement retenu.

Sur la fiche employé, le métier saisi en texte libre par le module de paie est remplacé par une liste déroulante des métiers du planning.

### 2.2 Équipes types

Le menu **Équipes types** permet de définir des compositions d'équipe, par exemple « Coulage — petite équipe = 1 maçon + 3 manœuvres ». Le système affiche l'**effectif**, la **composition** en clair et le **coût horaire de l'équipe** (somme des coûts de ses membres). Une couleur peut être choisie pour distinguer l'équipe dans le Gantt.

Huit équipes sont créées à l'installation (petite et renforcée pour le coffrage, le ferraillage, le coulage et la maçonnerie), avec des couleurs par famille.

### 2.3 Cadences

Le menu **Cadences** associe un **type de phase** (coffrage, coulage…), éventuellement un **type d'élément** (poteau, dalle…), une **équipe** et une **cadence** (quantité produite par heure, dans l'unité de la phase). L'écran affiche aussi l'effectif, le coût horaire de l'équipe et le **coût unitaire** (coût de main-d'œuvre d'un m³, d'un m²…). Une case « Équipe par défaut » désigne l'équipe retenue pour chiffrer la phase.

À l'installation, une cadence est créée pour chaque ligne de gabarit et chaque type d'élément : le rendement du gabarit devient celui de la petite équipe (par défaut), la renforcée produisant 1,85 fois plus (une équipe deux fois plus nombreuse ne va pas deux fois plus vite). Les durées existantes sont ainsi conservées.

### 2.4 Main-d'œuvre prévue par phase

Sur chaque phase d'un élément, un bloc **« Main-d'œuvre prévue »** affiche l'équipe retenue, l'effectif, la durée en heures et en jours, le coût de main-d'œuvre et l'éventuel délai technique. Ces valeurs se recalculent automatiquement quand les métrés de l'élément ou les cadences changent ; un bouton « Recalculer » force la mise à jour.

### 2.5 Synthèse de la main-d'œuvre du chantier

Un onglet **« Main-d'œuvre »** sur la fiche chantier présente :

- le coût de main-d'œuvre prévu, les heures-personnes et les journées d'équipe ;
- deux compteurs d'alerte : **phases sans cadence** (ni durée ni coût) et **phases sans métré** (cadence connue mais quantité nulle, par exemple une hauteur manquante) ;
- un tableau par métier : employés actuels, heures-personnes, journées, coût ;
- un bouton « Recalculer la main-d'œuvre ».

Un champ « Frais fixes de chantier par jour » est également présent (voir limites).

### 2.6 Délais techniques entre phases

Dans les gabarits de phases, une colonne **« Délai après la phase précédente (j) »** permet d'imposer un temps d'attente minimal (séchage, prise du béton). Le décoffrage est livré avec un délai de 7 jours après le coulage.

### 2.7 Planification automatique du chantier

L'onglet **« Planning »** de la fiche chantier permet de régler :

- la **date de début des travaux** (obligatoire pour planifier) ;
- le **calendrier du chantier** (heures et jours travaillés, par exemple une semaine de 6 jours ; à défaut celui de la société) ;
- le nombre d'**équipes de même type en parallèle** (1 par défaut), avec des exceptions par équipe (« 2 équipes de ferraillage ») ;
- l'option **« Reporter sur les échéances »**, pour que l'échéance des phases suive le planning.

Le bouton **« Planifier le chantier »** (avec confirmation) calcule les dates de début et de fin de toutes les phases non terminées, met à jour les dates prévues des phases et des ouvrages, la date de fin prévue du chantier, sa durée en jours ouvrés, et affiche une notification (« N phase(s) planifiée(s) : fin prévue le … »). Les éventuelles remarques (par exemple un métier sans coût horaire) apparaissent dans un encadré d'avertissement.

### 2.8 Planning en Gantt, calendrier et liste

Le bouton **« Planning (Gantt) »** ouvre les phases planifiées dans la vue Gantt du module `miro_gantt_view` :

- barres regroupées par ouvrage puis par élément, colorées selon la couleur de l'équipe ;
- colonnes latérales : équipe, effectif, durée en jours ; avancement et retard visibles sur les barres ;
- zoom jour, semaine, mois ou année, ouverture directement sur la date de début du chantier, et chargement de toutes les phases en une fois (jusqu'à 2 000) ;
- une barre **déplacée ou étirée** à la souris met à jour les dates prévues de la phase et, si l'option est active, son échéance.

Les mêmes phases sont aussi consultables en **calendrier** (mensuel, filtrable par équipe) et en **liste** (triée par date, avec total du coût de main-d'œuvre, lignes en rouge si en retard).

### 2.9 Charge et effectif proposé par métier

Après la planification, l'onglet Planning affiche un tableau **« Effectif proposé par métier »** : effectif à prévoir (pointe), effectif moyen, jours de travail, heures-personnes, employés actuels et nombre **à recruter ou affecter**. Le bouton **« Charge par métier »** ouvre un graphique en barres et un tableau croisé par semaine et par métier, ainsi qu'une liste où les **jours de pointe** (tout l'effectif proposé mobilisé) sont en rouge.

## 3. Qui l'utilise et comment

| Rôle | Utilisation |
|---|---|
| Responsable méthodes / administrateur | Paramètre les métiers, les équipes types, les cadences et les délais techniques |
| Responsable RH | Renseigne le métier et la paie des employés, ce qui alimente les coûts horaires |
| Conducteur de travaux / chef de projet | Lance la planification, ajuste le Gantt, consulte la charge et le coût de main-d'œuvre |
| Chef de chantier | Consulte le planning et affecte ensuite les ouvriers au démarrage des travaux |

Parcours type :

1. Le chantier est saisi dans `miro_construction_project` : éléments, métrés et phases générées.
2. Chaque phase reçoit automatiquement une équipe, une durée et un coût ; l'onglet « Main-d'œuvre » signale les phases sans cadence ou sans métré, que l'on corrige.
3. Dans l'onglet « Planning », le conducteur de travaux saisit la date de début, choisit le calendrier et le nombre d'équipes en parallèle.
4. Il clique sur « Planifier le chantier » et lit la date de fin et les remarques.
5. Il ouvre le Gantt pour vérifier l'enchaînement et décale à la main les phases qui doivent l'être.
6. Il consulte la charge par métier pour savoir combien d'ouvriers recruter ou affecter ; s'il augmente le nombre d'équipes en parallèle et relance, le chantier se raccourcit et l'effectif proposé augmente.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `miro.trade` (nouveau) | Métier | `name`, `code`, `employee_ids`, `employee_count`, `computed_hourly_cost`, `manual_hourly_cost`, `hourly_cost` |
| `miro.crew` (nouveau) | Équipe type | `name`, `line_ids`, `headcount`, `hourly_cost`, `composition`, `color` |
| `miro.crew.line` (nouveau) | Membre d'une équipe type | `crew_id`, `trade_id`, `quantity`, `hourly_cost` |
| `miro.crew.rate` (nouveau) | Cadence d'une équipe sur un type de phase | `phase_type`, `element_type_id` (vide = tous), `crew_id`, `rate`, `qty_key` (unité), `is_default`, `unit_cost` |
| `miro.project.crew.capacity` (nouveau) | Nombre d'équipes d'un type en parallèle sur un chantier | `project_id`, `crew_id`, `count` (unique par chantier et équipe) |
| `miro.planning.load` (nouveau) | Charge d'un métier par jour, issue du dernier planning | `project_id`, `date`, `trade_id`, `needed` (pointe du jour), `available` (effectif proposé), `person_hours`, `usage_pct`, `saturated` |
| `project.task` (étendu) | Phase : main-d'œuvre et dates planifiées | `miro_crew_rate_id`, `miro_crew_id`, `miro_headcount`, `miro_duration_hours`, `miro_duration_days`, `miro_labor_cost`, `miro_min_lag_days`, `miro_planned_start`, `miro_planned_end` |
| `project.project` (étendu) | Chantier : règles et résultat du planning, synthèse | `miro_calendar_id`, `miro_parallel_crews`, `miro_crew_capacity_ids`, `miro_update_deadlines`, `miro_planned_on`, `miro_planning_warnings`, `miro_planned_phase_count`, `miro_planned_workdays`, `miro_load_ids`, `miro_daily_overhead`, champs calculés de coût et de synthèse |
| `construction.phase.template.line` (étendu) | Ligne de gabarit de phase | `min_lag_days` (délai technique) |
| `construction.element` (étendu) | Élément de structure | Recalcul de la main-d'œuvre quand ses quantités changent |
| `hr.employee` (étendu) | Employé | `miro_trade_id` (métier du planning), méthode `_miro_loaded_hourly_cost` |

Relations importantes :

- un **métier** regroupe des employés ; une **équipe type** est composée de lignes (métier × nombre) ;
- une **cadence** relie un type de phase (et éventuellement un type d'élément) à une équipe ;
- chaque **phase** mémorise la cadence et l'équipe retenues ; ses dates planifiées sont propres au module, distinctes des dates prévues du module de base (qu'elles mettent à jour) ;
- un **chantier** possède ses lignes de charge par métier, recréées à chaque planification.

## 5. Règles métier et calculs

**Coût horaire chargé d'un employé** (`models/hr_employee.py`, `_miro_loaded_hourly_cost`) :

- journalier : taux journalier ÷ heures par jour ; horaire : taux horaire ; mensuel : salaire ÷ (jours de référence × heures par jour) ;
- si l'employé est soumis aux cotisations : × (1 + (taux patronal CNaPS + taux patronal santé) / 100).

**Coût d'un métier** (`models/trade.py`) : moyenne des coûts non nuls de ses employés actifs, sauf si un coût de référence est saisi. Le calcul est fait en `sudo` car les taux de paie sont réservés aux RH.

**Choix de la cadence** (`models/crew_rate.py`, `_rate_for`) : parmi les cadences positives du type de phase, celle propre au type d'élément passe avant la générale, puis l'équipe par défaut avant les autres, puis l'ordre de séquence.

**Main-d'œuvre d'une phase** (`models/project_task.py`, `_miro_refresh_labor`) :

- durée (h) = quantité de la phase ÷ cadence ; durée (j) = durée (h) ÷ heures normales par jour ;
- heures-personnes (heures allouées de la tâche) = durée × effectif de l'équipe ;
- coût = durée × coût horaire de l'équipe ;
- une phase **commencée** (avancement non nul, terminée ou annulée) garde ses valeurs, sauf recalcul forcé depuis la phase ;
- recalcul automatique quand les quantités d'un élément changent, quand ses phases sont générées, quand une cadence est créée, modifiée ou supprimée, ou quand la composition d'une équipe change.

**Planification** (`models/planner.py`, classe `SitePlanner`) : ordonnancement en série (« serial schedule generation scheme ») :

1. Les phases non terminées sont regroupées par **classe d'élément et niveau** : fondations, dallage sur terre-plein, poteaux, poutres, dalles, murs, autres.
2. Les groupes sont traités dans l'ordre de la structure : fondations d'abord, puis niveau par niveau (altitude puis séquence), et dans un niveau poteaux → poutres → dalle → murs.
3. Chaque groupe attend la fin de ses **prérequis** : le dallage attend les fondations ; les poteaux attendent la dalle du niveau inférieur (ou les fondations) ; les poutres attendent les poteaux du niveau ; la dalle attend les poutres (ou les poteaux) ; les murs attendent les poteaux.
4. Dans un élément, les phases suivent l'ordre du gabarit ; chacune commence au plus tôt à la fin de la phase dont elle dépend **plus le délai technique**, compté en jours calendaires (le béton sèche aussi le dimanche).
5. Une phase n'est placée que lorsqu'une **équipe de son type est libre** pendant toute sa durée : à aucun moment le nombre d'équipes d'un même type au travail ne dépasse la capacité du chantier.
6. Le temps est découpé en **quarts d'heure ouvrés** du calendrier du chantier (jours fériés et congés du calendrier inclus) : une phase de 6 h commencée à 15 h se termine le lendemain.
7. Une phase partiellement avancée n'est planifiée que pour son reste à faire (durée × (1 − avancement)).

**Application du résultat** (`models/project_planning.py`, `_miro_apply_plan`) :

- chaque phase reçoit ses dates planifiées, ses dates prévues (jour local) et sa durée prévue en jours, ainsi que son échéance si l'option est active ;
- chaque ouvrage (tâche parente) s'étend de la première à la dernière de ses phases ;
- la fin prévue du chantier est la fin de la dernière phase ; la durée en jours ouvrés est calculée sur le calendrier ;
- la **charge par métier** est recalculée : pour chaque jour et chaque métier, la pointe de personnes simultanées et les heures-personnes ; l'**effectif proposé** d'un métier est sa pointe sur tout le planning ; un jour est « saturé » quand la pointe du jour atteint cet effectif ;
- un avertissement est ajouté pour chaque métier mobilisé sans coût horaire.

**Synchronisation depuis le Gantt** (`models/project_planning.py`, `ProjectTask.write`) : quand les dates planifiées d'une phase sont modifiées à la main, ses dates prévues et son échéance suivent. Un indicateur de contexte (`miro_planner`) évite que la planification automatique ne déclenche cette synchronisation en boucle.

**Données par défaut** (`models/defaults.py`, `data/default_crews.xml`) : rattachement des employés à un métier retrouvé par son nom (ou créé), création des équipes et cadences de départ et du délai de décoffrage ; l'opération est idempotente et ne remplace jamais une valeur existante.

## 6. Interfaces

| Type | Élément |
|---|---|
| Menus | Construction > Configuration > **Métiers**, **Équipes types**, **Cadences** |
| Fiche chantier | Onglets **« Main-d'œuvre »** et **« Planning »** (ajoutés à la fois au formulaire chantier de construction et au formulaire projet standard) avec les boutons « Recalculer la main-d'œuvre », « Planifier le chantier », « Planning (Gantt) », « Charge par métier » |
| Fiche phase | Bloc « Main-d'œuvre prévue » et dates planifiées, bouton « Recalculer » |
| Fiche employé | Champ « Métier » sous forme de liste des métiers du planning |
| Gabarit de phase | Colonne « Délai après la phase précédente (j) » |
| Vues du planning | Gantt (`miro_gantt`), calendrier et liste des phases planifiées |
| Vues de charge | Graphique en barres, tableau croisé et liste de `miro.planning.load` |
| JavaScript | `static/src/gantt/gantt_initial_date.js` : extension (patch) de la vue Gantt qui lit dans le contexte de l'action la date d'ouverture (`miro_gantt_initial_date`) et le nombre de barres chargées (`miro_gantt_limit`), sans modifier le module Gantt |
| Données | Métiers de base, équipes et cadences par défaut |
| Rapports PDF, assistants, routes HTTP, tâches planifiées | Aucun |

## 7. Sécurité et droits d'accès

Tous les nouveaux modèles (métiers, équipes, lignes d'équipe, cadences, charge, capacités par chantier) sont accessibles en **lecture, écriture, création et suppression à tout utilisateur interne** (`base.group_user`), sans distinction de rôle (`security/ir.model.access.csv`).

- Les données de paie restent protégées : la liste des employés d'un métier et le champ `miro_trade_id` sont réservés au groupe RH ; le coût d'un métier est calculé en `sudo` pour être lisible depuis le planning sans exposer les salaires individuels.
- La vue Gantt du planning interdit la création et la suppression de phases (`create="0" delete="0"`) mais n'utilise pas les groupes Gantt de `miro_gantt_view` : tout utilisateur pouvant modifier les tâches peut déplacer les barres.

## 8. Intégration avec les autres modules

- **`miro_construction_project`** : fournit les chantiers, éléments, niveaux, gabarits de phases et quantités ; le module surcharge le calcul des heures prévues d'une phase (`_compute_hours`) pour utiliser la cadence d'équipe, et réutilise la détection des dallages sur terre-plein (`is_ground_slab`).
- **`miro_hr_paie`** : modes de paie, taux, cotisations et paramètres de la société (heures par jour, jours de référence, taux patronaux) pour le coût horaire chargé.
- **`resource`** : calendriers de travail et calcul des intervalles ouvrés.
- **`miro_gantt_view`** : affichage et modification du planning ; extension de son modèle et de son rendu JavaScript par patch.
- **`miro_construction_journal`** : dépend de ce module ; il utilise `_miro_loaded_hourly_cost` pour valoriser les heures d'ouvriers saisies au journal.
- **`miro_mobile_api`** et **`miro_ai_assistant`** : lisent le métier de l'employé, l'équipe proposée et les dates planifiées des phases.

## 9. Points techniques notables

- **Un vrai algorithme d'ordonnancement** : le planificateur est une classe Python indépendante de la base (`SitePlanner`) qui calcule un résultat en mémoire, ensuite appliqué en une passe. Il combine contraintes de précédence (structure, dépendances de gabarit, délais techniques) et contraintes de ressources (nombre d'équipes en parallèle), à la manière d'un « resource-constrained project scheduling ».
- **Temps discrétisé au quart d'heure sur un calendrier réel** (`WorkTime`) : les créneaux ouvrés sont générés à partir du calendrier Odoo (fuseau horaire, jours fériés), étendus à la demande par tranches de 370 jours, et retrouvés par recherche dichotomique (`bisect`).
- **Logique métier du gros œuvre encodée** : ordre fondations → poteaux → poutres → dalle, niveau par niveau, et distinction dallage/dalle d'étage.
- **Recalculs en cascade maîtrisés** : modification d'une cadence, d'une équipe ou d'un métré → recalcul des seules phases concernées, en épargnant les phases commencées ; un indicateur de contexte (`miro_no_refresh`) évite les recalculs inutiles lors de l'installation.
- **Coût cohérent dans toute l'application** : le même coût horaire chargé, dérivé de la paie, sert au chiffrage prévisionnel et au suivi réel du journal.
- **Proposition plutôt que contrainte** : le planning ne dépend pas des employés existants ; il déduit l'effectif à prévoir et le compare à l'effectif actuel (« à recruter / affecter »).
- **Extension non intrusive d'un composant JavaScript** : le patch OWL ajoute deux réglages au Gantt par le contexte, sans toucher au module Gantt.
- **Installation intelligente** : les cadences initiales sont dérivées des rendements des gabarits existants, si bien que l'installation ne modifie pas les durées déjà connues.

## 10. Limites et pistes d'amélioration

- **Frais fixes journaliers non exploités** : le champ « Frais fixes de chantier par jour » est décrit comme servant à départager une petite équipe et une équipe renforcée, mais aucun code ne l'utilise ; le choix de l'équipe se fait uniquement par la case « Équipe par défaut ». Une optimisation coût/délai reste à écrire.
- **Description du manifeste en retard** : elle présente le module comme « étape 1 » (équipes et cadences) alors que la planification, le Gantt et la charge par métier sont déjà implémentés.
- **Coûts figés entre deux recalculs** : le coût de main-d'œuvre d'une phase est stocké ; une hausse de salaire ou de coût de métier n'est répercutée qu'après « Recalculer » ou une nouvelle planification.
- **Tableau de synthèse en journées de 8 h** fixes, alors que le reste du module utilise le paramètre « heures normales par jour ».
- **Ordre de la structure figé dans le code** : les classes d'éléments et leurs prérequis sont codés en dur ; les éléments « autres » n'ont aucun prérequis.
- **Planification gloutonne** : chaque phase est placée au plus tôt dans l'ordre de traitement, sans recherche d'un optimum global ni calcul de chemin critique ou de marge.
- **Modifications manuelles écrasées** : relancer la planification remplace les dates des phases non terminées, y compris celles ajustées à la main dans le Gantt (la confirmation l'annonce).
- **Calendrier sans heure ouvrée** : le cas lève une erreur Python brute plutôt qu'un message utilisateur.
- **Droits larges** : tout utilisateur interne peut modifier métiers, équipes et cadences.
- **Pas de tests automatisés** pour le planificateur, alors qu'il s'y prête bien (classe indépendante).
- Pistes : affectation nominative des ouvriers aux phases, prise en compte des disponibilités réelles, comparaison planning initial / planning recalé (planning de référence), rapport PDF du planning.
