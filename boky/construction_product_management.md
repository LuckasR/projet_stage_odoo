# Gestion des matériaux de construction (`construction_product_management`)

> Ce module transforme la fiche produit standard d'Odoo en fiche « matériau de construction » : classement par type et par catégorie de matériau, caractéristiques techniques configurables (diamètre, granulométrie, classe de résistance…). Il fournit aussi le référentiel des besoins génériques (ciment, sable, acier…) sur lequel s'appuient les nomenclatures de chantier.

| Fiche | |
|---|---|
| Nom technique | `construction_product_management` |
| Version | 17.0.1.0.0 |
| Catégorie | Inventory/Inventory |
| Dépend de | `product`, `stock` |
| Utilisé par | `miro_construction_bom` |
| Auteur / licence | L. M. RABEMIAFARA / LGPL-3 |

## 1. Le besoin métier

Une entreprise de BTP achète et stocke des produits très différents : ciment en sacs, sable et gravier au m³, fer à béton à la barre ou au kilo, parpaings à l'unité. La fiche produit standard d'Odoo ne permet pas de décrire ce qui compte sur un chantier : la classe de résistance d'un ciment, la granulométrie d'un sable, le diamètre et la nuance d'un acier.

Il faut aussi pouvoir raisonner en **besoin générique** : une nomenclature dit « il faut du ciment », sans imposer une marque ou un conditionnement. Le module crée donc une hiérarchie de **catégories de matériaux** qui permet de rattacher plusieurs produits réels à un même besoin.

## 2. Fonctionnalités

### Fiche produit « matériau de construction »

Sur la fiche produit, une case **Matériau de construction** apparaît à côté du type de produit. Une fois cochée, un onglet **Matériau de construction** s'affiche avec :

- le **type de matériau** (ex. « Ciment CPJ 42.5 ») et la catégorie qui en découle ;
- le **besoin couvert** (catégorie de matériau générique) ;
- un tableau de **caractéristiques techniques**, pré-rempli selon le type choisi, où l'utilisateur saisit les valeurs (numérique, texte ou choix dans une liste) ;
- une **note technique** libre.

Choisir un type coche automatiquement la case, reprend la catégorie de matériau du type et ajoute une ligne pour chaque caractéristique attendue, sans effacer les lignes déjà saisies. Décocher la case vide le type et les caractéristiques.

### Types de matériaux

Un catalogue configurable de sous-types (« Sable de rivière 0/4 », « Gravier 8/15 », « Fer à béton Fe E400 »…), chacun rattaché à une catégorie fixe (ciment, sable, gravier, acier, bois, brique, parpaing, carrelage, peinture, autre) et à une catégorie de matériau. Le type définit la liste des **caractéristiques applicables** et affiche le nombre de produits liés (bouton statistique ouvrant ces produits). Neuf types sont livrés à l'installation.

### Caractéristiques techniques

L'utilisateur définit des caractéristiques réutilisables (largeur, diamètre, masse, classe de résistance…) avec un code technique unique, un type de valeur (numérique, texte, liste de choix), une unité de mesure pour les valeurs numériques et, pour les listes, les options possibles (ex. Fe E400 / Fe E500).

### Catégories de matériaux (besoins génériques)

Un référentiel hiérarchique (catégorie parente / sous-catégories) affiché sous la forme « Parent / Enfant ». Chaque fiche montre les produits rattachés, les sous-catégories et le nombre de produits, sous-catégories comprises. C'est ce référentiel que visent les lignes de nomenclature du module `miro_construction_bom`.

### Recherche et listes

Dans la liste des produits : colonnes optionnelles Catégorie et Type de matériau, filtre « Matériaux de construction », regroupements par catégorie et par type. Un menu dédié n'affiche que les matériaux, regroupés par catégorie.

## 3. Qui l'utilise et comment

| Rôle | Usage |
|---|---|
| Administrateur / responsable de stock | Définit les caractéristiques, les types et les catégories de matériaux. |
| Magasinier, acheteur, bureau d'études | Crée et renseigne les fiches matériaux, recherche les produits par catégorie. |

Parcours type :

1. Le responsable crée la caractéristique « Diamètre » (numérique, en mm) et « Nuance » (liste : Fe E400, Fe E500).
2. Il ouvre le type « Fer à béton Fe E400 » et lui associe ces caractéristiques ainsi que la catégorie « Acier ».
3. Un acheteur crée le produit « Fer HA10 barre de 12 m », choisit le type : la case est cochée, les lignes Diamètre et Nuance apparaissent, il saisit 10 et Fe E400.
4. Le produit est désormais proposé partout où une nomenclature demande de l'« Acier ».

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `construction.material.category` | Besoin générique, hiérarchique | `name`, `code`, `parent_id`, `child_ids`, `product_tmpl_ids`, `product_count`, `active` |
| `construction.material.type` | Sous-type de matériau | `name`, `category` (liste fixe), `material_category_id`, `attribute_ids`, `product_tmpl_ids`, `product_count`, `active` |
| `construction.material.attribute` | Définition d'une caractéristique | `name`, `code`, `value_type`, `uom_id`, `selection_option_ids` |
| `construction.material.attribute.option` | Valeur possible d'une caractéristique de type liste | `attribute_id`, `name` |
| `construction.material.characteristic` | Valeur d'une caractéristique pour un produit | `product_tmpl_id`, `attribute_id`, `value_float`, `value_char`, `value_selection_id` |
| `product.template` (étendu) | Fiche produit | `is_construction_material`, `construction_material_type_id`, `construction_category`, `material_category_id`, `characteristic_ids`, `technical_note` |

Relations importantes : un produit a un type et une catégorie de matériau ; un type propose plusieurs caractéristiques ; un produit porte une valeur par caractéristique. La catégorie de matériau est le lien vers les nomenclatures de chantier.

## 5. Règles métier et calculs

- **Type obligatoire** (`models/product_template.py`) : un produit marqué « matériau de construction » doit avoir un type, sinon l'enregistrement est refusé.
- **Pré-remplissage des caractéristiques** (`models/product_template.py`, `_sync_characteristics`) : ajoute uniquement les caractéristiques manquantes du type, sans toucher aux valeurs existantes.
- **Unicités** (contraintes SQL) : un nom de type par catégorie (`construction_material_type.py`) ; un code de caractéristique unique (`construction_material_attribute.py`) ; une seule valeur par caractéristique et par produit (`construction_material_characteristic.py`).
- **Liste de choix** : la valeur proposée est filtrée sur les options de la caractéristique concernée.
- **Comptage récursif** (`models/ConstructionMaterialCategory.py`) : le nombre de produits d'une catégorie inclut ses sous-catégories (opérateur `child_of`).
- **Transition liste fixe vers catégories** (`_for_legacy_code`, `_backfill_material_categories`) : l'ancienne liste fixe `category` est conservée pour compatibilité, mais la catégorie de matériau prime. À chaque mise à jour, une fonction de reprise crée au besoin la catégorie correspondant à l'ancienne valeur et la renseigne sur les types et produits qui n'en ont pas, sans jamais remplacer un choix existant.
- **Suppressions protégées** : un type, une caractéristique ou une catégorie utilisés ne peuvent pas être supprimés (`ondelete='restrict'`).

## 6. Interfaces

- **Menu** : application **Construction** (racine propre au module) avec les sous-menus Matériaux de construction, Catégories de matériaux, Types de matériaux, Caractéristiques.
- **Vues** : héritage du formulaire, de la liste et de la recherche produit ; listes éditables et formulaires pour types et caractéristiques ; liste et formulaire à onglets pour les catégories.
- **Données** : neuf types de matériaux initiaux (chargés en `noupdate`, donc modifiables sans être écrasés) ; appel de la fonction de reprise des catégories.
- Pas de rapport PDF, d'assistant, de route HTTP, de tâche planifiée ni de JavaScript.

## 7. Sécurité et droits d'accès

| Modèle | Utilisateur interne | Administrateur / responsable de stock |
|---|---|---|
| Types de matériaux | Tous droits | Tous droits |
| Caractéristiques et leurs options | Lecture seule | Tous droits |
| Valeurs de caractéristiques (sur les produits) | Tous droits | Tous droits (via le groupe utilisateur) |
| Catégories de matériaux | Tous droits | Tous droits |

Le paramétrage des caractéristiques est donc réservé aux administrateurs et responsables de stock, alors que tout utilisateur peut renseigner les valeurs sur une fiche produit. Il n'y a pas de règle d'enregistrement.

## 8. Intégration avec les autres modules

- **`product` / `stock`** : extension de la fiche produit et utilisation des unités de mesure (`uom.uom`).
- **`miro_construction_bom`** : s'appuie sur `construction.material.category` et sur le champ `material_category_id` des produits pour relier une ligne de nomenclature générique (« Ciment ») aux produits réels qu'un projet peut retenir, y compris dans les sous-catégories.

## 9. Points techniques notables

- **Caractéristiques dynamiques** plutôt que des champs figés : au lieu d'ajouter des champs « diamètre », « granulométrie »… à la fiche produit, le module utilise un modèle clé/valeur typé. On peut ajouter une caractéristique sans développement.
- **Évolution du modèle de données en douceur** : l'ancienne liste fixe de catégories a été doublée d'un référentiel hiérarchique. Une fonction de reprise idempotente, appelée à chaque mise à jour, assure la transition sans perte et sans écraser les choix de l'utilisateur.
- **Hiérarchie des besoins** : grâce à `child_of`, une catégorie « Ciment » couvre aussi ses sous-catégories, ce qui permet des besoins plus ou moins précis.
- **Historique** : une nomenclature maison qui existait dans ce module a été retirée au profit des nomenclatures natives, gérées désormais dans `miro_construction_bom`.

## 10. Limites et pistes d'amélioration

- **Documentation interne obsolète** : le `README.md` du module décrit des champs (densité, poids unitaire, diamètre d'acier…) et un emplacement de menu (Inventaire > Construction) qui ne correspondent plus au code.
- **Affichage des types** : la méthode `name_get` qui devait afficher « Nom [Catégorie] » est l'ancienne API ; en Odoo 17, c'est `_compute_display_name` qui est utilisé, ce suffixe n'est donc vraisemblablement pas affiché.
- **Double référentiel** : la liste fixe `category` et la catégorie de matériau coexistent, ce qui peut prêter à confusion.
- **Pas d'unicité** du code de catégorie de matériau, alors que la reprise recherche les catégories par code.
- **Menus** : le module crée sa propre racine « Construction », distincte de celle de `miro_construction_project` ; avec les deux modules installés, deux applications portent le même nom.
- Pistes (en partie listées dans le README) : unité « sac de 50 kg » liée au conditionnement, fiche technique PDF du matériau, normes qualité (NF EN 197-1), calcul du volume ou du poids en stock.
