# Mise en page des documents Miro Construction (`miro_report_layout`)

> Ce module donne à tous les documents PDF d'Odoo (factures, bons de commande, bons de livraison, bulletins de paie...) une identité visuelle unique « Miro Construction » : en-tête de marque, pied de page avec les mentions légales malgaches, tableaux aux couleurs de la société et, pour les factures, coordonnées bancaires, montant en toutes lettres et zone de cachet.

| Fiche | |
|---|---|
| Nom technique | `miro_report_layout` |
| Version | 17.0.1.0.0 |
| Catégorie | Hidden/Tools (module technique, non affiché comme application) |
| Dépend de | `web`, `account` |
| Utilisé par | `miro_hr_paie` (bulletin de paie) |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Les documents envoyés aux clients, fournisseurs et salariés sont la vitrine de l'entreprise. Les mises en page natives d'Odoo (Light, Boxed, Bold, Striped) sont génériques et ne prévoient pas certains usages malgaches :

- les identifiants légaux attendus sur une pièce commerciale à Madagascar : **NIF** (numéro d'identification fiscale), **STAT** (numéro statistique) et **RCS** (registre du commerce) ;
- la formule d'usage sur les factures : « Arrêtée la présente facture à la somme de ... » suivie du montant en toutes lettres ;
- les coordonnées bancaires pour le règlement, et une zone « Cachet et signature ».

Le module répond à ce besoin en une seule fois pour tous les documents, plutôt que de retoucher chaque rapport séparément.

## 2. Fonctionnalités

### 2.1 Une mise en page « Miro Construction » sélectionnable

Dans **Paramètres > Configurer la mise en page des documents**, une nouvelle mise en page « Miro Construction » apparaît en tête de liste, avec un aperçu (image et PDF d'exemple), à côté des mises en page natives. Une fois choisie, elle s'applique à tous les documents PDF qui utilisent la mise en page externe standard d'Odoo.

### 2.2 En-tête de marque

- À gauche : le logo de la société ; si aucun vrai logo n'est chargé (logo d'usine « Your logo »), le nom de l'entreprise est écrit en **lettrage** sur deux tons (par exemple « Miro » en couleur principale, « Construction » en couleur secondaire), suivi du slogan éventuel.
- À droite : nom, adresse, téléphone, e-mail et site web.
- Sous l'en-tête : un double filet aux couleurs de la société.

### 2.3 Corps du document habillé

- Blocs d'adresse présentés comme des cartes étiquetées « DESTINATAIRE » et « INFORMATIONS ».
- Bloc des dates et références sous forme de cartes.
- Tableaux des lignes avec en-tête coloré, lignes de section mises en évidence, totaux sur fond de couleur principale.
- Titres en police Montserrat grasse, en majuscules.

### 2.4 Pied de page légal

Sur chaque page : nom de la société, NIF, STAT et RCS ; contacts ; pagination « Page X / Y » et, si l'option Odoo est active, le numéro du document ; texte de pied de page libre de la société.

### 2.5 Facture enrichie

Sur les factures et avoirs clients :

| Ajout | Détail |
|---|---|
| Numéro mis en valeur | Le numéro de la pièce prend la couleur secondaire dans le titre |
| Montant en toutes lettres | « Arrêtée la présente facture à la somme de ... » (ou « Arrêté le présent avoir ... » pour un avoir) |
| Coordonnées bancaires | Banque, titulaire, numéro de compte, SWIFT/BIC, référence de paiement à rappeler, placés à gauche des totaux |
| Cachet et signature | Zone « Pour <société> » à droite sous les totaux |

### 2.6 Champ « N° STAT » sur la société

Un champ **N° STAT** est ajouté sur la fiche société, juste après le numéro de registre, pour être imprimé dans le pied de page.

### 2.7 Configuration automatique à l'installation

À l'installation, chaque société reçoit la mise en page Miro, les couleurs bleu nuit (#1B2A41) et ocre chantier (#E8A317), le montant en lettres activé sur les factures, et le nom « Miro Construction » si elle portait encore le nom d'usine. Les valeurs déjà personnalisées (couleurs, nom) ne sont pas écrasées.

## 3. Qui l'utilise et comment

| Profil | Usage |
|---|---|
| Administrateur | Installe le module, renseigne logo, NIF, STAT, RCS et compte bancaire de la société, ajuste éventuellement les couleurs |
| Comptable / commercial | Imprime ou envoie factures, devis, bons de commande : la mise en page s'applique sans action particulière |
| Service RH | Imprime les bulletins de paie (`miro_hr_paie`), qui reprennent la même identité |

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `res.company` (hérité) | Société émettrice des documents | `miro_stat` (N° STAT, nouveau) ; champs natifs réutilisés : `vat` (NIF), `company_registry` (RCS), `primary_color`, `secondary_color`, `external_report_layout_id`, `display_invoice_amount_total_words` |
| `report.layout` (donnée) | Entrée « Miro Construction » dans le choix des mises en page | `view_id`, `image`, `pdf`, `sequence` |

## 5. Règles métier et calculs

- **Branding initial** (`models/res_company.py`, `_miro_apply_branding`) : pour chaque société, applique la mise en page Miro ; ne remplace le nom que s'il vaut « My Company » ou « YourCompany », les couleurs que si elles sont vides, et active le montant en lettres s'il ne l'est pas.
- **Logo ou lettrage** (`views/report_layout_templates.xml`) : le logo est affiché seulement si la société a un logo qui n'est pas celui d'usine ; sinon le nom est coupé au premier espace pour former un lettrage sur deux tons.
- **Compte bancaire affiché** (`views/report_invoice_templates.xml`) : le compte choisi sur la facture, sinon le premier compte bancaire de la société ; le bloc n'apparaît que pour les factures et avoirs clients et seulement si un compte existe.
- **Couleurs** : celles de la société, avec repli sur bleu nuit / ocre si elles sont vides.

## 6. Interfaces

| Élément | Fichier | Description |
|---|---|---|
| Gabarit QWeb `external_layout_miro` | `views/report_layout_templates.xml` | Mise en page externe complète : en-tête, corps, pied de page |
| Gabarit `styles_company_report_miro` | `views/report_layout_templates.xml` | Extension de la feuille de style générée par société (`web.styles_company_report`) pour injecter les couleurs |
| Gabarit `report_invoice_document_miro` | `views/report_invoice_templates.xml` | Extension du modèle de facture natif `account.report_invoice_document` |
| Vue formulaire société | `views/res_company_views.xml` | Ajout du champ N° STAT |
| Donnée `report_layout_miro` | `data/report_layout_data.xml` | Ajout dans l'assistant de choix de mise en page |
| Appel `_miro_apply_branding` | `data/company_branding.xml` | Configuration des sociétés à l'installation |
| Feuille de style | `static/src/scss/report_miro.scss` | Structure, typographie, espacements, gris neutres |
| Aperçus | `static/img/preview_miro.png`, `preview_miro.pdf` | Vignette et exemple affichés dans l'assistant |

QWeb est le moteur de gabarits d'Odoo utilisé pour générer les rapports ; une « mise en page externe » est le cadre (en-tête et pied de page) dans lequel chaque document insère son contenu. Aucun menu n'est ajouté.

## 7. Sécurité et droits d'accès

Aucun groupe ni droit d'accès spécifique : le module ne crée pas de modèle. Le champ N° STAT suit les droits de la fiche société (modifiable par les administrateurs). Les documents restent soumis aux droits des modules qui les produisent (comptabilité, achats, paie...).

## 8. Intégration avec les autres modules

- **Tous les rapports PDF** qui appellent `web.external_layout` héritent de la mise en page dès qu'elle est sélectionnée pour la société : factures, devis, bons de commande, bons de livraison, rapports des modules Miro.
- **`account`** : la facture est enrichie par héritage du gabarit natif.
- **`miro_hr_paie`** dépend de ce module : son bulletin de paie appelle `web.external_layout`, réutilise les classes CSS du module (`miro-doc-number`, `miro-amount-words`) et imprime le champ `miro_stat`.

## 9. Points techniques notables

- **Habiller plutôt que remplacer** : la facture native n'est pas réécrite ; le module ajoute ou modifie quelques blocs par XPath (langage de ciblage d'éléments dans un document XML). Les autres modules qui modifient la facture (taxes, QR code, paiements) continuent de trouver leurs blocs.
- **Intégration au mécanisme natif des couleurs** : Odoo génère une feuille de style par société à partir de ses couleurs ; le module y ajoute une branche pour sa mise en page, exactement comme les mises en page natives. Les couleurs sont donc modifiables depuis l'interface standard, sans toucher au code.
- **Contraintes de wkhtmltopdf** : l'outil de conversion HTML vers PDF d'Odoo ne gère pas bien le flexbox ni les variables CSS ; la mise en page utilise des tableaux HTML et des variables SCSS compilées.
- **Polices** : Odoo ne déclare que la graisse normale de Montserrat ; le module déclare les graisses semi-grasse, grasse et extra-grasse à partir des fichiers déjà livrés avec Odoo.
- **Subtilité d'installation** : pendant l'installation, Odoo n'applique pas encore les extensions de vues du module en cours de chargement ; le code vide le cache des gabarits et régénère la feuille de style avec le contexte `install_module`, faute de quoi les couleurs seraient perdues.
- **Configuration non destructive** : le branding initial ne remplace que les valeurs d'usine.

## 10. Limites et pistes d'amélioration

- **Mentions en dur** : libellés en français (« DESTINATAIRE », « COORDONNÉES BANCAIRES », « Arrêtée la présente facture... ») écrits directement dans les gabarits et la feuille de style ; ceux placés dans le CSS (`content:`) ne sont pas traduisibles.
- **Spécifique à Madagascar** : NIF, STAT et RCS conviennent au contexte local ; une société d'un autre pays devrait adapter le pied de page.
- **Facture seulement** : coordonnées bancaires, montant en lettres et cachet ne sont ajoutés que sur la facture ; les devis et bons de commande ne bénéficient que de la mise en page générale.
- **Application à toutes les sociétés** : à l'installation, la mise en page est imposée à toutes les sociétés de la base (les couleurs et noms personnalisés étant conservés).
- Pas de tests automatisés du rendu PDF.
