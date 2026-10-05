# construction_product_management

Module Odoo 17 qui étend `product.template` pour gérer les matériaux de
construction (ciment, sable, gravier, acier, brique, parpaing, bois...).

## Installation

1. Copier le dossier `construction_product_management` dans votre répertoire
   `addons` (ou un chemin listé dans `addons_path`).
2. Redémarrer Odoo et activer le **mode développeur**.
3. Aller dans **Apps > Mettre à jour la liste des Apps**.
4. Rechercher « Construction Product Management » et cliquer sur **Installer**.

## Contenu du module

- **Modèle `construction.material.type`** : catalogue configurable des
  sous-types de matériaux (ex : « Ciment CPJ 42.5 », « Sable de rivière 0/4 »),
  rattachés à une catégorie générale (ciment, sable, gravier, acier, bois,
  brique, parpaing, carrelage, peinture, autre).
- **Extension de `product.template`** :
  - `is_construction_material` : active les champs spécifiques.
  - `construction_material_type_id` / `construction_category`.
  - Champs physiques : `density`, `unit_weight`, `volume_per_unit`.
  - Champs ciment : `cement_type`, `resistance_class`.
  - Champs sable/gravier : `granulometry`, `material_origin`.
  - Champs acier : `steel_diameter`, `steel_grade`, `bar_length`.
  - `packaging_type` (sac, vrac, palette, botte, unité, m³, tonne).
- **Vues** : onglet dédié dans la fiche produit, colonnes optionnelles en
  liste, filtres et regroupement par catégorie de matériau.
- **Menu** : `Inventaire > Construction` avec deux sous-menus
  (« Matériaux de construction » et « Types de matériaux »).
- **Données de démonstration** : quelques types de matériaux préconfigurés
  (chargés via `data/` avec `noupdate="1"`, donc modifiables sans être
  écrasés lors d'une mise à jour du module).

## Étapes suivantes possibles

- Ajouter une unité de mesure personnalisée (ex : sac de 50 kg) via
  `uom.uom` et la relier automatiquement selon `packaging_type`.
- Ajouter un calcul automatique du volume total en stock
  (`qty_available * volume_per_unit`).
- Lier une checklist qualité / norme (NF EN 197-1 pour le ciment, etc.).
- Ajouter un rapport PDF (fiche technique matériau) avec le module `pdf`.
