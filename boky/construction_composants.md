# Gestion des composants par niveau (`construction_composants`)

> Ce petit module autonome décrit un bâtiment sous la forme projet, niveaux, composants (semelles, murs, poteaux, dalles…), avec leurs dimensions et, pour les murs, leurs faces orientées. C'est un prototype de structuration des données du bâtiment, non relié aux autres modules.

| Fiche | |
|---|---|
| Nom technique | `construction_composants` |
| Version | 17.0.1.0.0 |
| Catégorie | Construction |
| Dépend de | `base` |
| Utilisé par | aucun module |
| Auteur / licence | « Votre société » (valeur par défaut du manifeste) / LGPL-3 |

## 1. Le besoin métier

Avant de chiffrer ou de planifier un chantier, il faut inventorier ce qui va être construit : à chaque niveau (fondation, rez-de-chaussée R+0, étage R+1…), combien de semelles, de poteaux, de murs, et de quelles dimensions. Pour un mur, l'orientation (nord, sud…) et le côté (intérieur, extérieur) comptent, par exemple pour l'enduit ou la peinture.

Ce module propose une structure simple pour saisir cet inventaire.

## 2. Fonctionnalités

### Projets et niveaux

L'utilisateur crée un **projet**, puis ses **niveaux** (Fondation, R+0, R+1…) ordonnés par une séquence. Le projet calcule le nombre de niveaux et de composants ; chaque niveau calcule son nombre de composants.

### Types de composants

L'utilisateur définit des types (Semelle, Mur, Poteau, Dalle…) avec un code, la liste des **dimensions attendues** (longueur, largeur, hauteur, épaisseur, chacune en m, cm ou mm) et une option **« Gère les faces »** pour les types comme le mur.

### Composants

Un composant porte une référence, un niveau (le projet en découle), un type et une quantité. Quand l'utilisateur choisit le type, les lignes de dimensions attendues sont pré-remplies : il n'a plus qu'à saisir les valeurs. Il peut aussi saisir des **faces** : orientation (nord, sud, est, ouest), type (intérieure, extérieure), longueur et hauteur en mètres.

## 3. Qui l'utilise et comment

Utilisateur visé : bureau d'études ou métreur (tout utilisateur interne).

1. Paramétrer les types : « Semelle » avec longueur, largeur, hauteur ; « Mur » avec « Gère les faces ».
2. Créer le projet « Villa X » et ses niveaux Fondation, R+0, R+1.
3. Créer les composants : « S1 », semelle, niveau Fondation, quantité 8 ; saisir les dimensions pré-remplies.
4. Pour un mur, ajouter ses faces (nord extérieure, 5 m x 2,8 m…).

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `construction.projet` | Projet de construction | `name`, `active`, `niveau_ids`, `niveau_count`, `composant_count` |
| `construction.niveau` | Niveau du bâtiment | `name`, `sequence`, `projet_id`, `composant_ids`, `composant_count` |
| `construction.type.composant` | Type de composant | `name`, `code`, `gere_les_faces`, `attribut_ids` |
| `construction.type.composant.attribut` | Dimension attendue pour un type | `type_id`, `name`, `unite`, `sequence` |
| `construction.composant` | Composant concret | `name`, `niveau_id`, `projet_id` (déduit), `type_id`, `quantite`, `dimension_ids`, `face_ids` |
| `construction.composant.dimension` | Valeur d'une dimension | `composant_id`, `name`, `valeur`, `unite` |
| `construction.composant.face` | Face orientée d'un composant | `composant_id`, `orientation`, `type_face`, `longueur`, `hauteur` |

Relations : un projet contient des niveaux, un niveau contient des composants, un composant a des dimensions et des faces. La suppression d'un projet supprime en cascade ses niveaux, leurs composants et leurs dimensions et faces.

## 5. Règles métier et calculs

- **Unicités** : un nom de niveau par projet (`models/construction_niveau.py`) ; un nom de type unique (`models/construction_type_composant.py`).
- **Quantité positive** (`models/construction_composant.py`) : contrainte SQL `quantite > 0`.
- **Pré-remplissage** (`models/construction_composant.py`, `_onchange_type_id`) : changer de type efface les dimensions saisies et les remplace par celles du nouveau type.
- **Compteurs** (`models/construction_projet.py`, `models/construction_niveau.py`) : nombre de niveaux et de composants calculés à l'affichage (non stockés).
- **Projet déduit** : le projet d'un composant est celui de son niveau (champ lié stocké).
- Aucun calcul de surface ou de volume n'est fait à partir des dimensions.

## 6. Interfaces

- **Menu** : application **Construction** avec Projets, Niveaux, Composants, Types de composant.
- **Vues** : quatre actions liste/formulaire ; aucune vue n'est définie explicitement, Odoo génère donc des vues par défaut.
- Pas de rapport, d'assistant, de route HTTP, de tâche planifiée ni de JavaScript.

## 7. Sécurité et droits d'accès

Tous les modèles sont ouverts en lecture, écriture, création et suppression à tout utilisateur interne (`base.group_user`). Pas de groupe dédié ni de règle d'enregistrement.

## 8. Intégration avec les autres modules

Aucune. Le module ne dépend que de `base` et n'est utilisé par aucun autre module. Ses notions (projet, niveau, élément, dimensions) sont traitées de façon plus complète dans `miro_construction_project` (éléments, niveaux, métrés, phases), avec lequel il n'a pas de lien.

## 9. Points techniques notables

- **Paramétrage piloté par les données** : les dimensions attendues sont définies sur le type et recopiées à la création, ce qui évite de coder un champ par dimension.
- **Hiérarchie projet / niveau / composant** avec suppression en cascade et projet déduit stocké, permettant de filtrer les composants par projet.
- Ce module illustre une première approche de modélisation du bâtiment, utile pour montrer l'évolution vers le modèle plus riche de `miro_construction_project`.

## 10. Limites et pistes d'amélioration

- **Prototype** : pas de vues dédiées (formulaires générés automatiquement, donc sans mise en page des dimensions et faces), pas d'intégration avec les projets Odoo (`project.project`) ni avec les autres modules.
- **Doublon fonctionnel** : son propre modèle de projet et sa racine de menu « Construction » font double emploi avec `miro_construction_project`.
- **Petites anomalies** : un caractère parasite (accent grave) traîne dans le fichier de vues ; les dimensions et faces ne sont pas exploitées (pas de surface ni de volume calculés) ; une face n'est pas contrôlée selon l'option « Gère les faces » du type ; le changement de type efface sans avertissement les dimensions saisies.
- Pistes : vues formulaire soignées, calcul automatique des métrés (volume de béton, surface de mur), fusion avec `miro_construction_project` ou retrait du module.
