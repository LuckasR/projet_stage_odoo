# Gestion de Projets de Construction (module Odoo)

## Ce que fait le module

1. **Hérite de `project.project` et `project.task`** — aucune donnée native
   n'est modifiée ni perdue, on ajoute uniquement des champs et des vues.
2. **Diagramme hiérarchique du chantier** : depuis un projet, le bouton
   "Diagramme du chantier" ouvre une vue `hierarchy` (fonctionnalité native
   Odoo 17+) qui affiche le projet → tâches → sous-tâches → sous-sous-tâches
   sur des niveaux illimités, chaque nœud pouvant être déplié/replié
   individuellement (des boutons du diagramme permettent aussi de tout
   déplier / tout replier d'un coup). Le pourcentage d'avancement est affiché
   en haut à droite de chaque carte.
3. **Cliquer sur une carte** ouvre la fiche complète de la tâche/sous-tâche
   correspondante (comportement natif de la vue hierarchy), quel que soit
   son niveau de profondeur.
4. **Avancement automatique en cascade** : une tâche sans sous-tâche a un
   avancement saisi à la main (`x_avancement_manuel`) ; une tâche avec des
   sous-tâches affiche automatiquement la moyenne de l'avancement de ses
   enfants directs — et donc, de proche en proche, de tous ses descendants.
5. **Fonctionnalités additionnelles utiles pour un chantier** :
   - Fiche projet enrichie : adresse, type de construction, phase du
     chantier, maître d'ouvrage, architecte, chef de chantier, surface,
     dates prévisionnelles, budget.
   - Fiche tâche enrichie : corps de métier, responsable technique,
     priorité chantier, dates prévues, coût prévu/réel.
   - Détection automatique des tâches **en retard** (échéance dépassée et
     avancement < 100 %), avec mise en couleur rouge dans les listes.
   - Registre **d'incidents de chantier** par tâche (gravité, état,
     responsable) consultable depuis la tâche ou depuis un menu dédié.
   - Consolidation automatique des coûts (prévu/réel) au niveau du projet.
   - Vues liste avec barres de progression et code couleur.

## Installation

1. Copier le dossier `construction_project` dans votre dossier
   `addons` (ou `custom-addons`) Odoo.
2. Redémarrer le serveur Odoo, activer le mode développeur.
3. Apps → Mettre à jour la liste des Apps → rechercher
   "Gestion de Projets de Construction" → Installer.

## Points à vérifier / adapter selon votre version d'Odoo

Ce module a été écrit pour **Odoo 17.0** (la vue `hierarchy` utilisée pour le
diagramme est une fonctionnalité introduite en version 17 ; en version 16 ou
antérieure, il faudra la remplacer par une vue liste groupée ou un widget
personnalisé).

Quelques éléments dépendent de la version exacte de votre Odoo et sont donc
à vérifier après installation (activez le mode développeur et regardez les
éventuelles erreurs au chargement) :

- Les identifiants XML des vues natives héritées :
  `project.edit_project` (formulaire projet) et `project.view_task_form2`
  (formulaire tâche). Ce sont les XMLID standards en 17.0 ; si votre
  installation utilise des vues personnalisées qui remplacent déjà ces
  vues, vérifiez qu'il n'y a pas de conflit de xpath.
- Le xmlid du menu parent `project.menu_project_report` dans
  `views/menu_views.xml` : s'il n'existe pas dans votre version, remplacez
  `parent="project.menu_project_report"` par un autre menu (ex.
  `project.menu_main_pm`) ou supprimez cette ligne et accédez au modèle
  `construction.task.incident` via Paramètres techniques.
- Les couleurs Bootstrap (`text-bg-success`, etc.) utilisées dans le
  template de la vue hierarchy correspondent à Bootstrap 5 (utilisé par
  Odoo 17). Si nécessaire, remplacez par les classes `badge-success`, etc.

## Idées d'évolutions possibles

- Vue Gantt (module `project_enterprise` en édition Enterprise) pour
  planifier les tâches dans le temps en plus du diagramme hiérarchique.
- Pondération de l'avancement des tâches parentes par la durée prévue de
  chaque sous-tâche plutôt qu'une simple moyenne arithmétique.
- Génération d'un rapport PDF de suivi de chantier (avancement, coûts,
  incidents) via le module `pdf` / QWeb.
- Envoi d'une notification automatique (email/activité) au chef de chantier
  quand une tâche passe en retard ou qu'un incident "critique" est créé.
- Champs météo / conditions de chantier au niveau de chaque journée.
