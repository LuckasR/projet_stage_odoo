# Personnalisation du PDF de facture (`miro_custom_pdf`)

> Petit module d'expérimentation qui modifie le modèle PDF de facture d'Odoo : titre « Facture N° », message de remerciement et classe CSS sur le tableau des lignes. Il sert surtout de démonstration des techniques d'héritage de rapport.

| Fiche | |
|---|---|
| Nom technique | `miro_custom_pdf` |
| Version | 17.0.1.0.0 |
| Catégorie | Accounting |
| Dépend de | `account` |
| Utilisé par | Aucun module |
| Auteur / licence | Non renseignés dans le manifeste |

## 1. Le besoin métier

Adapter l'apparence de la facture PDF standard d'Odoo aux habitudes de l'entreprise sans modifier le code d'Odoo. Dans les faits, le module a un caractère **pédagogique** : ses blocs sont commentés « Exemple 1 », « Exemple 2 », « Exemple 3 » et illustrent trois façons de personnaliser un rapport. Le besoin de mise en page professionnelle a ensuite été couvert de façon complète par `miro_report_layout`.

## 2. Fonctionnalités

### 2.1 Titre de facture reformulé

Le titre de la facture est remplacé par « Facture N° » suivi du numéro (le numéro n'est pas affiché tant que la facture est un brouillon sans numéro).

### 2.2 Message de remerciement

Le texte « Merci pour votre confiance ! » est ajouté sous le bloc des informations (date de facture, échéance, origine).

### 2.3 Classe CSS sur le tableau des lignes

Une classe `ma-classe-tableau` est ajoutée au tableau des lignes de facture, en vue d'un style personnalisé. Aucun style n'y est associé pour l'instant.

## 3. Qui l'utilise et comment

Comptables et commerciaux qui impriment ou envoient des factures : les modifications s'appliquent automatiquement à l'impression, sans paramétrage.

## 4. Modèle de données

Aucun modèle créé ni étendu ; le module ne contient pas de code Python.

## 5. Règles métier et calculs

Une seule condition : le numéro de facture n'est affiché que s'il est différent de « / » (valeur d'une facture brouillon), voir `report/report_invoice.xml`.

## 6. Interfaces

| Élément | Fichier | Description |
|---|---|---|
| Gabarit QWeb `report_invoice_document_inherit` | `report/report_invoice.xml` | Hérite de `account.report_invoice_document` (gabarit natif de la facture) et applique trois modifications par XPath |
| Feuille de style | `static/src/css/report_style.css` | Fichier vide et non déclaré dans le manifeste |

Aucun menu, aucune vue écran.

## 7. Sécurité et droits d'accès

Aucun droit spécifique : le module ne crée pas de données et suit les droits du module Comptabilité.

## 8. Intégration avec les autres modules

Le module modifie le même gabarit de facture que `miro_report_layout`. Les deux ne dépendent pas l'un de l'autre, si bien que leur ordre d'application n'est pas garanti s'ils sont installés ensemble (voir limites).

## 9. Points techniques notables

Le fichier illustre les trois opérations d'héritage de vue les plus courantes en Odoo, utiles à présenter dans un rapport de stage :

| Opération XPath | Exemple dans le module |
|---|---|
| `position="after"` (ajouter) | Message après le bloc `informations` |
| `position="replace"` (remplacer) | Remplacement complet du titre `h2` |
| `position="attributes"` (modifier un attribut) | Ajout d'une classe CSS au tableau des lignes |

## 10. Limites et pistes d'amélioration

- **Module inachevé** : fichier CSS vide et non chargé, classe `ma-classe-tableau` sans style, auteur et licence absents du manifeste, commentaire « ou 'sale' pour les devis » laissé dans les dépendances.
- **Titre trop simplifié** : le remplacement du `h2` affiche « Facture N° » pour tous les types de pièces, y compris les avoirs, les factures fournisseur et les brouillons, alors que le titre natif les distingue.
- **Recouvrement avec `miro_report_layout`** : les deux modules modifient la même facture, et ils sont installés ensemble sur la base de développement ; le remplacement du titre peut faire perdre la mise en valeur du numéro apportée par `miro_report_layout`, selon l'ordre de chargement. Il serait cohérent de fusionner ce qu'il reste d'utile (le message de remerciement) dans `miro_report_layout` et de désinstaller ce module.
