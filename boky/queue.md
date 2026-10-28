# File d'attente de tâches OCA (`queue`)

> Dépôt communautaire OCA qui ajoute à Odoo une file de tâches de fond (« jobs ») : une méthode longue est mise en attente puis exécutée en arrière-plan par des processus dédiés, sans bloquer l'utilisateur. Ce n'est pas du code écrit pendant le stage, mais une brique tierce sur laquelle reposent l'assistant IA et l'analyse des plans.

| Fiche | |
|---|---|
| Nom technique | `queue` (dépôt `OCA/queue`, branche 17.0) contenant six modules |
| Version | `queue_job` 17.0.1.5.3 ; autres modules 17.0.1.0.0 à 17.0.1.2.0 |
| Catégorie | Generic Modules (Others pour `queue_job_cron_jobrunner`) |
| Dépend de | `queue_job` : `mail`, `base_sparse_field`, `web` ; les autres modules dépendent de `queue_job` |
| Utilisé par | `miro_ai_assistant`, `miro_construction_project` |
| Auteur / licence | Odoo Community Association (OCA), avec Camptocamp, ACSONE, Akretion ; `queue_job` et `test_queue_job` en LGPL-3, les quatre autres en AGPL-3 |

## 1. Le besoin métier

Par défaut, Odoo traite chaque action d'un utilisateur dans sa requête web : tant que le calcul n'est pas fini, l'écran attend, et au-delà d'une limite de temps la requête est interrompue. Or le projet contient des traitements longs ou dépendants d'un service extérieur :

- l'appel à un modèle d'IA pour répondre dans la messagerie (plusieurs secondes, parfois des nouvelles tentatives) ;
- la lecture de plans DXF pour détecter murs, façades, ouvertures et éléments, puis la génération des phases de travaux.

Il faut donc pouvoir dire « fais ce travail plus tard, en arrière-plan », avec un suivi de l'état, des nouvelles tentatives en cas d'échec et une limite au nombre de traitements simultanés. Les tâches planifiées natives d'Odoo (`ir.cron`) ne suffisent pas : elles s'exécutent à heure fixe et ne mémorisent pas les paramètres d'un appel précis. C'est ce qu'apporte `queue_job`.

## 2. Fonctionnalités

### Mise en file d'une méthode (`queue_job`)
Un développeur écrit `record.with_delay().ma_methode(args)` au lieu de `record.ma_methode(args)` : l'appel est enregistré comme job avec ses arguments et l'utilisateur qui l'a déclenché, puis exécuté dès qu'une place se libère. Les états possibles sont notamment : en attente de dépendances, en attente, mis en file, démarré, terminé, échoué, annulé.

### Canaux et capacités (`queue_job`)
Les jobs sont répartis dans des canaux arborescents (`root`, `root.miro_assistant`…), chacun avec un nombre maximal de jobs simultanés. Cela évite qu'un type de traitement monopolise toutes les ressources.

### Nouvelles tentatives et suivi (`queue_job`)
Un job en échec peut être relancé automatiquement selon un schéma de délais. Un menu « Job Queue » permet de consulter les jobs, leurs erreurs, de les relancer ou de les annuler.

### Sous-modules complémentaires
| Module | Rôle |
|---|---|
| `queue_job` | Le cœur : modèle `queue.job`, canaux, fonctions de job, *jobrunner* (processus qui distribue les jobs) |
| `queue_job_cron` | Permet d'exécuter une tâche planifiée Odoo sous forme de job |
| `queue_job_cron_jobrunner` | Exécute les jobs via une tâche planifiée, sans jobrunner dédié (statut « Alpha ») |
| `queue_job_subscribe` | Choisit quels utilisateurs sont notifiés des jobs en échec |
| `base_import_async` | Import de fichiers CSV en arrière-plan |
| `test_queue_job` | Modèles et tests automatisés de `queue_job` ; pas d'usage en production |

Le code des modules du stage ne fait appel qu'à `queue_job`. Sur la base de développement, c'est d'ailleurs le seul sous-module installé : `queue_job_cron`, `queue_job_cron_jobrunner`, `queue_job_subscribe`, `base_import_async` et `test_queue_job` sont présents dans le dépôt mais non installés.

## 3. Qui l'utilise et comment

- **Les utilisateurs** ne le voient pas directement : ils constatent seulement que l'envoi d'un message au bot ou le lancement d'une analyse rend la main immédiatement.
- **Les développeurs** des modules `miro_*` déclarent leurs canaux et fonctions de job dans des fichiers XML et appellent `with_delay`.
- **L'administrateur** (groupe « Job Queue Manager ») suit les jobs dans le menu Job Queue et règle les capacités dans `odoo.conf`.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `queue.job` | Un job : appel différé d'une méthode | `uuid`, `state`, `channel`, `model_name`, `method_name`, arguments, `user_id`, dates, nombre d'essais, `exc_info` (erreur) |
| `queue.job.channel` | Un canal de la file | `name`, `parent_id` |
| `queue.job.function` | Paramétrage d'une méthode « jobable » | `model_id`, `method`, `channel_id`, `retry_pattern`, `related_action` |

## 5. Règles métier et calculs

- **Utilisateur d'exécution.** Le job s'exécute avec l'utilisateur et le contexte de celui qui l'a créé ; les droits d'accès restent donc ceux de cet utilisateur (point exploité par `miro_ai_assistant`).
- **Transaction propre.** Chaque job tourne dans sa propre transaction : un échec n'annule pas l'action de l'utilisateur qui l'a lancé.
- **Canal non configuré.** Un canal déclaré en base mais absent de `odoo.conf` partage la capacité de son parent (`parent_fallback` dans `queue_job/jobrunner/channels.py`).
- **Unicité.** Une `identity_key` empêche de mettre deux fois le même job en file (utilisée par l'analyse de plans).
- **Nouvelles tentatives.** Le `retry_pattern` d'une fonction de job fixe les délais entre essais.

## 6. Interfaces

| Type | Élément |
|---|---|
| Menu | « Job Queue » → « Queue » : jobs, canaux, fonctions (réservé au groupe Job Queue Manager) |
| Vues | Liste et fiche des jobs avec boutons de relance et d'annulation |
| Processus | *Jobrunner* démarré avec le serveur, qui écoute la base (notifications PostgreSQL) et envoie les jobs aux workers |
| Route HTTP | Point d'entrée interne `/queue_job/runjob`, appelé par le jobrunner pour exécuter un job |

## 7. Sécurité et droits d'accès

- Le groupe « Job Queue Manager » donne accès au menu et aux actions de relance ou d'annulation.
- Une règle multi-société limite la visibilité des jobs à la société de l'utilisateur.
- Les traitements eux-mêmes gardent les droits de l'utilisateur déclencheur, sauf si le code du job utilise volontairement `sudo()`.

## 8. Intégration avec les autres modules

**Configuration serveur** (`odoo.conf`) :
- `server_wide_modules = base,web,queue_job` : charge `queue_job` au démarrage du serveur, ce qui lance le jobrunner ;
- `workers = 4` : mode multiprocessus, nécessaire pour que des workers exécutent les jobs en parallèle des requêtes web ;
- section `[queue_job]`, `channels = root:3,root.miro_assistant:2` : au plus 3 jobs simultanés au total, dont 2 au plus pour l'assistant IA.

**Utilisation dans les modules du projet** (recherche de `with_delay`, `queue.job` ; aucun décorateur `@job`, qui n'existe plus depuis les versions récentes de `queue_job` et est remplacé par les enregistrements `queue.job.function`) :

| Module | Méthode mise en file | Canal |
|---|---|---|
| `miro_ai_assistant` | `miro.ai.assistant._answer_job` : réponse du bot | `root.miro_assistant` |
| `miro_construction_project` | `construction.dwg.files._detect_walls_job` : détection des murs | `root.construction_wall_detection` |
| `miro_construction_project` | `construction.dwg.files._detect_facades_job` : détection des façades | `root.construction_facade_detection` |
| `miro_construction_project` | `construction.dwg.files._detect_openings_job` : détection des ouvertures | `root.construction_opening_detection` |
| `miro_construction_project` | `construction.analysis._job_run_analysis` : analyse d'éléments sur plan | `root.construction_analysis` |
| `miro_construction_project` | `construction.element.draft._job_generate` : génération des éléments et phases, avec nouvelles tentatives | `root.construction_analysis` |

Les fiches de plans (`construction.dwg.files`) gardent aussi un lien vers leur job (champ Many2one vers `queue.job`) et une « related action » qui ouvre le plan concerné depuis la fiche du job.

## 9. Points techniques notables

- Choix d'une **brique standard et mature** de la communauté (statut « Mature » pour `queue_job`) plutôt qu'un mécanisme maison : threads, gestion des erreurs et reprise sont déjà éprouvés.
- **Séparation par canaux** : les réponses du bot (rapides, attendues par un utilisateur) ne patientent pas derrière les analyses de plans (lourdes), comme l'explique le commentaire de `miro_ai_assistant/data/queue_job_data.xml`.
- Le dépôt est déclaré comme un chemin à part dans `addons_path` (`custom-addons/queue`), ce qui le distingue clairement du code maison.

## 10. Limites et pistes d'amélioration

- **Canaux de `miro_construction_project` non déclarés dans `odoo.conf`** : ils retombent sur la capacité de `root`. Le commentaire de `data/queue_job_analysis_data.xml` suggère `root:4,root.construction_analysis:1`, réglage qui n'est pas appliqué dans la configuration actuelle.
- **Capacité modeste** : avec `root:3`, des analyses de plans simultanées peuvent retarder les réponses de l'assistant si elles occupent toutes les places hors du canal du bot.
- **Dépendance au mode multiprocessus** : sans `workers` et sans `server_wide_modules`, les jobs restent en attente ; `queue_job_cron_jobrunner` offre une alternative, mais en version Alpha.
- **Code tiers** : à ne pas modifier directement, et à mettre à jour depuis le dépôt OCA.
