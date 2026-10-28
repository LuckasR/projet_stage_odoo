# Journal de chantier (`miro_construction_journal`)

> Le rapport journalier du chef de chantier : qui a travaillé sur quelle phase, ce qui a été réalisé, les matières, le matériel et les dépenses de la journée. Chaque ligne validée met aussitôt à jour le stock, l'avancement des phases et le coût réel du chantier, sans aucune saisie de montant.

| Fiche | |
|---|---|
| Nom technique | `miro_construction_journal` |
| Version | 17.0.1.3.0 |
| Catégorie | Services/Project |
| Dépend de | `miro_construction_bom`, `miro_construction_planning` |
| Utilisé par | `miro_construction_overview`, `miro_mobile_api` |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Sur un chantier, le coût réel et l'avancement sont les deux chiffres que la direction suit en permanence. Avant ce module, ils étaient saisis à la main : un pourcentage d'avancement tapé sur la tâche, un coût réel recopié depuis des tableurs. Ces chiffres étaient approximatifs, en retard, et impossibles à justifier.

Le journal de chantier remplace ces saisies par des **faits de terrain** :

- le chef de chantier déclare chaque jour ce qui s'est passé : les ouvriers présents et leurs heures, les quantités réalisées par phase (par exemple 12 m³ de béton coulés), les matières consommées, les engins utilisés et les petites dépenses ;
- Odoo **calcule** le reste : le coût de la main-d'œuvre (heures × coût horaire chargé de l'ouvrier), le coût des matières (sortie de stock au prix du jour), le coût du matériel (heures × taux horaire de l'engin) et l'avancement de chaque phase (quantité réalisée cumulée ÷ métré prévu).

Le coût réel et l'avancement ne sont donc plus saisis. Ils découlent des journaux, et chaque chiffre peut être retracé jusqu'à la ligne qui l'a produit.

## 2. Fonctionnalités

### Un journal par chantier et par jour
Chaque journal regroupe la journée d'un chantier : la date, le chef de chantier, la météo (ensoleillé, nuageux, pluie, intempérie avec arrêt), les heures d'arrêt (intempéries, attente de livraison, panne) et un champ libre pour les incidents et observations. Odoo interdit d'avoir deux journaux pour le même chantier à la même date.

### Les travaux du jour
Un journal contient des **travaux**, chacun rattaché à une phase du chantier (par exemple « B14 - Coffrage »). Un travail porte :

- **le réalisé** : une quantité dans l'unité de la phase (m³, kg, m²…) si la phase a un métré, ou un état (pas commencé, en cours, fini) si elle n'en a pas ;
- **la main-d'œuvre** : les ouvriers et leurs heures ;
- **la consommation** : les matières utilisées, une ligne par besoin matière de la phase ;
- **le matériel** : les engins et leurs heures d'utilisation ;
- **les dépenses** : achats sur place, transport…

Une même phase peut avoir **plusieurs travaux dans la journée**. Par exemple, la ligne du matin est validée à midi et l'après-midi fait l'objet d'une nouvelle ligne.

### Pré-remplissage de la consommation
Quand on choisit une phase, Odoo crée une ligne de consommation pour chaque besoin matière de la phase, issu de sa nomenclature. Quand on saisit la quantité réalisée, il propose la **consommation théorique** : besoin de la phase × quantité réalisée ÷ métré. Le chef de chantier n'a plus qu'à corriger avec le réel.

### Frais du chantier
Le matériel et les dépenses qui ne concernent pas une phase précise (gardiennage, engin au service de tout le chantier) se saisissent à part, au niveau du journal.

### Validation ligne par ligne
C'est la règle centrale du module (version 17.0.1.3.0) :

- le chef de chantier **valide les lignes au fil de la journée** : soit un travail entier (qui valide aussi toutes ses lignes), soit une seule ligne (un ouvrier, une matière, un engin, une dépense) ;
- une ligne validée est **figée** : elle ne peut plus être modifiée ni supprimée, et on ne peut plus rien ajouter dans un travail validé ;
- la validation a des **effets immédiats** : les matières sortent du stock, les heures et les dépenses comptent dans le coût réel, et le réalisé du travail compte dans l'avancement de la phase ;
- on peut **ajouter de nouvelles lignes** tant que le journal entier n'est pas validé.

### Soumission et validation du journal
- **Soumettre** prévient le conducteur de travaux que la journée est finie. Cela ne verrouille rien : on peut encore ajouter et valider des lignes.
- **Valider le journal** est réservé au conducteur de travaux. Toutes les lignes restantes sont validées (et leurs matières sortent du stock), puis le journal est figé définitivement.

### Remise en brouillon d'une ligne
Seul le conducteur de travaux peut remettre une ligne validée en brouillon, et seulement tant que le journal n'est pas validé. Les matières déjà sorties **reviennent en stock** par un mouvement de retour, et l'avancement comme le coût réel se recalculent.

### Correction d'une erreur
Une quantité déclarée en trop se corrige par une **quantité négative** dans un journal suivant, avec un motif obligatoire (par exemple « 2 m³ déclarés en trop hier »). Odoo refuse une correction qui ramènerait le réalisé cumulé sous zéro.

### Reprendre les travaux du dernier journal
Un bouton recopie les travaux du journal précédent du chantier : mêmes phases, mêmes ouvriers avec leurs heures, même matériel. Les phases déjà terminées sont ignorées. Le chef de chantier n'a plus qu'à saisir les quantités du jour.

### Contrôles de cohérence de l'avancement
Pour chaque phase, Odoo compare l'avancement déclaré avec trois indicateurs et affiche une alerte quand l'écart dépasse 25 points :

- **la matière utilisée** : un avancement de 80 % avec seulement 20 % de la matière consommée signale un réalisé déclaré trop haut ou une consommation oubliée ;
- **les heures passées** par rapport aux heures prévues : l'équipe avance moins vite que prévu ;
- **les phases précédentes** non terminées, ainsi qu'un réalisé cumulé supérieur au métré.

Ces contrôles s'affichent sur la phase et, avant même la validation, sur chaque travail du journal (« ce que donnerait la phase avec ce travail »).

### Matériel de chantier
Un référentiel des engins et du matériel (bétonnière, grue, vibreur…) : chaque engin a une origine (en propre ou loué) et un **coût horaire** (amortissement et carburant pour un engin à soi, prix de location pour un engin loué).

### Coûts réels sur la phase et le chantier
La phase et le chantier affichent le coût réel ventilé en main-d'œuvre, matières, matériel et frais divers. Une tâche mère cumule ses sous-tâches, et le chantier ajoute ses frais sans phase.

## 3. Qui l'utilise et comment

| Rôle | Ce qu'il fait |
|---|---|
| Chef de chantier | Crée le journal du jour (dans Odoo ou depuis l'application mobile SuiviChantier), saisit les travaux, valide les lignes terminées, soumet la journée. |
| Conducteur de travaux (groupe « Gestionnaire de projet ») | Relit les journaux soumis, remet en brouillon une ligne erronée, valide le journal entier. |
| Direction, contrôle de gestion | Consulte le coût réel et l'avancement calculés sur les phases, les chantiers et le tableau de bord. |

Parcours type d'une journée :

1. Le matin, le chef de chantier ouvre le journal du jour et clique sur « Reprendre les travaux du dernier journal ».
2. À midi, il saisit la quantité coulée sur la dalle, corrige la consommation de ciment proposée, puis valide le travail : le ciment sort du stock et la phase passe de 40 % à 52 %.
3. L'après-midi, il ajoute une nouvelle ligne sur la même phase pour la suite du coulage.
4. Le soir, il ajoute la météo et les observations, puis soumet le journal.
5. Le conducteur de travaux relit le journal, remet éventuellement une ligne en brouillon pour correction, puis valide le journal entier.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `miro.site.journal` | Le journal d'un chantier pour un jour | `project_id`, `date`, `user_id` (chef de chantier), `state` (brouillon / soumis / validé), `location_id` (emplacement d'où sortent les matières), `weather`, `hours_lost`, `notes`, totaux calculés (`headcount`, `labor_hours`, `labor_cost`, `material_cost`, `equipment_cost`, `expense_cost`, `total_cost`) |
| `miro.site.journal.work` | Un travail sur une phase | `journal_id`, `task_id` (phase), `qty_done`, `correction_reason`, `status`, `state` (brouillon / validé), `validated_by_id`, `validated_on`, `progress_after`, `check_html` |
| `miro.site.journal.line` | Modèle abstrait commun aux lignes | `work_id` ou rattachement direct au journal, `journal_id`, `task_id`, `state`, `validated_by_id`, `validated_on`, verrous et actions de validation |
| `miro.site.journal.labor` | Main-d'œuvre | `employee_id`, `hours`, `hourly_cost` (figé à la saisie), `cost` |
| `miro.site.journal.material` | Consommation de matière | `need_id` (besoin matière de la phase), `quantity`, `planned_qty` (théorique), `unit_cost`, `cost`, `move_ids` (sorties de stock créées) |
| `miro.site.journal.equipment` | Matériel utilisé | `equipment_id`, `hours`, `hourly_cost`, `cost` |
| `miro.site.journal.expense` | Dépense | `name`, `partner_id`, `amount` |
| `miro.site.equipment` | Référentiel du matériel | `name`, `ownership` (en propre / loué), `hourly_cost` |

Le module étend aussi :

- **`project.task`** (la phase) : avancement calculé (`x_avancement_manuel`, `x_avancement_global`), réalisé cumulé (`x_qty_realisee`), poids dans l'avancement (`x_poids_avancement`), heures réalisées, contrôles de cohérence, coûts réels ventilés (`x_cout_mo_reel`, `x_cout_matiere_reel`, `x_cout_materiel_reel`, `x_cout_divers_reel`, `x_cout_reel`) ;
- **`project.project`** : nombre de journaux, journaux à valider, coûts réels totaux du chantier ;
- **`construction.element`** (l'ouvrage) : avancement pondéré de ses phases.

Relations principales : un chantier a plusieurs journaux ; un journal a plusieurs travaux et des lignes de frais du chantier ; un travail a des lignes de main-d'œuvre, de consommation, de matériel et de dépenses ; une ligne de consommation pointe vers un besoin matière de la phase (module `miro_construction_bom`) et vers les mouvements de stock qu'elle a créés.

## 5. Règles métier et calculs

**Avancement d'une phase** (`models/project_task.py`)
- Avec métré : réalisé cumulé des travaux validés ÷ métré de la phase × 100, borné entre 0 et 100 %.
- Sans métré : l'état du dernier travail validé donne 0 % (pas commencé), 50 % (en cours) ou 100 % (fini).
- Tâche mère et chantier : moyenne des sous-tâches **pondérée par leur coût prévu** (main-d'œuvre prévue + matières prévues). Une dalle à 1 000 000 pèse cent fois plus qu'une implantation à 10 000. Si aucune tâche n'a de coût prévu, c'est une moyenne simple.

**Coût réel** (`models/project_task.py`, `models/project_project.py`)
- Main-d'œuvre : somme des lignes validées, heures × coût horaire chargé. Ce coût horaire vient de la paie (`miro_hr_paie`). Il est lu en mode superutilisateur, car les taux de paie sont réservés aux RH, et il est figé sur la ligne au moment de la saisie.
- Matières : somme des mouvements de stock terminés liés aux besoins de la phase, quantité × prix au jour de la sortie. Un mouvement de retour (ligne remise en brouillon) se **déduit**.
- Matériel et dépenses : somme des lignes validées.
- Chantier : somme des coûts propres de chaque tâche (sans double compte des tâches mères), plus les frais du chantier sans phase.

**Validation et verrous** (`models/site_journal.py`)
- Un travail ou une ligne validé ne peut plus être modifié ni supprimé ; on ne peut plus ajouter de ligne dans un travail validé ; un journal qui contient des lignes validées ne peut plus être supprimé.
- Un journal validé est entièrement figé. Seuls ses abonnés et activités restent modifiables.
- Valider une ligne de consommation crée une sortie de stock vers l'emplacement « Consommation chantier », au coût standard du produit ce jour-là.
- La remise en brouillon est réservée au groupe `project.group_project_manager`. Elle crée le mouvement inverse et vide le lien vers les sorties de stock. On ne peut pas remettre en brouillon une ligne d'un travail validé sans remettre d'abord le travail en brouillon.
- Valider le journal valide d'abord tous les travaux et frais restants, puis passe le journal à l'état « Validé » en enregistrant qui l'a validé et quand.

**Autres contrôles**
- Un ouvrier ne peut pas cumuler plus de 24 h dans une journée, toutes phases confondues.
- Les heures doivent être positives ; une quantité consommée ne peut pas être négative.
- Une quantité réalisée négative exige un motif et ne peut pas dépasser ce qui a déjà été réalisé.
- Un journal vide (ni travail, ni frais, ni heures d'arrêt) ne peut être ni soumis ni validé.

## 6. Interfaces

- **Menu** Construction > Journaux de chantier : vues liste, calendrier (un journal par jour, coloré par chantier) et formulaire. Filtres « Mes journaux », « Brouillons », « À valider », « Validés », regroupements par chantier, chef de chantier ou mois.
- **Menu** Construction > Configuration > Matériel de chantier.
- **Formulaire du journal** : boutons Soumettre, Valider (conducteur de travaux), Renvoyer en brouillon, Reprendre les travaux du dernier journal ; onglets Travaux du jour, Frais du chantier, Météo et incidents, Coûts. Chaque ligne affiche son état, un bouton « Valider la ligne » et, pour le conducteur, « Remettre en brouillon ». Les champs d'une ligne validée passent en lecture seule.
- **Fiche chantier** : bouton statistique « Journaux », coûts réels totaux et nombre de journaux à valider.
- **Fiche phase** : réalisé cumulé sur le métré, heures réalisées, poids dans l'avancement, contrôle de cohérence (badge « Cohérent » ou « À vérifier ») et coûts réels ventilés.
- Pas de route HTTP propre : l'accès mobile passe par le module `miro_mobile_api`.

## 7. Sécurité et droits d'accès

- Tous les utilisateurs internes peuvent lire, créer et modifier les journaux et leurs lignes (`security/ir.model.access.csv`). Ils lisent le référentiel matériel.
- Le groupe Gestionnaire de projet (le conducteur de travaux) gère le référentiel matériel, valide les journaux et peut seul remettre une ligne en brouillon. Ce dernier contrôle est fait dans le code (`_check_can_reset`) et pas seulement dans la vue.
- Les verrous (ligne validée, travail validé, journal validé) sont appliqués dans les méthodes `create`, `write` et `unlink`. Ils s'imposent donc à toutes les interfaces : formulaire, import, API mobile.

## 8. Intégration avec les autres modules

- **`miro_construction_project`** : fournit les chantiers, les phases et leur métré (`phase_qty`), les ouvrages (`construction.element`) et le champ d'avancement global.
- **`miro_construction_bom`** : fournit les besoins matière des phases (`construction.material.need`) et la méthode de sortie de stock `_consume`, avec le retour en stock (`reverse=True`).
- **`miro_construction_planning`** : fournit les heures prévues des phases et les équipes. Par lui, `miro_hr_paie` fournit le coût horaire chargé des ouvriers et le nombre d'heures par jour de la société.
- **`miro_construction_overview`** : le tableau de bord lit les journaux, les heures validées et les coûts réels.
- **`miro_mobile_api`** : l'application mobile crée, modifie et valide les lignes du journal ; elle ne valide jamais le journal entier.

## 9. Points techniques notables

- **Des chiffres calculés, jamais saisis** : l'avancement et le coût réel sont des champs calculés et stockés, recalculés automatiquement par l'ORM d'Odoo (le moteur de dépendances `@api.depends`) dès qu'une ligne change d'état. C'est le choix d'architecture principal du module.
- **Un modèle abstrait commun** (`miro.site.journal.line`) factorise pour les quatre types de lignes le rattachement au travail ou au journal, l'état, les verrous et la validation. Chaque type n'ajoute que ses champs et ses effets propres, par des « hooks » `_on_validate` et `_on_reset` : la ligne de consommation y sort ou remet la matière en stock.
- **Migrations de données** maîtrisées :
  - **1.2.0** : les avancements saisis à la main avant le module sont repris dans un « journal de reprise » validé par chantier, pour ne perdre aucun historique ;
  - **1.3.0** : l'état des lignes, jusque-là une copie de l'état du journal, devient l'état propre de chaque ligne, et la contrainte « une phase par journal » est supprimée de la base.
- **Coût horaire figé** : le coût horaire de l'ouvrier est recopié sur la ligne à la saisie. Une augmentation de salaire ultérieure ne réécrit pas le passé.
- **Contrôles de cohérence** : plutôt que d'empêcher la saisie, le module confronte l'avancement déclaré aux heures et à la matière, et signale les écarts. C'est une aide à la décision pour le conducteur de travaux.

## 10. Limites et pistes d'amélioration

- `models/construction_element.py` : la méthode `action_open_site_journals` utilise la fonction de traduction `_` sans l'importer, et filtre les journaux sur l'identifiant de l'ouvrage au lieu de celui du chantier. Elle n'est appelée par aucune vue aujourd'hui, mais elle échouerait si on la branchait.
- Le prix des matières est le coût standard du produit au jour de la sortie : pas de valorisation FIFO ni au coût moyen réel du lot.
- La remise en brouillon d'un travail remet aussi en brouillon toutes ses lignes, y compris celles qui avaient été validées une par une.
- Le coût du matériel repose sur un taux horaire saisi à la main : pas de lien avec la comptabilité des immobilisations ni avec les factures de location.
- Piste : envoyer une notification au conducteur de travaux à la soumission d'un journal, ou quand un contrôle de cohérence passe à « À vérifier ».
