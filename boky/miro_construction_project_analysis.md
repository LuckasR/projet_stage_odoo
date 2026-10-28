# Analyse de plans et génération des phases, première version (`miro_construction_project_analysis`)

> Ce dossier n'est pas un module Odoo autonome : c'est un lot de fichiers à fusionner dans `miro_construction_project` pour ajouter l'analyse automatique des plans (détection des éléments de construction et de leurs quantités), la validation humaine des résultats, puis la génération automatique des phases de travaux. Cette fonctionnalité a depuis été intégrée, sous une forme plus aboutie, dans `miro_construction_project` lui-même.

| Fiche | |
|---|---|
| Nom technique | `miro_construction_project_analysis` (nom du dossier ; pas de manifeste à la racine) |
| Version | Aucune (pas de `__manifest__.py`) |
| Catégorie | Aucune ; code destiné à `miro_construction_project` (Services/Project) |
| Dépend de | Selon `__manifest___SNIPPET.py` : `project`, `mail`, plus les modèles existants de `miro_construction_project` (`construction.element`, `construction.work`, `construction.file`) |
| Utilisé par | Aucun module ; le dossier n'est pas installable |
| Auteur / licence | Non précisé dans le dossier (code du stagiaire) |

## 1. Le besoin métier

Pour lancer un chantier, il faut transformer un plan (par exemple le plan des fondations) en une liste d'éléments à construire — semelle S1, semelle S2, poteau P3… — avec pour chacun des quantités : volume de béton (m³), poids d'acier (kg), surface de coffrage (m²). Chaque élément se décompose ensuite en phases de travaux (ferraillage, puis coffrage, puis coulage du béton), dont la durée dépend des quantités.

Ce travail de « métré » (relevé des quantités sur plan) et de découpage en tâches est long et répétitif quand il est fait à la main. L'idée du dossier est de l'automatiser en trois temps :

1. un **service d'analyse** lit le plan et propose les éléments détectés avec leurs quantités et un indice de confiance ;
2. un **humain valide** ou corrige ces propositions (l'automate ne crée jamais directement de données définitives) ;
3. Odoo **génère** les éléments et leurs phases de travaux dans le projet, avec les heures prévues et l'enchaînement des phases.

## 2. Fonctionnalités

### Lancer l'analyse d'un plan
Sur une fiche « Analyse de plan », l'utilisateur choisit un plan du projet et lance l'analyse. Odoo envoie au service d'analyse externe un lien de téléchargement sécurisé du fichier joint au plan et l'adresse à laquelle renvoyer le résultat. L'analyse passe à l'état « En cours ».

### Recevoir le résultat
Le service d'analyse renvoie un JSON listant les éléments détectés (clé, type, quantités, dimensions, confiance, page et zone du plan). Le fichier `exemple_resultat.json` en donne un exemple : deux semelles S1 et S2, avec une confiance de 0,93 et 0,71. Le résultat crée des **brouillons** d'éléments, jamais des éléments définitifs.

### Tester sans service externe
Un JSON peut être collé à la main dans la fiche d'analyse puis importé (« Importer le JSON »), ce qui permet de tester toute la chaîne sans service d'analyse.

### Revoir les brouillons
Chaque brouillon indique s'il est nouveau, modifié ou inchangé par rapport aux éléments déjà présents dans le projet, et signale une anomalie si le type détecté est inconnu. Les quantités sont modifiables. L'utilisateur peut valider, rejeter ou remettre « à valider » chaque brouillon, ou valider d'un coup tous ceux dont la confiance dépasse 0,9.

### Générer les éléments et les phases
Les brouillons validés deviennent des éléments de construction rattachés au bon ouvrage (par exemple « Fondation », créé s'il n'existe pas). Pour chaque élément, les phases sont créées comme tâches du projet à partir d'un gabarit, avec les heures prévues et les dépendances entre phases.

### Gérer les révisions de plan
Quand un plan est révisé (indice A, B…), une nouvelle analyse met à jour les éléments existants grâce à leur clé stable (S1, S2…). Les éléments absents de la nouvelle analyse sont signalés dans le fil de discussion de l'analyse, mais jamais supprimés automatiquement.

### Gabarits de phases et types d'éléments
Un type d'élément (semelle, poteau…) relie le code renvoyé par l'analyse, l'ouvrage de rattachement et un gabarit de phases. Un exemple est fourni : le type « Semelle » avec le gabarit Ferraillage → Coffrage → Coulage béton.

## 3. Qui l'utilise et comment

Tel quel, personne : le dossier n'est pas installable. Dans l'intention du code, une fois fusionné :

| Profil (groupe Odoo) | Usage prévu |
|---|---|
| Utilisateur Projet (`project.group_project_user`) | Lance les analyses, revoit, valide ou rejette les brouillons ; lit les types et gabarits |
| Responsable Projet (`project.group_project_manager`) | Tous les droits, y compris paramétrer les types d'éléments et les gabarits de phases |
| Service d'analyse externe | Appelle la route de retour avec le résultat JSON |

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `construction.analysis` (nouveau) | Une analyse d'un plan, avec son cycle de vie | `file_id` (plan), `project_id`, `revision`, `engine`, `state` (À lancer / En cours / Terminée / Échec), `started_at`, `finished_at`, `error_log`, `payload_json`, `draft_ids` |
| `construction.element.draft` (nouveau) | Élément détecté en attente de validation | `analysis_id`, `key`, `type_code`, `type_id`, `quantities` / `dimensions` / `source_bbox` (champs JSON), `confidence`, `source_page`, `issue`, `change_type`, `state` (À valider / Validé / Rejeté / Généré), `element_id` |
| `construction.element.type` (nouveau) | Type d'élément reconnu par l'analyse | `name`, `code` (unique), `work_name` (ouvrage de rattachement), `phase_template_id` |
| `construction.phase.template` (nouveau) | Gabarit de phases | `name`, `line_ids` |
| `construction.phase.template.line` (nouveau) | Une phase du gabarit | `sequence`, `name`, `phase_type`, `depends_on_line_id`, `qty_key`, `rate_per_hour`, `fixed_hours` |
| `construction.element` (extension) | Élément de construction existant, enrichi | `key`, `type_id`, `source_file_id`, `source_page`, `confidence`, `qty_beton_m3`, `qty_acier_kg`, `qty_coffrage_m2`, `task_ids`, `progress` (calculé) |
| `project.task` (extension) | Tâche devenue « phase » d'un élément | `element_id`, `phase_type`, `phase_template_line_id` |

## 5. Règles métier et calculs

**Envoi au service** (`models/models_analysis/construction_analysis.py`, `action_start`). L'URL du service est lue dans le paramètre système `miro_construction.analysis_url`. Le fichier joint au plan est partagé par un lien `/web/content/...` muni d'un jeton d'accès. La requête porte un en-tête `X-Miro-Token`. En cas d'échec réseau, l'analyse passe en « Échec » avec le message d'erreur.

**Analyses bloquées** (`_cron_timeout_running`). Une analyse restée « En cours » plus de 30 minutes sans réponse est passée en « Échec ».

**Traitement du résultat** (`_process_result`) :
- le JSON doit être un objet, avec la version de schéma attendue (1) et une liste `elements` ;
- un élément sans clé ou en double est ignoré et noté dans le journal d'erreur ;
- le type est retrouvé par son code ; s'il est inconnu, le brouillon porte une anomalie ;
- l'évolution est calculée par `_detect_change` : « Nouveau » si aucun élément du projet n'a cette clé, « Modifié » si l'une des trois quantités diffère, sinon « Inchangé » ;
- un brouillon déjà validé ou généré n'est jamais réécrasé ;
- les éléments du projet absents de l'analyse sont listés dans le fil de discussion.

**Validation** (`construction_element_draft.py`). Un brouillon ne peut être validé ou généré sans type (contrainte). Une clé est unique par analyse (contrainte SQL).

**Génération idempotente** (`action_generate`). « Idempotent » signifie que relancer l'opération ne crée pas de doublons. L'ouvrage est retrouvé par son nom ou créé ; l'élément est retrouvé par sa clé dans le projet et mis à jour, sinon créé (création groupée). L'unicité de la clé par projet est vérifiée par une contrainte dans `construction_element_ext.py`.

**Phases** (`construction_element_ext.py`, `_generate_tasks`). Pour chaque ligne du gabarit, une tâche est créée seulement si l'élément n'a pas déjà une phase de ce code. Elle est nommée « S1 - Ferraillage », rattachée à la tâche de l'ouvrage, et les dépendances entre phases sont posées si le champ natif `depend_on_ids` existe. Rien n'est jamais supprimé.

**Heures prévues** (`construction_phase_template.py`, `_compute_hours`) : quantité de référence / rendement horaire, sinon heures forfaitaires. Avec le gabarit fourni, une semelle de 145 kg d'acier demande 145 / 25 = 5,8 h de ferraillage.

**Avancement d'un élément** (`_compute_progress`) : moyenne des phases terminées pondérée par les heures prévues (poids 1 si non renseignées), en ignorant les phases annulées.

## 6. Interfaces

| Type | Élément |
|---|---|
| Route HTTP | `POST /construction/analysis/result` (`controllers/main.py`), accès public protégé par jeton, sans CSRF. Codes de réponse : 401 jeton invalide, 400 JSON invalide, 404 analyse inconnue, 409 analyse non en cours, 422 résultat refusé, 200 avec le nombre de brouillons. |
| Tâche planifiée | « Construction : analyses bloquées », toutes les 10 minutes (`data/ir_cron.xml`) |
| Données | Gabarit et type « Semelle » de démonstration (`data/construction_phase_template_data.xml`) |
| Actions | Boutons prévus par les méthodes `action_start`, `action_retry`, `action_import_payload`, `action_validate_confident`, `action_generate`, `action_view_drafts`, `action_validate`, `action_reject`, `action_reset`, `action_generate_tasks`, `action_view_tasks` |
| Vues XML et menus | Aucun : le snippet de manifeste indique « tes vues (à créer) » |
| JavaScript | Aucun |

## 7. Sécurité et droits d'accès

- `security/ir.model.access.csv` définit les droits pour les cinq nouveaux modèles : lecture seule des types et gabarits pour l'utilisateur Projet, tous droits pour le responsable ; l'utilisateur peut créer et modifier des analyses et modifier des brouillons, sans supprimer.
- La route de retour est publique mais exige l'en-tête `X-Miro-Token`, égal au paramètre système `miro_construction.api_token`. La comparaison utilise `hmac.compare_digest`, qui évite de deviner le jeton en mesurant le temps de réponse. Si aucun jeton n'est configuré, tout appel est refusé.
- La route travaille ensuite en superutilisateur, ce qui est justifié puisque l'appelant est une machine authentifiée par le jeton.
- Le fichier du plan est exposé au service externe via un jeton d'accès propre à la pièce jointe, pas via une session utilisateur.

## 8. Intégration avec les autres modules

**Destination prévue.** Les fichiers `*_SNIPPET.py` indiquent explicitement qu'ils sont à fusionner dans `miro_construction_project` : ajouter `from . import controllers` au `__init__.py`, ajouter trois imports à la fin de `models/__init__.py` (« l'ordre compte : après tes modèles existants »), et ajouter les fichiers de sécurité et de données au manifeste. Le code suppose l'existence de `construction.element`, `construction.work` et `construction.file`.

**État de l'intégration.** La comparaison avec `custom-addons/miro_construction_project/` montre que la fonctionnalité **a été intégrée puis a évolué** ; les fichiers du dossier sont tous différents de leurs équivalents actuels :

| Aspect | Ce dossier (première version) | `miro_construction_project` actuel |
|---|---|---|
| Modèle de plan | `construction.file` | `construction.dwg.files` (plans DWG/DXF) ; `construction.file` n'existe plus dans le dépôt |
| Moteur d'analyse | Service externe appelé en HTTP, réponse par rappel (*callback*) | Analyse interne exécutée en tâche de fond `queue_job` (`with_delay`), avec trois moteurs : blocs DXF, géométrie des fondations, murs détectés (`construction_analysis_dxf.py`, `_footing`, `_wall`, `_opening`…) |
| Route `/construction/analysis/result` | Présente | Absente ; `controllers/main.py` sert désormais les fichiers DXF |
| Cron des analyses bloquées | Présent | Absent (le suivi est assuré par `queue_job`) |
| Test manuel | Champ `payload_json` + bouton d'import | Champ `manual_json` utilisé à la place du moteur |
| Quantités | béton, acier, coffrage | + surface (`surface_m2`) ; niveaux de plan |
| `construction.element` | Extension (`_inherit`) | Défini directement dans `models/construction_element.py` |
| Génération | Synchrone | Par lots en tâche de fond (`_job_generate`, nouvelles tentatives à 30 s puis 120 s) |

Le dossier est donc à lire comme une **étape intermédiaire** conservée dans le dépôt (dernier commit le concernant : « add_change », 5 octobre 2026), pas comme du code actif.

## 9. Points techniques notables

- **Humain dans la boucle.** L'automate ne produit que des brouillons ; seule une validation explicite crée des données définitives. Le seuil de confiance permet d'accélérer la validation des cas sûrs.
- **Idempotence et clés stables.** La clé métier (S1, P3…) sert d'identifiant à travers les révisions de plan ; génération et création des phases peuvent être relancées sans doublons, et rien n'est supprimé automatiquement.
- **Contrat d'échange versionné.** Le JSON porte un `schema_version`, ce qui permet de faire évoluer le format sans casser silencieusement l'import.
- **Paramétrage plutôt que code.** Types d'éléments, gabarits, rendements et dépendances de phases sont des données modifiables par un responsable.
- **Architecture asynchrone par rappel.** Odoo ne reste pas bloqué pendant l'analyse : le service rappelle Odoo quand il a fini, et un cron rattrape les analyses perdues.
- **Sécurité de la route publique** : jeton partagé, comparaison à temps constant, contrôle de l'état de l'analyse, savepoint pour ne pas laisser de données partielles.
- **Méthode de travail.** Le découpage en *snippets* à fusionner montre une démarche incrémentale : prototyper la fonctionnalité à part, puis l'intégrer et la faire évoluer (passage à une analyse DXF interne et à `queue_job`).

## 10. Limites et pistes d'amélioration

- **Non installable tel quel** : pas de manifeste ni de `__init__.py` à la racine, il faut fusionner les fichiers à la main dans `miro_construction_project`.
- **Obsolète par rapport au module actuel** : il référence le modèle `construction.file`, qui n'existe plus ; le fusionner aujourd'hui créerait des conflits avec la version intégrée.
- **Aucune vue ni menu** : les actions n'ont pas d'interface dans ce dossier.
- **Service d'analyse non fourni** : le dossier décrit le contrat d'échange mais ne contient pas le moteur qui lit réellement les plans. Rien dans le code n'indique qu'il s'agisse d'IA ; seul l'indice de confiance suggère une détection automatique.
- **Trois quantités codées en dur** (béton, acier, coffrage) dans plusieurs fichiers.
- **Pas de tests automatisés.**
- **Piste** : supprimer ce dossier du dépôt (ou l'archiver hors de `custom-addons`) puisque la fonctionnalité vit désormais dans `miro_construction_project`, afin d'éviter toute confusion.
