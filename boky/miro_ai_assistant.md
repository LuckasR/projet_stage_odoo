# Miro Assistant, l'assistant IA des chantiers (`miro_ai_assistant`)

> Un robot de discussion intégré à la messagerie d'Odoo (Discuss) et une bulle flottante sur tous les écrans : on lui pose une question en français sur un chantier (« Où en est la Villa Ivato ? ») et il répond à partir des données réelles de la base, en lecture seule et avec les droits de la personne qui pose la question.

| Fiche | |
|---|---|
| Nom technique | `miro_ai_assistant` |
| Version | 17.0.1.0.0 |
| Catégorie | Productivity/Discuss |
| Dépend de | `mail`, `queue_job`, `miro_construction_project` |
| Utilisé par | Aucun autre module (module « feuille ») |
| Auteur / licence | MIRO K.E. / LGPL-3 |

## 1. Le besoin métier

Dans une entreprise de bâtiment, la direction, les conducteurs de travaux et les chefs de chantier ont souvent besoin d'une information ponctuelle : le pourcentage d'avancement d'un chantier, les tâches en retard, l'état des approvisionnements en matériaux, ce qui démarre la semaine prochaine. Ces chiffres existent dans Odoo, mais ils sont répartis entre plusieurs écrans et plusieurs modules (projet, éléments de construction, besoins en matériaux, planning).

Le module répond à ce besoin par une interface conversationnelle : l'utilisateur pose sa question en langage naturel, et un modèle de langage (LLM, « Large Language Model », programme d'IA capable de comprendre et de rédiger du texte) va chercher lui-même les chiffres dans la base puis formule une réponse courte. La règle de fond, inscrite dans les consignes données au modèle, est qu'il **ne devine jamais un chiffre** : tout vient des outils qui lisent la base.

## 2. Fonctionnalités

### Discuter avec le bot dans Discuss
Un contact « Miro Assistant » existe dans la messagerie. On peut lui écrire en conversation privée, comme à un collègue. Dans un canal de groupe, il suffit de le mentionner (`@Miro Assistant`) pour qu'il réponde. Pendant le calcul, l'indicateur « en train d'écrire… » s'affiche.

### Bulle flottante
Une bulle en bas à droite de l'écran (« Miro Assistant — Où en est mon chantier ? ») ouvre directement la conversation avec le bot dans une petite fenêtre de discussion. C'est la même conversation que dans Discuss, donc le même historique. La bulle se décale à gauche des fenêtres de discussion déjà ouvertes, disparaît quand la fenêtre du bot est affichée, et se masque sur téléphone si une fenêtre de discussion occupe l'écran.

### Questions sur les chantiers
Le bot sait répondre, grâce à sept outils de lecture, aux questions suivantes :

| Outil | Ce qu'il renvoie au modèle |
|---|---|
| `find_projects` | Recherche d'un chantier par nom, client, ville ou maître d'ouvrage ; liste les chantiers si la recherche est vide |
| `get_project_progress` | Avancement global, statut, dates, décompte des tâches (terminées, en cours, non commencées, en retard), avancement par ouvrage, budget et coûts prévus / réels |
| `get_progress_by_level` | Avancement de la structure par niveau (fondations, RDC, R+1…) et par type d'élément (poteau, poutre, dalle…) |
| `get_late_tasks` | Tâches dont l'échéance est dépassée, avec le nombre de jours de retard |
| `search_tasks` | Recherche de tâches ou de phases par nom ou par élément (« coulage P3 », « dalle R+1 ») |
| `get_material_status` | Besoins en matériaux : coût prévu et consommé, pourcentages commandé / reçu / consommé, ruptures, dépassements, principaux matériaux |
| `get_planning_summary` | Planning proposé : dates planifiées, durée en jours ouvrés, coût de main-d'œuvre, phases en cours et phases qui démarrent dans les 7 jours |

Le modèle choisit lui-même quel outil appeler, éventuellement plusieurs à la suite (par exemple `find_projects` pour retrouver l'identifiant du chantier, puis `get_late_tasks`).

### Réponses mises en forme
Le modèle répond en Markdown simple (gras, listes). Le module convertit ce texte en HTML sûr avant de le publier dans la conversation, au nom du bot.

### Messages d'erreur compréhensibles
Si le fournisseur d'IA refuse la clé, est injoignable, limite le débit ou ne trouve pas le modèle, l'utilisateur reçoit dans la conversation une phrase explicite (« La clé API est refusée… », « Trop de questions en même temps… ») plutôt qu'une erreur technique. Si le module n'est pas encore configuré, le bot le dit.

### Paramétrage du fournisseur d'IA
Un écran dans **Paramètres → Miro Assistant** permet de choisir le fournisseur, le modèle et quelques réglages, sans toucher au code.

## 3. Qui l'utilise et comment

| Profil | Usage |
|---|---|
| Direction, conducteurs de travaux, chefs de chantier | Posent leurs questions dans Discuss ou via la bulle. Chacun ne reçoit que ce qu'il pourrait voir lui-même dans Odoo. |
| Administrateur (groupe Paramètres) | Saisit l'URL de l'API, la clé, le modèle et les options dans Paramètres → Miro Assistant. |
| Administrateur technique | Configure les canaux de tâches de fond dans `odoo.conf` et surveille les jobs dans le menu Job Queue de `queue_job`. |

Parcours type : l'utilisateur clique sur la bulle, tape « Quelles tâches sont en retard sur la Villa Ivato ? ». Le message part immédiatement ; le bot affiche « en train d'écrire… » ; quelques secondes plus tard, la réponse arrive, avec les chiffres clés en gras et deux à cinq points utiles. Le bot ne peut rien modifier : si on lui demande une modification, il explique où la faire dans Odoo.

## 4. Modèle de données

Le module ne crée aucune table métier : ses deux modèles sont abstraits (`AbstractModel`, c'est-à-dire des classes de logique sans table en base).

| Modèle | Rôle | Champs clés |
|---|---|---|
| `miro.ai.assistant` (abstrait) | Conversation avec le modèle de langage : historique, appels HTTP, boucle d'outils, publication de la réponse | aucun champ |
| `miro.ai.assistant.tools` (abstrait) | Les sept outils de lecture de la base | aucun champ |
| `discuss.channel` (hérité) | Détecte les messages adressés au bot | aucun champ ajouté |
| `res.config.settings` (hérité) | Écran de paramétrage | `miro_ai_api_url`, `miro_ai_api_key`, `miro_ai_model`, `miro_ai_reasoning_effort`, `miro_ai_max_tokens`, `miro_ai_extra_params` (tous stockés dans `ir.config_parameter`) |

Données créées à l'installation (`data/assistant_data.xml`, `data/queue_job_data.xml`) :

| Enregistrement | Rôle |
|---|---|
| Contact `partner_miro_assistant` | Identité du bot (nom, avatar) dans la messagerie |
| Utilisateur `user_miro_assistant` (archivé) | Nécessaire pour que Discuss ouvre une conversation avec le contact ; archivé, il ne peut pas se connecter (même principe qu'OdooBot) |
| Canal de jobs `miro_assistant` | File d'attente dédiée aux réponses du bot |
| Fonction de job `_answer_job` | Rattache la méthode de réponse à ce canal |

## 5. Règles métier et calculs

**Déclenchement** (`models/discuss_channel.py`). Après chaque message publié dans une conversation, le module vérifie qu'il s'agit d'un commentaire, que l'auteur n'est pas le bot lui-même, et que la conversation est soit un échange privé avec le bot, soit un canal où le bot est mentionné. Si oui, la réponse est planifiée.

**Traitement en tâche de fond** (`models/assistant.py`, `_schedule_answer`). Le bot passe en « en train d'écrire », puis la méthode `_answer_job` est mise en file via `with_delay` (`queue_job`) avec au plus une nouvelle tentative. L'envoi du message par l'utilisateur n'est donc jamais bloqué par l'appel à l'IA, qui peut prendre plusieurs secondes.

**Historique** (`_history`). Les 20 derniers commentaires de la conversation sont relus et convertis au format « Chat Completions » (rôles `user` / `assistant`). Dans un canal de groupe, le nom de l'auteur est préfixé pour que le modèle sache qui parle. Deux messages consécutifs du même rôle sont fusionnés.

**Consigne système** (`SYSTEM_PROMPT`). Le modèle reçoit une consigne en français : il est l'assistant de Miro Construction à Madagascar, il doit interroger les outils avant de répondre, ne jamais inventer un pourcentage, une date ou un identifiant de chantier, demander une précision si plusieurs chantiers correspondent, répondre brièvement, sans tableaux, dates au format JJ/MM/AAAA. La date du jour et le nom de l'utilisateur sont ajoutés.

**Boucle d'outils** (`_answer`). Tant que le modèle demande un outil, l'outil est exécuté et son résultat (JSON compact, pour économiser des jetons) lui est renvoyé, dans la limite de 8 allers-retours. Au-delà, le bot demande à l'utilisateur de préciser sa question. Si le modèle produit un appel d'outil mal formé (erreur 400), un nouvel essai est fait une fois.

**Isolation des outils** (`_run_tool`). Seuls les noms d'outils déclarés sont acceptés. Chaque outil s'exécute dans un *savepoint* (point de sauvegarde de transaction) : une erreur SQL dans un outil n'annule pas tout le job. L'erreur est renvoyée au modèle sous forme `{"erreur": ...}` pour qu'il puisse s'adapter.

**Limite de débit** (`_chat`, `_retry_after`). En cas de réponse HTTP 429 (trop de requêtes), le module lit le délai demandé par le fournisseur (en-tête `Retry-After` ou texte « try again in 7.26s ») et réessaie jusqu'à 3 fois si l'attente ne dépasse pas 30 secondes. Ce cas est fréquent avec l'offre gratuite de Groq.

**Calculs dans les outils** (`models/assistant_tools.py`) :
- une tâche est « terminée » si son état est *Terminée* ou si son avancement atteint 100 % ;
- `find_projects` exige que chaque mot de la recherche apparaisse dans l'un des champs (nom, client, ville, maître d'ouvrage), puis, à défaut de résultat, se contente d'un seul mot (tolérance aux fautes) ;
- `get_progress_by_level` regroupe les phases par niveau et par type d'élément, calcule l'avancement moyen et trie les niveaux par altitude ;
- les listes sont plafonnées (30 ouvrages, 25 tâches en retard, 20 résultats de recherche, 20 matériaux, 8 phases) pour limiter la taille des réponses envoyées au modèle ;
- les outils qui dépendent d'autres modules (éléments de construction, matériaux, planning) vérifient d'abord que les champs ou méthodes existent, et renvoient sinon un message clair au modèle.

**Configuration par défaut** (`_init_default_params`). À l'installation : fournisseur Groq, modèle `openai/gpt-oss-20b`, réflexion « faible », 4000 jetons maximum par réponse, sans écraser un réglage existant. La fonction nettoie aussi les restes d'une première version du module qui utilisait l'API d'Anthropic (Claude) : ancien paramètre supprimé, ancienne clé effacée.

## 6. Interfaces

| Type | Élément |
|---|---|
| Menu / vue | Section « Miro Assistant » dans Paramètres (`views/res_config_settings_views.xml`), visible uniquement du groupe Administration / Paramètres. La clé est affichée masquée (`password="True"`). |
| Messagerie | Contact « Miro Assistant » dans Discuss, conversation privée ou mention dans un canal |
| Composant JS | `MiroAssistantBubble` (`static/src/bubble/assistant_bubble.js`), composant OWL enregistré dans `main_components`, donc présent sur tout le back-office. Il appelle `get_bot_partner_id` puis ouvre la conversation avec le service `mail.thread`. |
| Appel sortant | `POST {url}/chat/completions` vers le fournisseur d'IA, délai maximal 120 s |
| Tâche de fond | Job `_answer_job` sur le canal `root.miro_assistant` |
| Route HTTP | Aucune |
| Tâche planifiée (cron) | Aucune |

## 7. Sécurité et droits d'accès

- **Lecture seule.** Aucun outil n'écrit dans la base. La consigne interdit au modèle de prétendre modifier quoi que ce soit.
- **Droits de l'utilisateur.** Les outils n'utilisent pas `sudo()` (mode superutilisateur d'Odoo). Le job est exécuté au nom de l'utilisateur qui a posé la question, et le chantier est recherché par `search()` plutôt que `browse()` pour que les règles d'accès s'appliquent : un chef de chantier ne reçoit que les chantiers qu'il verrait dans Odoo.
- **Opérations techniques en `sudo`.** La lecture de l'historique de la conversation, l'indicateur de frappe et la publication de la réponse au nom du bot se font en `sudo`, car l'utilisateur n'a pas le droit d'écrire au nom d'un autre contact.
- **Bot sans connexion.** L'utilisateur technique du bot est archivé : il ne peut pas se connecter.
- **Clé d'API.** Elle est stockée dans les paramètres système (`ir.config_parameter`, clé `miro_ai_assistant.api_key`), saisie par un administrateur dans Paramètres → Miro Assistant. Une clé peut ne pas être nécessaire pour un modèle local (Ollama sur `localhost`).
- **HTML sûr.** Le texte du modèle est échappé avant conversion Markdown → HTML, ce qui empêche l'injection de code HTML ou JavaScript dans la conversation.
- **Pas de fichier `ir.model.access.csv`.** Les modèles étant abstraits, aucun droit d'accès n'est à déclarer.
- **Confidentialité.** Les questions et les données lues par les outils sont envoyées au fournisseur d'IA externe choisi. C'est un point à considérer selon le fournisseur (voir section 10).

## 8. Intégration avec les autres modules

| Module | Nature du lien |
|---|---|
| `mail` | Messagerie Discuss, contact du bot, publication des messages, indicateur de frappe |
| `queue_job` (OCA) | Exécution des réponses en tâche de fond, sur un canal dédié |
| `miro_construction_project` | Champs du projet et des tâches (`x_avancement_global`, `x_status`, `x_est_en_retard`, dates prévues, coûts) et éléments de construction (`construction_element_id`, niveaux, types) |
| `miro_construction_bom` (facultatif) | Méthode `get_material_dashboard` utilisée par `get_material_status` |
| `miro_construction_planning` (facultatif) | Champs `miro_planned_start/end`, `miro_crew_id`, coût de main-d'œuvre, utilisés par `get_planning_summary` |

Les deux derniers modules ne sont pas déclarés en dépendance : les outils testent leur présence à l'exécution. Le module reste donc installable sans eux, avec des outils qui répondent « module non installé ».

## 9. Points techniques notables

- **« Tool calling » (appel de fonctions).** C'est l'architecture centrale : plutôt que de donner toute la base au modèle, on lui décrit des fonctions (nom, description, schéma JSON des paramètres) et il décide lesquelles appeler. Cela limite les « hallucinations » (chiffres inventés) et le volume de données envoyées.
- **Fournisseur interchangeable.** Le module parle le format « Chat Completions » d'OpenAI, devenu un standard de fait : Groq, OpenAI, Mistral, OpenRouter ou un modèle local Ollama conviennent en changeant seulement l'URL, la clé et le nom du modèle. L'historique du code montre d'ailleurs un passage de l'API Anthropic (Claude) à ce format générique.
- **Asynchronisme avec `queue_job`.** L'appel à l'IA est lent et dépend d'un service externe ; il est sorti de la requête de l'utilisateur. Un canal dédié évite que les réponses du bot attendent derrière les analyses de plans, plus longues.
- **Robustesse.** Toute erreur aboutit à une réponse dans la conversation ; erreurs HTTP traduites en messages clairs ; nouvelle tentative sur limite de débit et sur appel d'outil mal formé ; plafond d'allers-retours ; savepoint par outil.
- **Économie de jetons.** JSON compact, listes plafonnées, historique limité à 20 messages, réponses courtes demandées par la consigne.
- **Réutilisation de l'interface native.** La bulle ne réimplémente pas de fenêtre de chat : elle ouvre la fenêtre de discussion standard d'Odoo, ce qui garde un seul historique.
- **Intégration MCP.** Le message de commit qui a créé le module mentionne une « Intégration MCP » (Model Context Protocol, protocole d'exposition d'outils aux IA). Le code de ce module ne contient toutefois aucune implémentation MCP : les outils sont appelés directement par le module via l'API Chat Completions.

## 10. Limites et pistes d'amélioration

- **Données envoyées à un tiers.** Les chiffres des chantiers partent chez le fournisseur d'IA. Un modèle local (Ollama) supprimerait ce point, au prix de ressources serveur.
- **Clé en clair dans les paramètres système.** Elle est masquée à l'écran mais lisible par les administrateurs et en base.
- **Attente bloquante.** En cas de limite de débit, le worker attend avec `time.sleep` (jusqu'à 30 s par essai) et occupe une place du canal pendant ce temps.
- **Pas de réponse en continu (streaming).** La réponse s'affiche d'un bloc à la fin.
- **Liste d'outils fermée et en lecture seule.** Ajouter une question (incidents, journal de chantier, coûts détaillés) demande d'écrire un nouvel outil en Python.
- **Pas de tests automatisés** dans le module.
- **Dépendances implicites** aux champs de `miro_construction_planning` et `miro_construction_bom`, vérifiées à l'exécution mais non déclarées.
- **Pas de suivi de consommation.** Les jetons utilisés sont seulement écrits dans le journal du serveur ; un tableau de suivi des coûts d'IA serait utile.
- **Pistes :** exposer ces mêmes outils via un vrai serveur MCP pour d'autres clients IA, ajouter des actions d'écriture encadrées (avec confirmation de l'utilisateur), mémoriser les préférences par utilisateur.
