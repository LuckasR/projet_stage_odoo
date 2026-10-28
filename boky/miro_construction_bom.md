# Nomenclatures et besoins matériaux (`miro_construction_bom`)

> Ce module relie les métrés des éléments de construction (volume de béton, poids d'acier, surface coffrée ou maçonnée) à des « recettes » de matériaux. Il calcule ainsi, phase par phase, les besoins en matières premières d'un chantier, puis les suit jusqu'à la demande de prix, la réception et la consommation réelle.

| Fiche | |
|---|---|
| Nom technique | `miro_construction_bom` |
| Version | 17.0.1.1.0 |
| Catégorie | Services/Project |
| Dépend de | `miro_construction_project`, `construction_product_management`, `mrp`, `purchase`, `stock` |
| Utilisé par | `miro_construction_journal` (et, en lecture, `miro_mobile_api`) |
| Auteur / licence | « Votre Entreprise » (valeur par défaut du manifeste) / LGPL-3 |

## 1. Le besoin métier

Sur un chantier, la quantité de matériaux à acheter découle directement des métrés : un poteau de 0,25 m³ coulé en béton dosé à 350 kg/m³ demande environ 87,5 kg de ciment, du sable, du gravier et de l'eau. Jusqu'ici, le conducteur de travaux faisait ces calculs à part, sur tableur, sans lien avec les achats ni avec le stock.

Le module répond à quatre questions :

- **Combien faut-il de chaque matériau**, pour chaque phase de chaque élément (semelle, poteau, mur…), compte tenu des pertes (chutes d'acier, sable perdu, panneau de coffrage réemployé) ?
- **Quel produit réel acheter** pour un besoin générique (« ciment » devient « Ciment CPJ 42.5, sac de 50 kg » sur ce chantier) ?
- **Où en est l'approvisionnement** : ce qui est commandé, reçu, en stock, manquant ?
- **L'écart entre prévu et réel** : a-t-on consommé plus que prévu sur une phase ?

## 2. Fonctionnalités

### Recettes de chantier (nomenclatures)

Le module réutilise les nomenclatures natives d'Odoo (`mrp.bom`, appelées « BoM » ou nomenclatures de fabrication) comme **recettes de chantier**. Une recette décrit les matériaux nécessaires pour **une unité d'ouvrage** : 1 m³ de béton coulé, 1 kg d'acier posé, 1 m² coffré, 1 m² de maçonnerie. Aucun ordre de fabrication n'est jamais créé : la nomenclature sert uniquement au calcul.

Sur la fiche nomenclature, l'utilisateur voit :

- une case **« Recette de chantier »** qui rend la nomenclature proposable sur les phases ;
- pour chaque ligne, une **catégorie de matériau** (« besoin couvert ») et un **coefficient** de pertes ou de réemploi (1,05 = 5 % de pertes ; 0,20 = panneau réemployé 5 fois) ;
- un onglet **Phases** listant les phases de gabarit qui l'utilisent, un bouton statistique **Besoins**, et un bouton **Recalculer les besoins** qui applique une recette modifiée aux phases non commencées.

Les nomenclatures imbriquées de type « Kit » sont prises en compte : le mortier d'une maçonnerie peut lui-même être une recette (ciment + sable + eau).

### Recettes livrées par défaut

À l'installation et à chaque mise à jour, quatre recettes sont créées si elles n'existent pas :

| Code | Ouvrage (unité) | Phase visée | Composition |
|---|---|---|---|
| `MIRO-BET-350` | Béton dosé à 350 kg/m³ (1 m³) | coulage | 350 kg ciment, 0,40 m³ sable (x1,05), 0,80 m³ gravier (x1,05), 175 L eau |
| `MIRO-ARM-HA` | Armatures HA (1 kg) | ferraillage | 1 kg acier (x1,10), 0,01 kg fil de ligature |
| `MIRO-COF-BOIS` | Coffrage bois (1 m²) | coffrage | 1 m² contreplaqué (x0,20), 0,05 kg clous |
| `MIRO-MAC-PARP` | Maçonnerie de parpaings (1 m²) | élévation | 10 parpaings (x1,05), 0,02 m³ mortier (x1,10) |

Elles sont rattachées automatiquement aux phases de gabarit de même code qui n'ont pas encore de nomenclature. Un gabarit « Mur maçonné » (une phase Élévation au m²) est aussi créé et attribué au type d'élément « Mur » s'il n'en avait aucun.

### Rattachement aux phases et surcharge par type d'élément

Dans un gabarit de phases (défini par `miro_construction_project`), chaque phase peut porter une nomenclature. Le module ajoute aussi la quantité de référence « Surface (m²) ».

Sur un **type d'élément**, un onglet **Nomenclatures** permet d'imposer une autre recette pour une phase donnée : le même gabarit « Semelle » peut servir aux semelles (béton C20/25) et aux poteaux (béton C25/30).

### Calcul automatique des besoins par phase

Pour chaque phase (tâche) d'un élément, le module crée des **besoins matériaux** : une ligne par matériau de la recette, avec la quantité nécessaire, le produit retenu et le coût prévu. Ces besoins sont recalculés automatiquement :

- à la génération des phases d'un élément ;
- quand un métré de l'élément change (par exemple une ouverture déduite d'un mur) ;
- sur demande (bouton sur le projet, la phase ou la nomenclature).

Une phase déjà commencée garde ses besoins, et un besoin déjà commandé ou consommé n'est jamais modifié ni supprimé.

### Choix du produit réel par projet

Dans l'onglet **Matériaux** du projet, l'utilisateur associe chaque besoin générique (catégorie) à un produit précis. Ce choix s'applique immédiatement à tous les besoins non commandés du projet, y compris ceux des sous-catégories. Sans choix, c'est l'article indiqué sur la ligne de nomenclature qui est utilisé.

### Suivi d'un besoin

Chaque besoin a un état calculé : **Produit à choisir**, **À commander**, **Commandé**, **Reçu**, **Consommé**. Il affiche les quantités commandée, reçue, consommée, le reste à consommer et l'écart réel/prévu (positif = surconsommation, surligné en rouge dans les listes).

### Demandes de prix fournisseurs

Le bouton **Demandes de prix matériaux** du projet ouvre un assistant qui regroupe les besoins « À commander » par produit, propose de déduire le stock disponible, pré-remplit le fournisseur et le prix depuis la fiche produit, puis crée **une demande de prix par fournisseur**. Les besoins sont rattachés aux lignes d'achat créées, ce qui fait évoluer leur état.

### Tableau de bord des matériaux

Un bouton **Besoins en MP** sur la fiche projet ouvre un tableau de bord dédié :

- indicateurs : coût prévu, coût consommé, nombre de matériaux, besoins et éléments, pourcentages commandé / reçu / consommé (pondérés par la valeur) ;
- tableau par matériau avec une barre d'approvisionnement (consommé, reçu, commandé), le stock disponible, le manque éventuel et un statut coloré ;
- filtres (À commander, Stock insuffisant, Surconsommation, Produit à choisir) et recherche ;
- répartition du coût prévu par ouvrage, par niveau ou par phase ;
- boutons pour recalculer, lancer les demandes de prix, imprimer le rapport ou ouvrir le détail des besoins.

### Rapport PDF des besoins en matériaux

Un rapport A4 paysage reprend les mêmes données : synthèse, tableau d'approvisionnement par matériau, répartition du coût prévu et points d'attention (stock insuffisant, surconsommation, produit à choisir).

### Consommation réelle (déléguée au journal de chantier)

Le module fournit le mécanisme de sortie de stock vers un emplacement virtuel « Consommation chantier ». La saisie des consommations se fait désormais dans le **journal de chantier** (`miro_construction_journal`). Un ancien assistant de consommation propre au module a été supprimé dans la version en cours de développement.

## 3. Qui l'utilise et comment

| Rôle | Usage |
|---|---|
| Bureau d'études / méthodes | Paramètre les recettes, leurs coefficients et leur rattachement aux phases et types d'éléments. |
| Conducteur de travaux | Choisit les produits du chantier, consulte le tableau de bord, recalcule les besoins. |
| Acheteur | Lance les demandes de prix depuis les besoins, suit les commandes et réceptions. |
| Chef de chantier | Déclare les consommations via le journal de chantier (autre module). |

Parcours type :

1. Le bureau d'études vérifie les recettes livrées (menu Configuration > Nomenclatures) et ajuste un dosage ou un coefficient.
2. Les éléments du projet sont saisis et leurs phases générées (module `miro_construction_project`) : les besoins sont calculés automatiquement.
3. Dans l'onglet **Matériaux** du projet, le conducteur de travaux associe « Ciment » au produit réellement acheté.
4. Il ouvre le tableau de bord **Besoins en MP** et repère les matériaux à commander ou en stock insuffisant.
5. Il clique sur **Demandes de prix**, ajuste quantités et fournisseurs, puis valide : les demandes de prix sont créées.
6. À la réception, les besoins passent à « Reçu ». Au fil du chantier, les consommations déclarées dans le journal font passer les besoins à « Consommé » et révèlent les écarts.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `construction.material.need` (nouveau) | Besoin matière d'une phase | `task_id`, `element_id`, `project_id`, `level_id`, `bom_id`, `bom_line_id`, `category_id`, `product_id`, `base_qty`, `quantity`, `product_qty`, `planned_cost`, `purchase_line_id`, `move_ids`, `qty_ordered`, `qty_received`, `qty_consumed`, `qty_remaining`, `qty_gap`, `state` |
| `construction.project.material` (nouveau) | Produit retenu pour une catégorie sur un projet | `project_id`, `category_id`, `product_id` |
| `construction.element.type.bom` (nouveau) | Nomenclature imposée par un type d'élément pour une phase | `type_id`, `phase_line_id`, `bom_id` |
| `construction.need.purchase.wizard` / `.line` (transitoires) | Assistant de demandes de prix | `project_id`, `deduct_stock`, lignes : `product_id`, `needed_qty`, `available_qty`, `to_order_qty`, `partner_id`, `price_unit` |
| `mrp.bom` (étendu) | Recette de chantier | `construction_ok`, `phase_line_ids`, `need_ids` |
| `mrp.bom.line` (étendu) | Ligne de recette | `material_category_id`, `coefficient` |
| `construction.phase.template.line` (étendu) | Phase de gabarit | `bom_id`, valeur `surface_m2` ajoutée à `qty_key` |
| `construction.element.type` (étendu) | Type d'élément | `bom_override_ids` |
| `project.project`, `project.task`, `construction.element` (étendus) | Projet, phase, élément | `material_need_ids`, `material_choice_ids`, `material_planned_cost` |
| `purchase.order.line`, `stock.move` (étendus) | Achat et mouvement de stock | `construction_need_ids`, `construction_need_id` |

Relations importantes :

- Un **élément** a plusieurs **phases** (tâches) ; chaque phase a plusieurs **besoins**, un par ligne de recette.
- Un besoin pointe vers une **ligne d'achat** (plusieurs besoins d'un même produit partagent une ligne) et vers des **mouvements de stock** de consommation.
- La **catégorie de matériau** (venant de `construction_product_management`) est le pivot entre la ligne de recette générique et le produit choisi par le projet.

## 5. Règles métier et calculs

- **Formule du besoin** (`models/material_need.py`, `_refresh_material_needs`) : besoin = métré de la phase x (quantité de la ligne / quantité de référence de la recette) x coefficient. Le métré est converti dans l'unité de la recette sans arrondi, pour éviter qu'un 0,252 m³ devienne 0,26 m³ avant multiplication.
- **Explosion de la recette** (`models/mrp_bom.py`, `_construction_explode`) : descend dans les kits comme l'`explode()` natif, mais applique le coefficient de chaque ligne et n'arrondit pas à l'unité supérieure (l'arrondi natif gonflerait chaque besoin de phase).
- **Cohérence des unités** (`models/mrp_bom.py`, `_check_unit_for` ; `models/bom_links.py`) : une recette ne peut être rattachée à une phase que si son unité est de la même catégorie que le métré (m³ pour le béton, kg pour l'acier, m² pour coffrage et surface). Une phase portant une recette doit avoir une quantité de référence.
- **Choix de la recette** (`models/bom_links.py`, `_bom_for`) : la surcharge du type d'élément prime sur la recette du gabarit. Une seule surcharge par phase et par type (contrainte SQL).
- **Verrou des besoins** (`models/material_need.py`, `_is_locked`) : un besoin rattaché à un achat non annulé ou ayant une consommation validée n'est plus réécrit ni supprimé. Une phase commencée (avancement non nul, ou tâche terminée/annulée) n'est pas recalculée, sauf recalcul forcé depuis la phase.
- **Choix du produit** (`models/project_material.py`, `_product_for`) : on remonte la hiérarchie des catégories jusqu'à trouver un choix du projet ; sinon l'article de la ligne. Un produit retenu doit appartenir à la catégorie ou à une sous-catégorie (domaine). Une ligne de recette dont l'article n'a pas de catégorie lui transmet la sienne (`_link_products`) ; un article d'une autre catégorie est refusé (`_check_material_category`).
- **Conversion produit et coût** (`_compute_product_qty`) : la quantité est convertie dans l'unité du produit si les unités sont compatibles ; coût prévu = quantité produit x coût standard du produit.
- **Avancement achat** (`_compute_progress`) : chaque besoin reçoit une part de la quantité reçue au prorata de sa quantité sur la ligne d'achat. « Commandé » ne compte que pour une commande confirmée.
- **Consommation et retours** (`_consume`, `stock.move._miro_consumed_qty`) : une consommation est un mouvement de stock validé depuis l'emplacement choisi vers « Consommation chantier », au coût du produit le jour de la sortie. Avec `reverse=True`, le mouvement inverse fait revenir la matière (annulation d'un journal) ; ce retour est compté en négatif dans le consommé. La sortie est forcée à la quantité déclarée même si le stock informatique ne la couvre pas.
- **États** : Produit à choisir > Consommé (consommé >= prévu) > Reçu > Commandé > À commander, comparaisons faites à la précision de l'unité du produit.
- **Tableau de bord** (`get_material_dashboard`) : manque = reste à consommer - stock disponible - quantités commandées non encore reçues, arrondi à la précision de l'unité pour éviter les faux « manque 0 » dus aux résidus de calcul flottant.
- **Assistant d'achat** (`wizard/need_purchase_wizard.py`) : quantité proposée = besoin - stock disponible (si « déduire le stock ») ; refus si rien à commander ou si un fournisseur manque. Le stock n'est pas réservé au projet.
- **Taux d'avancement matière** (`_material_progress`) : part des matériaux mis en œuvre, pondérée par le coût prévu, plafonnée au prévu ; prévue comme contrôle de l'avancement déclaré, elle n'est appelée par aucun écran du module.

## 6. Interfaces

- **Menus** : Construction > Besoins matériaux ; Construction > Configuration > Nomenclatures (recettes de chantier uniquement).
- **Vues** : liste (avec totaux et couleurs), tableau croisé dynamique (catégorie x niveau) et formulaire des besoins ; extensions des formulaires nomenclature, gabarit de phases, type d'élément, projet (boutons d'en-tête, bouton statistique, onglet Matériaux), formulaire « Chantier » et phase (onglet Matériaux placé en premier).
- **Assistant** : Demandes de prix matériaux.
- **Rapport PDF** : « Rapport des besoins en matériaux », format A4 paysage dédié, disponible aussi dans le menu Imprimer du projet.
- **JavaScript** : action client OWL `miro_construction_bom.material_dashboard` (tableau de bord), qui obtient toutes ses données en un seul appel serveur.
- **Données** : emplacement virtuel « Consommation chantier » ; activation des unités de mesure pour tous les utilisateurs internes (les recettes mêlent m³, kg, L et m²) ; recettes par défaut.
- **Migration** : script `migrations/17.0.1.1.0/pre-migrate.py` (voir section 9).
- Aucune route HTTP ni tâche planifiée.

## 7. Sécurité et droits d'accès

Les nouveaux modèles (besoins, choix de matériaux, surcharges par type, assistant) sont accessibles en lecture, écriture, création et suppression à tout utilisateur interne (`base.group_user`). Il n'y a ni groupe dédié ni règle d'enregistrement : la séparation des responsabilités (qui peut commander, qui peut modifier une recette) repose sur les droits natifs des modules Achats et Fabrication. Les listes et formulaires de besoins interdisent la création manuelle (`create="false"`) : un besoin naît toujours du calcul.

## 8. Intégration avec les autres modules

- **`miro_construction_project`** : fournit projets, éléments et leurs métrés, gabarits de phases, types d'éléments, phases (tâches). Le module s'accroche à `construction.element.write` et `_generate_tasks` pour recalculer.
- **`construction_product_management`** : fournit les catégories de matériaux hiérarchiques et le champ « besoin couvert » des produits.
- **`mrp`** : nomenclatures natives, kits, recherche de nomenclature (`_bom_find`).
- **`purchase`** : demandes de prix, lignes d'achat, sélection du fournisseur (`_select_seller`).
- **`stock`** : stock disponible, mouvements de consommation, emplacement virtuel.
- **`miro_construction_journal`** : appelle `_consume` à la validation d'un journal et `_consume(..., reverse=True)` à sa remise en brouillon ; utilise les besoins et coûts pour le coût réel des phases.
- **`miro_mobile_api`** : lit les besoins d'une phase pour l'application mobile de suivi de chantier.

## 9. Points techniques notables

- **Réutiliser le natif plutôt que réinventer** : une première version utilisait une nomenclature maison (`construction.bom`). Le passage aux nomenclatures natives `mrp.bom` apporte gratuitement kits, variantes, unités et interface. Un script de pré-migration détache les anciennes références (sinon PostgreSQL refuse la suppression de l'ancienne table à cause d'une clé étrangère), supprime les besoins non commandés pour qu'ils soient recalculés, et conserve ceux qui ont déjà servi.
- **Explosion sur mesure** : l'algorithme récursif reprend la logique native mais supprime l'arrondi et applique les coefficients, ce qui est indispensable pour des quantités de chantier fractionnaires.
- **Besoin générique / produit réel** : séparer la catégorie (« ciment ») du produit (« CPJ 42.5 en sac ») permet de partager des recettes entre chantiers tout en laissant chaque projet choisir ses fournisseurs.
- **Recalcul sûr** : le recalcul compare les besoins existants et souhaités par ligne de recette, met à jour ou crée, supprime les besoins obsolètes, mais ne touche jamais un besoin verrouillé. C'est ce qui permet de recalculer à tout moment sans casser les commandes.
- **Installation idempotente** : `_install_default_boms` peut être rejouée à chaque mise à jour sans dupliquer ni écraser les choix de l'utilisateur.
- **Consommation par mouvements de stock** : utiliser un emplacement virtuel de type production fait remonter la consommation dans la valorisation de stock standard et fige le coût au jour de la sortie ; l'annulation passe par un mouvement retour plutôt qu'une suppression, ce qui garde la traçabilité.
- **Tableau de bord performant** : agrégation entièrement côté serveur en une méthode, réutilisée telle quelle par le rapport PDF, ce qui garantit des chiffres identiques à l'écran et à l'impression.

## 10. Limites et pistes d'amélioration

- **Unités d'achat** : l'assistant crée la ligne d'achat dans l'unité d'achat du produit avec une quantité calculée dans son unité de stock, sans conversion ; de même, la répartition des réceptions compare des quantités dans ces deux unités. Cela n'est juste que si les deux unités sont identiques.
- **Commande partielle** : quand le stock est déduit, la ligne d'achat porte moins que la somme des besoins, mais chaque besoin est compté « commandé » pour sa quantité entière et l'état « Commandé » s'affiche même pour une demande de prix non confirmée.
- **Droits** : aucun groupe dédié ; tout utilisateur interne peut modifier ou supprimer des besoins.
- **Coût** : coût prévu basé sur le coût standard courant du produit, non figé à la date du calcul.
- **Réservation** : le stock déduit n'est pas réservé au chantier et peut être consommé par un autre projet.
- **Taux d'avancement matière** calculé mais pas encore exploité à l'écran.
- **Travail en cours** : la suppression de l'assistant de consommation et le transfert de la saisie vers le journal de chantier ne sont pas encore validés dans l'historique Git.
- Pistes : réservation du stock par projet, planification des achats selon les dates des phases, alertes automatiques de surconsommation, comparaison des prix entre fournisseurs.
