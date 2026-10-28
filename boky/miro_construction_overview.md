# Vue d'ensemble du chantier (`miro_construction_overview`)

> Ce module ajoute à la fiche chantier un premier onglet « Vue d'ensemble » : un tableau de bord qui rassemble en un écran l'avancement, le délai, les coûts prévus et réels, les matériaux, l'activité, les incidents et une liste d'alertes. Tout est calculé automatiquement à l'ouverture de la fiche, à partir des autres modules Miro Construction, sans aucune saisie.

| Fiche | |
|---|---|
| Nom technique | `miro_construction_overview` |
| Version | 17.0.1.0.0 |
| Catégorie | Services/Project |
| Dépend de | `miro_construction_journal` (qui entraîne `miro_construction_bom`, `miro_construction_planning` et `miro_construction_project`) |
| Utilisé par | Aucun module (module « terminal ») |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Sur un chantier, les informations utiles au pilotage sont dispersées : l'avancement est dans les tâches, les heures dans les journaux de chantier, les quantités de matériaux dans les besoins et les mouvements de stock, les coûts prévus dans le chiffrage, les problèmes dans les incidents. Un conducteur de travaux ou un responsable qui ouvre la fiche d'un chantier veut savoir en quelques secondes :

- si le chantier est **en avance ou en retard** par rapport au planning ;
- si les **dépenses** restent compatibles avec le budget et l'avancement atteint ;
- si les **matériaux** sont commandés, livrés et consommés comme prévu ;
- ce qui **demande une action** aujourd'hui (journal à valider, incident grave, stock insuffisant, données manquantes...).

Le module répond à ce besoin en produisant une synthèse lisible, sans double saisie : il ne stocke rien, il agrège ce que les autres modules savent déjà.

## 2. Fonctionnalités

### 2.1 Bandeau d'indicateurs

En haut de l'onglet, six cartes résument l'état du chantier, chacune avec une valeur, une barre de progression et une ligne d'explication :

| Indicateur | Ce que voit l'utilisateur |
|---|---|
| Avancement | Avancement global en %, avec un repère « attendu à ce jour » sur la barre et l'écart en points (vert, orange ou rouge) |
| Délai | Jours restants ou jours de dépassement, dates de début et fin, « jour X / Y » |
| Budget consommé | Part du budget (ou, à défaut, du coût prévu chiffré) déjà dépensée, montant réel sur montant de référence |
| Coût final estimé | Projection du coût à terminaison si la dérive actuelle se poursuit, avec l'indice de performance des coûts |
| Main-d'œuvre | Heures réalisées sur heures prévues, effectif moyen par jour |
| Matériaux | % reçus, avec une barre empilée consommé / reçu / commandé |

Lorsque les données nécessaires manquent (dates de travaux, coûts réels), la carte l'indique explicitement (« Dates de travaux non renseignées », « Estimé dès les premiers coûts réels ») au lieu d'afficher une valeur trompeuse.

### 2.2 Points d'attention (alertes)

Une carte liste les situations qui demandent une action, classées par gravité (danger, avertissement, information) avec une icône et une couleur. Exemples : coût réel au-delà du budget, dérive des coûts, incidents graves non résolus, retard sur le planning, date de fin dépassée, tâches en retard, phases dont l'avancement est incohérent, matériaux en rupture ou en surconsommation, journaux à valider, absence de journal récent, données de chiffrage manquantes. Si aucune alerte n'est levée, un message positif s'affiche : « Aucun point d'attention : le chantier est dans les clous. »

### 2.3 Avancement par ouvrage

Un tableau présente chaque ouvrage (élément de construction de premier niveau : fondations, élévation, toiture...) avec le nombre de phases terminées sur le total, une barre d'avancement, le coût réel et une étiquette « N en retard » s'il contient des tâches en retard.

### 2.4 Coûts prévus et réels par nature

Un tableau croise le prévu et le réel pour quatre natures de coût : main-d'œuvre, matières, matériel, frais divers, avec le pourcentage consommé (signalé en rouge s'il dépasse l'avancement de plus de 10 points). En pied de tableau : le budget du marché et la marge prévue (budget moins coût prévu).

### 2.5 Approvisionnement des matériaux

Les huit matériaux principaux sont listés avec les quantités prévues, reçues et consommées et une étiquette d'état. Au-delà de huit, un lien textuel renvoie au tableau de bord complet des matériaux (bouton « Matériaux »).

### 2.6 Activité du chantier et incidents ouverts

- Les six derniers journaux de chantier : date, chef de chantier, nombre d'ouvriers, heures, coût et état (brouillon, soumis, validé).
- Les incidents non résolus, triés du plus grave au moins grave puis du plus récent au plus ancien (six affichés).

### 2.7 Fiche d'identité

Un encart récapitule le code chantier, le client, le maître d'ouvrage, l'architecte ou bureau d'études, le chef de chantier, le type de construction, la phase actuelle, le lieu, la surface et le nombre de tâches (dont en retard).

### 2.8 Accès directs

Le module ajoute à la fiche chantier :

- dans l'en-tête, des boutons **Journal du jour**, **Matériaux**, **Maquette 3D** et **Rapport matériaux** ;
- dans la zone des boutons statistiques (les compteurs cliquables en haut à droite d'une fiche Odoo), **Éléments** et **Incidents ouverts**.

Le bouton « Journal du jour » ouvre le journal existant à la date du jour, ou, s'il n'existe pas encore, un nouveau journal prérempli avec le chantier et la date.

## 3. Qui l'utilise et comment

| Profil | Usage |
|---|---|
| Conducteur de travaux / chef de projet | Ouvre la fiche chantier, lit les indicateurs et les alertes, traite les points d'attention (valider les journaux, relancer les achats...) |
| Chef de chantier | Utilise le bouton « Journal du jour » pour saisir ou reprendre la journée en cours |
| Direction | Consulte la dérive des coûts et le coût final estimé pour arbitrer |

L'onglet est le premier de la fiche : Odoo ouvre donc la fiche directement dessus. Il est en lecture seule ; pour corriger une donnée, l'utilisateur passe par le module concerné (tâches, journaux, matériaux).

## 4. Modèle de données

Le module ne crée aucun nouveau modèle. Il étend le modèle Odoo des projets, qui représente ici un chantier.

| Modèle | Rôle | Champs clés |
|---|---|---|
| `project.project` (hérité) | Chantier | `x_overview_html` (HTML calculé, non stocké : le tableau de bord), `x_incident_open_count` (nombre d'incidents non résolus), `x_element_count` (nombre d'éléments de construction) |

Les données affichées proviennent de champs définis par les autres modules :

| Donnée | Module d'origine |
|---|---|
| Avancement global, budget, coût réel total, dates de travaux, tâches en retard, notion d'ouvrage | `miro_construction_project` |
| Coût prévu de main-d'œuvre, heures prévues, phases sans cadence ou sans métré | `miro_construction_planning` |
| Coût prévu des matières, tableau de bord des matériaux | `miro_construction_bom` |
| Journaux de chantier, lignes de main-d'œuvre, coûts réels par nature, contrôle de l'avancement | `miro_construction_journal` |
| Incidents (`construction.task.incident`), éléments (`construction.element`) | modèles de la chaîne de dépendances |

## 5. Règles métier et calculs

Tous les calculs se trouvent dans `models/project_project.py`, méthode `_overview_values()` et ses sous-méthodes.

### Délai (`_overview_schedule`)

L'avancement **attendu** suppose un rythme constant entre la date de début des travaux et la date de fin prévue :

- jours écoulés = jours depuis le début, bornés entre 0 et la durée totale ;
- avancement attendu = 100 × jours écoulés / durée totale ;
- écart planning = avancement réel − avancement attendu (en points).

Exemple : chantier de 200 jours, jour 100, avancement réel 38 % : attendu 50 %, écart −12 points, ce qui déclenche une alerte « Retard sur le planning ».

### Coûts et dérive (`_overview_costs`)

Le module applique la méthode de la **valeur acquise**, classique en gestion de projet :

| Grandeur | Formule |
|---|---|
| Coût prévu | coût prévu main-d'œuvre + coût prévu matières |
| Référence | budget du marché s'il est saisi, sinon coût prévu |
| Budget consommé | 100 × coût réel / référence |
| Valeur produite (acquise) | référence × avancement global / 100 |
| Indice de performance des coûts (CPI) | valeur produite / coût réel |
| Coût final estimé | référence / CPI |

Un CPI de 0,90 signifie qu'on dépense 1 € pour produire 0,90 € d'ouvrage : à ce rythme, un chantier de 100 000 € coûtera environ 111 000 €. Le matériel et les frais divers n'ont pas de coût prévu chiffré : seule leur part réelle est affichée.

### Activité (`_overview_activity`)

- **Heures réalisées** : somme des heures des lignes de main-d'œuvre dont la ligne elle-même est validée (`state == 'validated'`), quel que soit l'état du journal qui les porte. Une heure compte donc dès que sa ligne est validée, sans attendre la validation du journal complet.
- **Nombre de journées** et **effectif moyen** : calculés sur les seuls journaux validés.
- **Journaux à valider** : journaux à l'état « soumis ».
- **Jours depuis le dernier journal** : écart entre aujourd'hui et le dernier journal validé.

### Ouvrages (`_overview_ouvrages`)

Les ouvrages sont les tâches marquées comme ouvrage ; à défaut, les tâches sans parent. Pour chacun : les phases sont ses descendants sans sous-tâche ; une phase est terminée à 100 % d'avancement ; le nombre « en retard » compte l'ouvrage et ses descendants en retard.

### Alertes (`_overview_alerts`)

| Niveau | Condition |
|---|---|
| Danger | Budget consommé > 100 % ; CPI < 0,95 ; incident de gravité critique ou haute non résolu ; écart planning < −25 points ; date de fin dépassée avec avancement < 100 % |
| Avertissement | Écart planning entre −25 et −10 points ; tâches en retard ; phases dont le contrôle d'avancement est « à vérifier » ; matériaux en stock insuffisant ; matériaux en surconsommation |
| Information | Journaux soumis à valider ; chantier « en cours » sans journal validé depuis plus de 3 jours ; besoins matériaux sans produit ; phases sans cadence ou sans métré ; budget non saisi ; dates de travaux manquantes |

Les compteurs de matériaux (rupture, surconsommation, besoins sans produit, % commandé / reçu / consommé) sont fournis par `get_material_dashboard()` du module `miro_construction_bom`.

## 6. Interfaces

| Élément | Fichier | Description |
|---|---|---|
| Héritage de la fiche chantier | `views/project_views.xml` | Ajoute les boutons d'en-tête, les deux boutons statistiques et l'onglet « Vue d'ensemble » placé avant l'onglet « Budget et avancement » |
| Gabarit QWeb `project_overview` | `views/overview_templates.xml` | Structure HTML du tableau de bord (indicateurs, alertes, six cartes) |
| Feuille de style | `static/src/scss/overview.scss` | Mise en forme en grille de cartes, barres de progression, étiquettes colorées (vert / bleu / orange / rouge) |
| Actions | `models/project_project.py` | `action_open_today_journal`, `action_open_open_incidents`, `action_open_elements` |

QWeb est le moteur de gabarits d'Odoo ; ici il est utilisé côté serveur pour produire du HTML affiché dans un champ, et non pour un rapport PDF. Aucun menu ni rapport PDF n'est ajouté par ce module ; le bouton « Rapport matériaux » appelle un rapport défini dans `miro_construction_bom`.

## 7. Sécurité et droits d'accès

Le module ne définit ni groupe, ni règle d'accès, ni fichier `ir.model.access.csv`, puisqu'il ne crée aucun modèle. L'onglet est visible par quiconque peut ouvrir la fiche chantier ; les données agrégées sont lues avec les droits de l'utilisateur courant sur les modèles sous-jacents (tâches, journaux, incidents, besoins matériaux). Dans le gabarit, toutes les valeurs sont insérées avec `t-esc`, qui échappe le texte, ce qui limite le risque d'injection malgré l'option `sanitize=False` du champ HTML.

## 8. Intégration avec les autres modules

Le module est une **couche de synthèse** placée en bout de chaîne :

- `miro_construction_project` fournit la fiche chantier, l'avancement, les coûts réels et la maquette 3D ;
- `miro_construction_planning` fournit les heures et coûts prévus de main-d'œuvre ;
- `miro_construction_bom` fournit les besoins et le tableau de bord des matériaux ;
- `miro_construction_journal` fournit les journaux, les lignes de main-d'œuvre validées et le contrôle de cohérence de l'avancement.

Il est déclaré `auto_install` : il s'installe automatiquement dès que `miro_construction_journal` est installé.

## 9. Points techniques notables

- **Tableau de bord rendu côté serveur** : plutôt qu'un composant JavaScript (OWL), le tableau de bord est un champ HTML calculé (`x_overview_html`) rendu par `ir.qweb._render`. C'est simple, sans appel réseau supplémentaire, et s'intègre dans la fiche standard.
- **Aucune donnée stockée** : tout est recalculé à chaque ouverture, donc toujours à jour, sans risque de désynchronisation.
- **Séparation calcul / présentation** : la méthode `_overview_values()` prépare un dictionnaire de valeurs (et de petites fonctions de formatage : montants, dates, pourcentages bornés pour les barres), le gabarit ne fait que les afficher.
- **Indicateurs de gestion de projet reconnus** : valeur acquise, CPI et estimation à terminaison, appliqués au chantier.
- **Robustesse face aux données incomplètes** : chaque indicateur prévoit le cas « donnée manquante » et le transforme en alerte d'information plutôt qu'en erreur ou en chiffre faux.
- **Protection des fiches non enregistrées** : le calcul est ignoré tant que le chantier n'a pas d'identifiant réel.
- **Évolution récente** : les heures réelles comptent désormais les lignes de main-d'œuvre validées individuellement, et une alerte signale les phases dont l'avancement saisi est incohérent avec la matière ou les heures consommées.

## 10. Limites et pistes d'amélioration

- **Performance** : le calcul complet est relancé à chaque ouverture de fiche ; sur un gros chantier (nombreuses tâches, journaux et besoins), l'affichage peut ralentir. Une mise en cache ou un calcul différé serait à envisager.
- **Pas d'historique** : faute de stockage, on ne peut pas tracer l'évolution du CPI ou de l'écart planning dans le temps (courbes en S).
- **Hypothèse linéaire** : l'avancement attendu suppose un rythme constant, alors qu'un chantier réel suit plutôt une courbe en S ; il pourrait s'appuyer sur le planning détaillé des phases.
- **Seuils figés dans le code** (10 et 25 points de retard, CPI 0,95, 3 jours sans journal) : ils pourraient devenir des paramètres de configuration.
- **Coûts prévus partiels** : le matériel et les frais divers ne sont pas chiffrés en prévision, ce qui fausse légèrement la référence lorsque le budget n'est pas saisi.
- **Légère hétérogénéité des bases de calcul** : les heures réalisées viennent des lignes validées de tous les journaux, tandis que l'effectif moyen et le nombre de journées ne prennent que les journaux validés.
- Pas de tests automatisés dans le module.
