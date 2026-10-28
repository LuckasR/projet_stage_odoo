# API mobile du chantier (`miro_mobile_api`)

> L'interface qui relie l'application mobile SuiviChantier à Odoo : le chef de chantier remplit son journal, valide ses lignes, signale des incidents et prend des photos depuis son téléphone, y compris sans réseau. Tout part vers Odoo dès que la connexion revient, sans doublon et sans écraser le travail du bureau.

| Fiche | |
|---|---|
| Nom technique | `miro_mobile_api` |
| Version | 17.0.1.1.0 |
| Catégorie | Services/Project |
| Dépend de | `miro_construction_journal`, `miro_construction_project` |
| Utilisé par | L'application mobile SuiviChantier (dossier `SuiviChantier/` du dépôt) ; aucun autre module Odoo |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Le chef de chantier passe sa journée sur le terrain, loin d'un ordinateur. Pour que le journal de chantier soit rempli **au moment où les choses se passent**, et non le soir de mémoire, il lui faut un outil sur son téléphone.

Deux contraintes du terrain ont guidé la conception :

- **Le réseau est mauvais ou absent** sur beaucoup de chantiers. L'application doit fonctionner hors-ligne pendant des heures, voire des jours, puis tout envoyer au retour du réseau.
- **Plusieurs personnes modifient les mêmes données.** Pendant que le chef de chantier est hors-ligne, le conducteur de travaux peut corriger le journal au bureau. Il ne faut jamais écraser silencieusement l'un ou l'autre : un conflit doit être **signalé**, et c'est l'utilisateur qui tranche.

Les décisions retenues avec l'entreprise sont les suivantes :

- périmètre limité au terrain (journal, photos, avancement, incidents) ;
- l'application valide des lignes mais **jamais le journal entier**, qui reste au conducteur de travaux dans Odoo ;
- les conflits sont toujours signalés à l'utilisateur.

## 2. Fonctionnalités

### Connexion par appareil
Le chef de chantier se connecte une fois avec son identifiant et son mot de passe Odoo. L'API lui remet un **jeton** propre à son téléphone :

- le jeton n'expire pas, pour supporter de longues périodes hors-ligne ;
- Odoo n'en garde que l'empreinte (hachage SHA-256), jamais le jeton en clair ;
- un téléphone perdu se révoque depuis Odoo, ce qui le déconnecte immédiatement ;
- seuls les utilisateurs internes (pas les comptes portail) peuvent se connecter.

### Téléchargement des données pour travailler hors-ligne
En un appel, le téléphone reçoit tout ce dont il a besoin :

- les chantiers en cours de l'utilisateur (ceux dont il est chef de chantier ou chef de projet) ;
- leurs phases avec le métré, l'unité, le réalisé, l'avancement, l'équipe et les besoins matière ;
- les ouvriers, le matériel, les journaux des 30 derniers jours et les incidents non résolus ;
- les listes de valeurs avec leurs libellés (météo, états, gravité).

### Envoi des saisies faites hors-ligne
Le téléphone envoie une **file d'opérations**, chacune identifiée par un `uuid` qu'il a lui-même généré :

| Opération | Ce qu'elle fait |
|---|---|
| `journal.header` | Crée ou met à jour l'en-tête du journal du jour (météo, heures d'arrêt, observations, frais du chantier) ; peut aussi le soumettre. |
| `work.upsert` | Crée ou met à jour un travail et ses lignes (ouvriers, matières, matériel, dépenses) ; peut valider le travail entier ou certaines lignes. |
| `work.delete` | Supprime un travail encore en brouillon. |
| `incident.create` | Signale un incident sur une phase. |
| `incident.update` | Change l'état, la description ou la gravité d'un incident. |

Les opérations sont traitées une par une : une opération refusée n'empêche pas les suivantes, et la réponse donne un résultat par opération (`ok`, `conflict` ou `error`).

### Validation des lignes depuis le téléphone
Chaque ligne envoyée peut porter une demande de validation. L'API applique d'abord les modifications, puis valide les lignes demandées, avec leurs effets immédiats dans Odoo : sortie de stock, avancement, coût réel. Une ligne déjà validée n'est plus jamais modifiée.

### Détection et signalement des conflits
L'en-tête du journal et chaque travail ont un **numéro de version**. Le téléphone renvoie la version sur laquelle il a travaillé. Si elle a changé entre-temps, l'opération est refusée comme conflit, avec la version d'Odoo pour que l'utilisateur puisse comparer :

| Raison | Situation |
|---|---|
| `modified` | La donnée a été modifiée par quelqu'un d'autre depuis la dernière synchronisation. |
| `locked` | Le travail a été validé, ou le journal entier validé par le conducteur. |
| `exists` | Un en-tête de journal a déjà été rempli par quelqu'un d'autre. |
| `deleted` | La donnée a été supprimée au bureau. |

Parce que les versions sont **par travail**, deux personnes peuvent remplir des lignes différentes du même journal sans se gêner.

### Photos
Les photos prises sur le téléphone sont envoyées une par une et rattachées au journal ou à l'incident. Elles sont téléchargeables ensuite pour être consultées hors-ligne. L'envoi aussi est protégé contre les doublons.

## 3. Qui l'utilise et comment

| Rôle | Ce qu'il fait |
|---|---|
| Chef de chantier | Utilise l'application SuiviChantier : remplit le journal, valide ses lignes, signale des incidents, prend des photos. |
| Conducteur de travaux | Dans Odoo : voit arriver les lignes, valide les journaux, révoque un téléphone perdu (menu Téléphones connectés). |
| Application SuiviChantier | Seul client de l'API. |

Parcours type :

1. Au bureau, avec du Wi-Fi, le chef de chantier ouvre l'application : elle télécharge ses chantiers.
2. Sur le chantier, sans réseau, il saisit ses travaux et valide la ligne du coulage. Tout reste enregistré sur le téléphone, et la ligne affiche « validation en attente ».
3. Le soir, le réseau revient : l'application envoie la file d'opérations, puis les photos, puis recharge les données d'Odoo.
4. Si le conducteur de travaux avait modifié le même travail entre-temps, l'application affiche un bandeau « Conflit avec Odoo » avec deux choix : garder la version d'Odoo ou envoyer la sienne.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `miro.mobile.device` | Un téléphone connecté | `name`, `user_id`, `token_hash` (empreinte du jeton, réservée aux administrateurs), `last_seen`, `active` |
| `miro.mobile.op` | Une opération déjà appliquée (pour l'idempotence) | `uuid` (unique), `device_id`, `kind`, `result` (réponse JSON mémorisée) |
| `miro.mobile.api` | Modèle abstrait, sans table : toute la logique de lecture et d'écriture de l'API | — |

Le module ajoute aussi des champs aux modèles du journal (`models/site_journal.py`) :

| Modèle étendu | Champ ajouté | Rôle |
|---|---|---|
| `miro.site.journal` | `mobile_version` | Version de l'en-tête (météo, observations, frais du chantier, état) |
| `miro.site.journal.work` | `mobile_uuid`, `mobile_version` | Identifiant donné par le téléphone, et version du travail |
| Lignes du journal | `mobile_uuid` | Identifiant donné par le téléphone |

Une ligne saisie au bureau n'a pas d'identifiant mobile : l'API l'expose sous la forme `srv-<id>`.

## 5. Règles métier et calculs

**Idempotence** (`models/mobile_api.py`, méthode `_push`) : avant d'appliquer une opération, l'API cherche son `uuid` dans `miro.mobile.op`. Si elle a déjà été appliquée, par exemple parce que la réponse s'est perdue dans une coupure réseau, elle renvoie le résultat mémorisé sans rien refaire. Seules les opérations réussies sont mémorisées : un conflit ou une erreur peut être renvoyé après correction.

**Isolation des opérations** : chaque opération s'exécute dans un point de sauvegarde (*savepoint*) de la base. En cas d'erreur, seule cette opération est annulée.

**Versions** (`models/site_journal.py`) : le compteur augmente à chaque modification, où qu'elle soit faite :
- une modification de l'en-tête ou d'une ligne de frais du chantier fait monter la version du journal ;
- une modification du travail ou de l'une de ses lignes fait monter la version du travail ;
- l'incrément se fait par une requête SQL directe, pour ne pas repasser par les verrous du journal ni déclencher de recalculs.

**Règles de conflit** :
- *Travail* : sans version de base, un identifiant déjà connu ne peut venir que du même téléphone (un envoi dont la réponse s'est perdue), donc ce n'est pas un conflit. Un travail validé renvoie `locked`.
- *En-tête* : un journal en version 1 a été créé par un travail mais son en-tête n'a jamais été saisi, donc ce n'est pas un conflit.

**Alignement des lignes** (`_sync_lines`) : les lignes d'Odoo sont alignées sur celles du téléphone, reconnues par leur identifiant. Une ligne validée n'est jamais touchée ; une ligne en brouillon absente du téléphone est supprimée ; une ligne de matière à 0 est considérée comme absente.

**Périmètre** : l'utilisateur n'agit que sur les chantiers dont il est chef de chantier ou chef de projet, et dont le statut n'est ni « terminé » ni « annulé ». Une phase doit appartenir au chantier, et un besoin matière à la phase.

**Observations** : elles sont converties du texte brut en HTML à l'envoi (`plaintext2html`), et inversement au téléchargement.

## 6. Interfaces

Routes HTTP (`controllers/main.py`), toutes sous `/api/mobile/v1`, au format JSON :

| Route | Méthode | Rôle |
|---|---|---|
| `/login` | POST | Connexion, renvoie le jeton de l'appareil |
| `/logout` | POST | Révoque l'appareil |
| `/sync/pull` | GET | Instantané des données de l'utilisateur |
| `/sync/push` | POST | File d'opérations, renvoie un résultat par opération |
| `/photos` | POST | Envoi d'une photo (formulaire multipart) |
| `/photos/<id>` | GET | Téléchargement d'une photo |

Les erreurs sont renvoyées en JSON avec un code HTTP adapté :

| Code HTTP | Signification |
|---|---|
| 401 | Jeton invalide ou mot de passe incorrect |
| 403 | Accès refusé |
| 422 | Règle métier non respectée, avec le message d'Odoo |

Dans Odoo, le menu **Construction > Configuration > Téléphones connectés** liste les appareils et leur dernière synchronisation, avec un bouton « Révoquer ».

## 7. Sécurité et droits d'accès

- **Pas de session ni de cookie** : chaque requête porte le jeton dans l'en-tête `Authorization: Bearer`. Les routes sont donc déclarées `auth='none'`, et l'authentification est faite par le décorateur `mobile_auth`.
- **Droits Odoo appliqués** : une fois le jeton reconnu, la requête s'exécute **sous l'utilisateur du téléphone** (`request.update_env`). Ses droits Odoo s'appliquent comme au bureau, en plus du filtre « mes chantiers ».
- **Jeton protégé** : l'empreinte du jeton n'est lisible que par les administrateurs, et le jeton en clair n'est transmis qu'une fois, à la connexion. La protection contre les essais de mot de passe répétés est celle d'Odoo.
- **CORS** : il est ouvert (`cors='*'`), ce qui ne pose pas de risque ici puisque l'accès dépend du jeton et non d'un cookie.
- **Droits sur les modèles** : la gestion des appareils est réservée au groupe Gestionnaire de projet, et le journal des opérations aux administrateurs.
- **Validation du journal** : l'API ne propose aucune opération pour valider le journal entier, qui reste réservé au conducteur de travaux.

## 8. Intégration avec les autres modules

- **`miro_construction_journal`** : l'API lit et écrit les journaux, travaux et lignes, et passe par leurs méthodes métier (`action_validate_line`, `action_submit`). Elle respecte donc les mêmes verrous et produit les mêmes effets (stock, avancement, coût) que l'interface d'Odoo.
- **`miro_construction_project`** : fournit les chantiers, les phases et les incidents (`construction.task.incident`).
- **`miro_construction_bom`**, **`miro_hr_paie`** : indirectement, par le journal (besoins matière, coût horaire des ouvriers, heures par jour).
- **Application SuiviChantier** (dossier `SuiviChantier/`, React 19 + Vite + Capacitor pour Android) :
  - elle stocke ses données dans IndexedDB : un instantané d'Odoo, et les saisies locales par en-tête, par travail et par incident ;
  - elle synchronise toute seule au retour du réseau, en trois temps : saisies, puis photos, puis rechargement ;
  - elle affiche les conflits ligne par ligne avec leurs choix de résolution ;
  - son interface est conçue pour le pouce : gros boutons « − / + », validation par une coche, reprise du journal de la veille.

## 9. Points techniques notables

- **Une architecture « hors-ligne d'abord »** : le téléphone est la source de vérité pendant la saisie, et Odoo celle de vérité après synchronisation. Toute la difficulté est de réconcilier les deux sans perte, ce qui repose sur trois mécanismes :
  - les **uuid générés par le client** (idempotence et identification des lignes) ;
  - le **verrouillage optimiste** par numéro de version (détection des conflits) ;
  - les **savepoints** (une opération en échec n'annule pas les autres).
- **Un découpage fin des versions** : une première version envoyait le journal en bloc. Avec la validation ligne par ligne, elle a été remplacée par un en-tête et des travaux versionnés séparément, ce qui réduit fortement les conflits entre utilisateurs.
- **Aucune règle métier dupliquée** : l'API ne recalcule ni coût ni avancement. Elle appelle les méthodes du journal, si bien qu'une règle modifiée dans le journal s'applique aussitôt au mobile.
- **Tests de bout en bout** : les scénarios ont été vérifiés dans un navigateur piloté par puppeteer contre une vraie base Odoo :
  - saisie, puis validation d'une ligne et d'un travail ;
  - deuxième ligne sur la même phase ;
  - soumission puis ajout d'une ligne ;
  - conflit résolu ;
  - saisie conservée après rechargement sans réseau.

## 10. Limites et pistes d'amélioration

- Le téléchargement est un **instantané complet** à chaque synchronisation (environ 2 s pour 1 364 phases). Pour de gros chantiers, il faudrait un téléchargement incrémental, limité à ce qui a changé depuis la dernière fois.
- La table `miro.mobile.op` grossit sans limite : prévoir une tâche planifiée qui purge les opérations de plus de quelques semaines.
- La connexion suppose une seule base de données sélectionnée par `dbfilter`, puisque les routes n'ont pas de session. Un déploiement multi-bases demanderait de passer le nom de la base.
- En production, Odoo doit être servi en HTTPS, et l'application Android ne doit plus autoriser le trafic HTTP non chiffré.
- Le jeton n'expire jamais : un délai d'expiration long (par exemple 90 jours sans synchronisation) renforcerait la sécurité sans gêner le hors-ligne.
