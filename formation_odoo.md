# Formation Odoo — Du débutant à l'avancé

> Odoo 17 — Framework MVC (Python / XML / JavaScript OWL)

---

## Table des matières

1. [Architecture d'Odoo](#1-architecture-dodoo)
2. [Le `__manifest__.py`](#2-le-__manifest__py)
3. [Les Modèles (Models)](#3-les-modèles-models)
4. [Les Vues (Views)](#4-les-vues-views)
5. [Héritage et Extension](#5-héritage-et-extension)
6. [Sécurité](#6-sécurité)
7. [Séquence et Code automatisé](#7-séquence-et-code-automatisé)
8. [Wizards (assistants)](#8-wizards-assistants)
9. [QWeb / Rapports (PDF / HTML)](#9-qweb--rapports-pdf--html)
10. [Contrôleurs (Routes HTTP / API)](#10-contrôleurs-routes-http--api)
11. [Actions (ir.actions)](#11-actions-iractions)
12. [Décorateurs avancés](#12-décorateurs-avancés)
13. [Traductions et localisation](#13-traductions-et-localisation)
14. [Tests unitaires](#14-tests-unitaires)
15. [Scheduled Actions (CRON)](#15-scheduled-actions-cron)
16. [Mixins intégrés](#16-mixins-intégrés)
17. [Personnalisation avancée](#17-personnalisation-avancée)
18. [Pièges et bonnes pratiques](#18-pièges-et-bonnes-pratiques)
19. [Serveur Odoo](#19-serveur-odoo)

---

## 1. Architecture d'Odoo

Odoo est un framework **MVC (Modèle-Vue-Contrôleur)** écrit en **Python** avec des vues en **XML** et du **JavaScript (OWL)**.

| Couche | Technologie | Rôle |
|---|---|---|
| Modèle (Model) | Python (`odoo.models`) | Données, logique métier, ORM |
| Vue (View) | XML | Interface utilisateur |
| Contrôleur | Python (`odoo.http`) | Routes HTTP / API |
| Template | QWeb (XML) | PDF, emails, pages web |

### Arborescence d'un module Odoo

```
mon_module/
├── __manifest__.py       # Descriptif du module
├── __init__.py           # Init Python
├── models/               # Modèles
│   ├── __init__.py
│   └── mon_modele.py
├── views/                # Vues XML
│   └── mes_vues.xml
├── security/             # Droits d'accès
│   └── ir.model.access.csv
├── data/                 # Données initiales / démo
├── static/               # Assets (CSS, JS, images)
│   ├── description/
│   └── src/
├── report/               # Rapports QWeb
├── controllers/          # Contrôleurs HTTP
└── wizard/               # Assistants (wizards)
```

---

## 2. Le `__manifest__.py`

C'est la carte d'identité du module.

```python
{
    'name': "Mon Module",
    'version': '17.0.1.0.0',
    'depends': ['base', 'sale'],  # Dépendances
    'category': 'Sales',
    'application': True,          # Visible dans Apps
    'author': "Moi",
    'website': "https://example.com",
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/mes_vues.xml',
        'views/menu.xml',
    ],
    'demo': [
        'data/demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

---

## 3. Les Modèles (Models)

### 3.1 Modèle basique

```python
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class BibliothequeLivre(models.Model):
    _name = 'bibliotheque.livre'       # Identifiant technique (unique)
    _description = "Livre"
    _rec_name = 'titre'                # Champ utilisé pour l'affichage (sinon 'name')
    _order = 'date_publication desc'   # Ordre par défaut
    _inherit = 'mail.thread'           # Héritage simple (ajoute des champs)
    _sql_constraints = [               # Contraintes SQL
        ('titre_unique', 'UNIQUE(titre)', "Le titre doit être unique"),
    ]

    titre = fields.Char(string="Titre", required=True)
    pages = fields.Integer(string="Nombre de pages")
    prix = fields.Float(string="Prix", digits=(10, 2))
    resume = fields.Text(string="Résumé")
    date_publication = fields.Date(string="Date de publication")
    actif = fields.Boolean(string="Actif", default=True)
```

### 3.2 Types de champs principaux

```python
# --- Basiques ---
champs_char     = fields.Char(string="Texte court", size=100, required=True)
champs_text     = fields.Text(string="Texte long")
champs_integer  = fields.Integer(string="Nombre entier")
champs_float    = fields.Float(string="Nombre décimal", digits=(10, 2))
champs_boolean  = fields.Boolean(string="Oui/Non", default=False)
champs_date     = fields.Date(string="Date")
champs_datetime = fields.Datetime(string="Date et heure")
champs_selection = fields.Selection([
    ('draft', 'Brouillon'),
    ('confirm', 'Confirmé'),
    ('done', 'Terminé'),
    ('cancel', 'Annulé'),
], string="Statut", default='draft')
champs_html     = fields.Html(string="HTML")
champs_binary   = fields.Binary(string="Fichier")
champs_monetary = fields.Monetary(string="Montant", currency_field='currency_id')

# --- Relationnels ---
champs_many2one = fields.Many2one(
    'res.partner',          # Modèle cible
    string="Client",
    required=True,
    ondelete='cascade'      # cascade / restrict / set null
)

champs_one2many = fields.One2many(
    'vente.ligne',          # Modèle cible (doit avoir Many2one inverse)
    'vente_id',             # Champ inverse dans le modèle cible
    string="Lignes de vente"
)

champs_many2many = fields.Many2many(
    'res.partner',
    'etiquette_partner_rel', # Table de liaison (optionnel)
    'etiquette_id',          # Colonne vers ce modèle
    'partner_id',            # Colonne vers l'autre modèle
    string="Contacts"
)

# --- Spéciaux ---
champs_reference = fields.Reference([
    ('res.partner', 'Contact'),
    ('res.users', 'Utilisateur'),
], string="Référence")

champs_image = fields.Image(string="Image", max_width=800, max_height=800)
```

### 3.3 Attributs avancés de champs

```python
champs = fields.Char(
    string="Libellé",                # Texte affiché dans l'interface
    required=True,                    # Champ obligatoire
    readonly=True,                    # Lecture seule
    default='Valeur',                 # Valeur par défaut
    default=lambda self: self.env.user,  # Valeur par défaut dynamique
    help="Texte d'aide",              # Bulle d'aide
    index=True,                       # Index SQL (performance)
    copy=False,                       # Ne pas copier en duplicant
    tracking=True,                    # Suivi des modifications (mail.thread)
    groups='base.group_user',         # Restreint à un groupe
    invisible=True,                   # Caché
    translate=True,                   # Traduisible
    sanitize=True,                    # Nettoie le HTML
    related='client.email',           # Champ lié (remonte via relation)
    compute='_calc_champs',           # Champ calculé
    inverse='_inv_champs',            # Inverse d'un champ calculé
    store=True,                       # Stocker en DB (pour compute)
    currency_field='currency_id',     # Pour fields.Monetary
    prefetch=True,                    # Préchargement optimisé
)
```

### 3.4 Champs calculés et contraintes

```python
# --- Champ calculé simple ---
prix_ttc = fields.Float(
    string="Prix TTC",
    compute='_calc_prix_ttc',
    store=True,                           # Stocké en DB
    inverse='_set_prix_ttc'               # Permet d'écrire sur ce champ
)

@api.depends('prix_ht', 'taxe')
def _calc_prix_ttc(self):
    for rec in self:
        rec.prix_ttc = rec.prix_ht * (1 + rec.taxe / 100)

def _set_prix_ttc(self):
    """Inverse : quand on écrit prix_ttc, recalcule prix_ht"""
    for rec in self:
        rec.prix_ht = rec.prix_ttc / (1 + rec.taxe / 100)


# --- Champ calculé avec recherche ---
nom_complet = fields.Char(
    string="Nom complet",
    compute='_calc_nom_complet',
    search='_search_nom_complet'   # Permet la recherche sur ce champ
)

@api.depends('prenom', 'nom')
def _calc_nom_complet(self):
    for rec in self:
        rec.nom_complet = f"{rec.prenom} {rec.nom}"

def _search_nom_complet(self, operator, value):
    """Permet de filtrer sur le champ calculé"""
    return ['|', ('prenom', operator, value), ('nom', operator, value)]


# --- Contraintes Python ---
@api.constrains('date_debut', 'date_fin')
def _check_dates(self):
    for rec in self:
        if rec.date_fin and rec.date_debut and rec.date_fin < rec.date_debut:
            raise ValidationError(
                "La date de fin doit être postérieure à la date de début"
            )


# --- Contrainte SQL ---
_sql_constraints = [
    ('code_unique', 'UNIQUE(code)', "Le code doit être unique"),
    ('prix_positif', 'CHECK(prix > 0)', "Le prix doit être positif"),
]
```

### 3.5 L'ORM en détail

```python
# --- CRUD ---
record = self.env['bibliotheque.livre'].create({
    'titre': "1984",
    'pages': 328,
})
record.write({'pages': 330})           # Modifier
record.read(['titre', 'pages'])        # Lire (retourne liste de dicts)
record.unlink()                        # Supprimer

# --- Recherche (Search) ---
records = self.env['bibliotheque.livre'].search([
    ('pages', '>', 100),
    ('actif', '=', True),
    '|',                               # OU logique
        ('titre', 'ilike', 'orwell'),
        ('auteur', 'ilike', 'orwell'),
], limit=10, offset=0, order='date_publication desc')

# Recherche avec count
nb = self.env['bibliotheque.livre'].search_count([('actif', '=', True)])

# --- Parcourir (Browse) ---
record = self.env['bibliotheque.livre'].browse([1, 2, 3])
record = self.env['bibliotheque.livre'].browse(1)    # Un seul

# --- Méthodes de recherche avancée ---
records = self.env['bibliotheque.livre'].name_search(
    '1984', operator='ilike', limit=10
)

# --- Méthodes d'enregistrement ---
record.ensure_one()                       # Vérifie qu'il y a exactement 1 record
records.filtered(lambda r: r.actif)        # Filtrer en Python
records.filtered('actif')                  # Raccourci (même chose)
records.mapped('titre')                    # Récupérer une liste de valeurs
records.mapped(lambda r: r.auteur_id.name) # Mapping avec traversée
records.sorted(key='date_publication', reverse=True)  # Trier
records[:5]                               # Trancher (paginer)

# --- Exists et vérifications ---
if record.exists():
    # L'enregistrement existe toujours en DB
    pass

record.check_access_rights('read')         # Vérifie les droits
record.check_access_rule('read')           # Vérifie les rules
record.sudo()                              # Contourner les droits
record.with_user(user)                     # En tant qu'un autre utilisateur

# --- SQL brut ---
self.env.cr.execute(
    "SELECT id, name FROM res_partner WHERE id = %s", [1]
)
rows = self.env.cr.fetchall()              # Tous les résultats
row = self.env.cr.fetchone()               # Un seul résultat
```

### 3.6 Décorateurs et API

```python
# --- @api.depends : pour les champs calculés ---
@api.depends('lignes.prix_total')
def _calc_total(self):
    ...

# --- @api.onchange : réagit à un changement UI (ne sauvegarde PAS) ---
@api.onchange('pays_id')
def _onchange_pays(self):
    if self.pays_id:
        self.devise = self.pays_id.devise_id
    return {
        'warning': {'title': "Attention", 'message': "Vérifiez la devise"}
    }

# --- @api.constrains : validation de données ---
@api.constrains('email')
def _check_email(self):
    ...

# --- @api.model / @api.model_create_multi ---
@api.model
def _default_category(self):
    return self.env['categorie'].search([], limit=1)

@api.model_create_multi
def create(self, vals_list):
    """Override de create pour traiter plusieurs enregistrements"""
    for vals in vals_list:
        if vals.get('ref', _('Nouveau')) == _('Nouveau'):
            vals['ref'] = self.env['ir.sequence'].next_by_code('mon.code')
    return super().create(vals_list)

# --- @api.returns : type de retour déclaré ---
@api.returns('bibliotheque.livre')
def get_livres_actifs(self):
    ...

# --- Contexte ---
records.with_context(force_company=1, lang='fr_FR').write(...)
records.with_company(1).write(...)
records.with_user(admin_user).write(...)
```

### 3.7 Environnement (`self.env`)

```python
# self.env est l'environnement courant
self.env.user           # Utilisateur connecté (res.users)
self.env.company        # Société courante (res.company)
self.env.lang           # Langue courante
self.env.cr             # Curseur SQL (base de données)
self.env.uid            # ID utilisateur

# Créer un environnement différent
self.env['res.partner'].sudo()
self.env['res.partner'].with_user(user)
self.env['res.partner'].with_context(lang='fr_FR')

# Accéder à un modèle
self.env['res.partner']
self.env['ir.sequence'].next_by_code('sale.order')

# Exécuter du SQL brut
self.env.cr.execute("UPDATE res_partner SET name = %s WHERE id = %s", ("New name", 1))
```

---

## 4. Les Vues (Views)

### 4.1 Vue Formulaire (`<form>`)

```xml
<form>
    <header>
        <button name="action_confirm" type="object"
                string="Confirmer" class="btn-primary"
                confirm="Confirmer cette action ?"/>
        <button name="action_reset" type="object"
                string="Reset" confirm="Annuler ?"/>
        <field name="state" widget="statusbar"
               statusbar_visible="draft,confirm,done"/>
    </header>

    <sheet>
        <div class="oe_title">
            <h1><field name="name" placeholder="Titre..."/></h1>
        </div>

        <group>
            <group string="Informations">
                <field name="date"/>
                <field name="personne" options="{'no_create': True}"/>
                <field name="montant" widget="monetary"/>
            </group>
            <group string="Détails">
                <field name="notes" widget="html"/>
                <field name="fichier" widget="binary"/>
            </group>
        </group>

        <notebook>
            <page string="Lignes" name="lines_page">
                <field name="ligne_ids">
                    <tree editable="bottom">
                        <field name="produit"/>
                        <field name="quantite"/>
                        <field name="prix_unitaire"/>
                    </tree>
                </field>
            </page>
            <page string="Notes">
                <field name="notes"/>
            </page>
        </notebook>
    </sheet>

    <div class="oe_chatter">
        <field name="message_ids" widget="mail_thread"/>
    </div>
</form>
```

### 4.2 Vue Arborescente / Liste (`<tree>`)

```xml
<tree editable="top"                     # top / bottom : édition inline
      default_order="date desc"
      multi_edit="1"                     # Édition multiple
      import="1"                         # Autoriser import CSV
      create="0"                         # Cacher le bouton Créer
      delete="0"                         # Cacher le bouton Supprimer
      onClick="action_open_record">      # Action au clic (JS)
    <field name="ref" invisible="1"/>
    <field name="name"/>
    <field name="date" widget="date"/>
    <field name="montant" sum="Total"/>
    <field name="state" widget="badge"
           decoration-warning="state == 'draft'"
           decoration-success="state == 'done'"
           decoration-danger="state == 'cancel'"/>
    <button name="action_open" type="object"
            string="Ouvrir" icon="fa-eye"/>
</tree>
```

### Décorations disponibles en Odoo 17

```xml
<tree>
    <field name="montant"
           decoration-danger="montant < 0"
           decoration-success="montant >= 1000"
           decoration-warning="montant < 100 and montant > 0"
           decoration-info="True"
           decoration-muted="state == 'cancel'"
           decoration-bf="True"          <!-- Gras -->
           decoration-it="True"          <!-- Italique -->
    />
</tree>
```

Raccourcis dans les `tree` :
- **`sum`** : somme en bas de colonne
- **`avg`** : moyenne
- **`widget="handle"`** : réordonnancement par glissé

### 4.3 Vue Kanban (tableau de bord visuel)

```xml
<kanban class="oe_kanban_margin">
    <field name="color"/>               <!-- Couleur de carte -->
    <field name="state"/>
    <field name="name"/>
    <templates>
        <t t-name="kanban-box">
            <div class="oe_kanban_card">
                <div class="oe_kanban_content">
                    <div class="o_kanban_record_top">
                        <field name="name"/>
                    </div>
                    <div class="o_kanban_record_body">
                        <field name="description"/>
                    </div>
                    <div class="o_kanban_record_bottom">
                        <field name="date" widget="date"/>
                    </div>
                </div>
            </div>
        </t>
    </templates>
</kanban>
```

### 4.4 Vue Graphique / Pivot

```xml
<graph type="bar">              <!-- bar / pie / line -->
    <field name="date" interval="month"/>   <!-- Intervalle temporel -->
    <field name="montant" type="measure"/>
    <field name="categorie" type="row"/>
</graph>

<pivot>
    <field name="date" interval="month"/>
    <field name="montant" type="measure"/>
    <field name="categorie" type="row"/>
    <field name="region" type="col"/>
    <field name="state"/>
</pivot>
```

### 4.5 Vue Recherche

```xml
<search>
    <field name="name" filter_domain="[
        '|', ('name', 'ilike', self), ('ref', 'ilike', self)
    ]"/>
    <filter name="mes_livres" string="Mes livres"
            domain="[('create_uid', '=', uid)]"/>
    <filter name="categorie" string="Catégorie"
            context="{'group_by': 'categorie_id'}"/>
    <separator/>
    <filter name="date_filter" string="Ce mois"
            date="date_publication"/>
    <group expand="0" string="Groupes">
        <filter name="groupe_client" string="Client"
                domain="[('partner_id', '!=', False)]"/>
    </group>
</search>
```

### 4.6 Widgets (rendus spéciaux pour les champs)

| Widget | Usage |
|---|---|
| `widget="statusbar"` | Barre d'étapes (champ selection) |
| `widget="progressbar"` | Barre de progression |
| `widget="monetary"` | Affichage monétaire |
| `widget="float_time"` | Durée (ex: 2.5 → 02:30) |
| `widget="float_factor"` | Pourcentage |
| `widget="integer"` | Compteur avec flèches |
| `widget="email"` | Email cliquable |
| `widget="phone"` | Téléphone cliquable |
| `widget="url"` | Lien cliquable |
| `widget="image"` | Aperçu image |
| `widget="html"` | Éditeur HTML riche |
| `widget="ace"` | Éditeur de code |
| `widget="many2many_tags"` | Tags pour les many2many |
| `widget="many2many_checkboxes"` | Checkboxes |
| `widget="radio"` | Boutons radio (selection) |
| `widget="badge"` | Badge coloré (selection) |
| `widget="handle"` | Poignée de réordonnancement |
| `widget="toggle_button"` | Bouton on/off |
| `widget="priority"` | Étoiles de priorité |
| `widget="pdf_viewer"` | Visionneuse PDF |
| `widget="dashboard"` | Tableau de bord (KPI) |

### 4.7 Attributs dynamiques (Odoo 17 — sans `attrs` ni `states`)

En Odoo 17, on utilise les attributs directs :

```xml
<!-- Au lieu de : attrs="{'invisible': [('state', '=', 'done')]}"
     on écrit directement : -->
<field name="champ" invisible="state == 'done'"
                    readonly="state != 'draft'"
                    required="state == 'confirm'"/>

<!-- Conditions multiples -->
<field name="champ" invisible="state == 'done' and categorie == 'speciale'"/>

<!-- Groupes de permissions -->
<field name="secret" groups="base.group_system"/>

<!-- Comparaisons avancées -->
<field name="champ" invisible="state in ('done', 'cancel')"/>
<field name="champ" invisible="montant > 1000"/>
```

---

## 5. Héritage et Extension

C'est la force d'Odoo — tout s'hérite sans modifier l'existant.

### 5.1 Héritage de modèle (classe Python)

```python
# --- Héritage simple : ajouter des champs à un modèle existant ---
class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    code_client = fields.Char(string="Code client", copy=False)

    def write(self, vals):
        # Code avant l'appel parent
        result = super().write(vals)
        # Code après l'appel parent
        return result


# --- Héritage par délégation ---
class Voiture(models.Model):
    _name = 'voiture'
    _inherits = {'fleet.vehicle': 'vehicle_id'}
    vehicle_id = fields.Many2one(
        'fleet.vehicle', required=True, ondelete='cascade'
    )


# --- Mixin (trait réutilisable) ---
class TrackVisibilityMixin(models.AbstractModel):
    _name = 'track.visibility.mixin'
    _description = "Track Visibility"

    last_seen = fields.Datetime(string="Dernière vue")


class MonModele(models.Model):
    _name = 'mon.modele'
    _inherit = ['track.visibility.mixin', 'mail.thread']
```

### 5.2 Héritage de vue (XML)

```xml
<!-- Héritage de vue : modifie une vue existante -->
<record id="view_partner_form_inherit" model="ir.ui.view">
    <field name="name">res.partner.form.inherit</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.view_partner_form"/>
    <field name="arch" type="xml">

        <!-- Insérer après un champ -->
        <field name="email" position="after">
            <field name="code_client"/>
        </field>

        <!-- Insérer avant -->
        <field name="name" position="before">
            <field name="title"/>
        </field>

        <!-- Remplacer -->
        <field name="comment" position="replace">
            <field name="code_client"/>
        </field>

        <!-- À l'intérieur -->
        <div class="oe_title" position="inside">
            <field name="code_client"/>
        </div>

        <!-- Au-dessus / en-dessous -->
        <notebook position="after">
            <div class="oe_chatter"/>
        </notebook>

        <!-- Attributs -->
        <field name="phone" position="attributes">
            <attribute name="invisible">1</attribute>
            <attribute name="widget">phone</attribute>
        </field>

        <!-- XPath avancé -->
        <xpath expr="//field[@name='category_id']" position="after">
            <field name="code_client"/>
        </xpath>

    </field>
</record>
```

### 5.3 Héritage de modèle de vue (extending views model)

```python
class IrUiViewInherit(models.Model):
    _inherit = 'ir.ui.view'

    description = fields.Text(string="Description de la vue")
```

---

## 6. Sécurité

### 6.1 Fichier CSV (droits d'accès)

`security/ir.model.access.csv` :

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_bibliotheque_livre_user,Bibliotheque Livre User,model_bibliotheque_livre,base.group_user,1,1,1,0
access_bibliotheque_livre_manager,Bibliotheque Livre Manager,model_bibliotheque_livre,base.group_system,1,1,1,1
```

### 6.2 Records Rules (règles par enregistrement)

`security/security.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_bibliotheque_livre_personnel" model="ir.rule">
        <field name="name">Voir seulement ses livres</field>
        <field name="model_id" ref="model_bibliotheque_livre"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('create_uid', '=', user.id)]</field>
        <field name="groups" eval="[(4, ref('base.group_user'))]"/>
        <field name="perm_read" eval="True"/>
        <field name="perm_write" eval="True"/>
        <field name="perm_create" eval="True"/>
        <field name="perm_unlink" eval="True"/>
    </record>
</odoo>
```

### 6.3 Sécurité au niveau champ

```python
champ_secret = fields.Char(groups='base.group_system')
champ_fiscal = fields.Char(groups='account.group_account_invoice')
```

---

## 7. Séquence et Code automatisé

```python
class BibliothequeLivre(models.Model):
    _name = 'bibliotheque.livre'

    ref = fields.Char(
        string="Référence", required=True,
        default=lambda self: _('Nouveau'),
        copy=False, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('ref', _('Nouveau')) == _('Nouveau'):
                vals['ref'] = (
                    self.env['ir.sequence']
                    .next_by_code('bibliotheque.livre')
                )
        return super().create(vals_list)
```

`data/sequence.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="seq_bibliotheque_livre" model="ir.sequence">
        <field name="name">Livre</field>
        <field name="code">bibliotheque.livre</field>
        <field name="prefix">LIV-%(year)s-</field>
        <field name="padding">5</field>
        <field name="implementation">standard</field>
    </record>
</odoo>
```

---

## 8. Wizards (assistants)

Un wizard est un modèle temporaire (transient) qui s'affiche en popup.

### Modèle (`wizard/wizard_emprunt.py`)

```python
from odoo import models, fields, api

class WizardEmprunt(models.TransientModel):
    _name = 'wizard.emprunt'
    _description = "Wizard Emprunt Livre"

    livre_id = fields.Many2one(
        'bibliotheque.livre', string="Livre", required=True
    )
    emprunteur = fields.Many2one(
        'res.partner', string="Emprunteur", required=True
    )
    date_retour = fields.Date(
        string="Date de retour prévue",
        default=lambda self: fields.Date.today()
    )

    def action_emprunter(self):
        self.env['bibliotheque.emprunt'].create({
            'livre_id': self.livre_id.id,
            'emprunteur': self.emprunteur.id,
            'date_emprunt': fields.Date.today(),
            'date_retour': self.date_retour,
        })
        self.livre_id.state = 'emprunte'
        return {'type': 'ir.actions.act_window_close'}
```

### Vue (`wizard/wizard_views.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_wizard_emprunt" model="ir.ui.view">
        <field name="name">wizard.emprunt.form</field>
        <field name="model">wizard.emprunt</field>
        <field name="arch" type="xml">
            <form string="Nouvel emprunt">
                <group>
                    <field name="livre_id"/>
                    <field name="emprunteur"/>
                    <field name="date_retour"/>
                </group>
                <footer>
                    <button name="action_emprunter" string="Valider"
                            type="object" class="btn-primary"/>
                    <button string="Annuler" class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_wizard_emprunt" model="ir.actions.act_window">
        <field name="name">Nouvel emprunt</field>
        <field name="res_model">wizard.emprunt</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

### Action pour ouvrir le wizard (depuis un bouton sur le livre)

```python
def action_open_wizard(self):
    return {
        'name': "Nouvel emprunt",
        'type': 'ir.actions.act_window',
        'res_model': 'wizard.emprunt',
        'view_mode': 'form',
        'target': 'new',
        'context': {
            'default_livre_id': self.id,
        },
    }
```

---

## 9. QWeb / Rapports (PDF / HTML)

### Déclaration du rapport

```xml
<record id="report_bibliotheque_livre" model="ir.actions.report">
    <field name="name">Étiquette Livre</field>
    <field name="model">bibliotheque.livre</field>
    <field name="report_type">qweb-pdf</field>
    <field name="report_name">bibliotheque.report_livre</field>
    <field name="print_report_name">'Livre - %s' % (object.name)</field>
</record>
```

### Template QWeb (`report/report_livre.xml`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="report_livre">
        <t t-foreach="docs" t-as="doc">
            <div class="page">
                <h2 t-field="doc.titre"/>
                <p>Auteur : <span t-field="doc.auteur_id.name"/></p>
                <p>Pages : <span t-field="doc.pages"/></p>
                <p t-if="doc.resume" t-field="doc.resume"/>
            </div>
        </t>
    </template>
</odoo>
```

### Héritage d'un rapport existant

```xml
<template id="report_invoice_document_inherit"
          inherit_id="account.report_invoice_document">
    <xpath expr="//div[@name='invoice_lines']" position="after">
        <p>Signature : ________________</p>
    </xpath>
</template>
```

---

## 10. Contrôleurs (Routes HTTP / API)

```python
from odoo import http
from odoo.http import request, Response
import json

class BibliothequeAPI(http.Controller):

    # --- Route web simple ---
    @http.route(
        '/bibliotheque/livres', type='http', auth='public', website=True
    )
    def liste_livres(self):
        livres = request.env['bibliotheque.livre'].sudo().search([])
        return request.render('bibliotheque.liste_livres_template', {
            'livres': livres,
        })

    # --- API JSON (GET) ---
    @http.route(
        '/api/bibliotheque/livres',
        type='json', auth='user', methods=['GET']
    )
    def api_get_livres(self):
        livres = request.env['bibliotheque.livre'].search([])
        return livres.read(['titre', 'auteur', 'pages'])

    # --- API avec paramètres ---
    @http.route(
        '/api/bibliotheque/livre/<int:livre_id>',
        type='json', auth='user'
    )
    def api_get_livre(self, livre_id):
        livre = request.env['bibliotheque.livre'].browse(livre_id)
        if not livre.exists():
            return {'error': 'Not found'}
        return {
            'id': livre.id,
            'titre': livre.titre,
            'pages': livre.pages,
        }

    # --- Endpoint POST ---
    @http.route(
        '/api/bibliotheque/livre',
        type='json', auth='user', methods=['POST']
    )
    def api_create_livre(self):
        data = request.jsonrequest
        livre = request.env['bibliotheque.livre'].create({
            'titre': data.get('titre'),
            'pages': data.get('pages'),
        })
        return {'id': livre.id, 'titre': livre.titre}

    # --- Réponse HTTP personnalisée (CSV) ---
    @http.route(
        '/bibliotheque/export/csv', type='http', auth='user'
    )
    def export_csv(self):
        livres = request.env['bibliotheque.livre'].search([])
        csv_data = "Titre,Auteur,Pages\n"
        for l in livres:
            csv_data += f"{l.titre},{l.auteur_id.name},{l.pages}\n"
        return request.make_response(
            csv_data,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition',
                 'attachment; filename="livres.csv"'),
            ]
        )
```

---

## 11. Actions (ir.actions)

```python
# --- Action fenêtre (ouvrir une vue) ---
def action_open_related(self):
    return {
        'type': 'ir.actions.act_window',
        'name': "Livres associés",
        'res_model': 'bibliotheque.livre',
        'view_mode': 'tree,form,kanban',
        'domain': [('categorie_id', '=', self.categorie_id.id)],
        'context': {
            'default_categorie_id': self.categorie_id.id,
        },
        'target': 'current',        # current / new (popup)
    }

# --- Action URL ---
def action_open_website(self):
    return {
        'type': 'ir.actions.act_url',
        'url': 'https://example.com',
        'target': 'new',            # new / self
    }

# --- Action serveur ---
def action_archive_selected(self):
    return {
        'type': 'ir.actions.server',
        'model_id': self.env.ref(
            'bibliotheque.model_bibliotheque_livre'
        ).id,
        'state': 'code',
        'code': """
records = env['bibliotheque.livre'].browse(context.get('active_ids'))
records.write({'actif': False})
        """,
    }

# --- Action rapport ---
def action_print_report(self):
    return {
        'type': 'ir.actions.report',
        'report_name': 'bibliotheque.report_livre',
        'model': 'bibliotheque.livre',
        'report_type': 'qweb-pdf',
    }

# --- Action client JS ---
def action_show_map(self):
    return {
        'type': 'ir.actions.client',
        'tag': 'bibliotheque.map_view',
        'params': {'livre_id': self.id},
    }
```

---

## 12. Décorateurs avancés

```python
# --- @api.depends_context : dépend du contexte, pas des champs ---
@api.depends_context('company', 'lang')
def _calc_label(self):
    """Recalculé quand la société ou la langue change"""
    ...

# --- @api.model + @api.returns pour les méthodes de classe ---
@api.model
@api.returns('bibliotheque.livre')
def search_livres_recents(self, jours=30):
    return self.search([
        ('date_publication', '>=',
         fields.Date.today() - timedelta(days=jours))
    ])

# --- @api.autovacuum : nettoyage automatique ---
@api.autovacuum
def _clean_old_records(self):
    """Supprime les enregistrements de plus d'un an"""
    limit = fields.Date.today() - timedelta(days=365)
    self.search([('date', '<', limit)]).unlink()

# --- Convention de nommage des méthodes ---
def _compute_xxx(self):     # Champ calculé
def _inverse_xxx(self):     # Inverse
def _search_xxx(self):      # Recherche
def _default_xxx(self):     # Valeur par défaut
def _onchange_xxx(self):    # Onchange
def _check_xxx(self):       # Contrainte
def _auto_init(self):       # Initialisation automatique
```

---

## 13. Traductions et localisation

```python
from odoo import _

message = _("Livre créé avec succès")

# Chaîne avec variables
message = _("Le livre %s a %d pages") % (titre, pages)

# Dans les champs
name = fields.Char(string=_("Titre"))
```

Fichier `.po` (`i18n/fr.po`) :

```po
#. module: bibliotheque
#: model:bibliotheque.livre
msgid "Livre"
msgstr "Book"

#. module: bibliotheque
#: model:bibliotheque.livre,field:titre
msgid "Titre"
msgstr "Title"
```

Exporter les traductions :

```bash
odoo-bin --addons-path=addons -d ma_base \
         --i18n-export=fr.po bibliotheque
```

---

## 14. Tests unitaires

```python
from odoo.tests import common, tagged
from datetime import timedelta

@tagged('standard', 'nice')
class TestBibliotheque(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.Livre = self.env['bibliotheque.livre']
        self.livre = self.Livre.create({
            'titre': "1984",
            'pages': 328,
        })

    def test_creation_livre(self):
        self.assertEqual(self.livre.titre, "1984")
        self.assertEqual(self.livre.state, 'draft')

    def test_emprunt_change_state(self):
        self.livre.action_emprunter()
        self.assertEqual(self.livre.state, 'emprunte')

    def test_contrainte_dates(self):
        with self.assertRaises(ValidationError):
            self.Livre.create({
                'titre': "Test",
                'date_debut': fields.Date.today(),
                'date_fin': (
                    fields.Date.today() - timedelta(days=1)
                ),
            })

    @tagged('slow')
    def test_generer_pdf(self):
        report = (
            self.env['ir.actions.report']
            ._get_report_from_name('bibliotheque.report_livre')
        )
        result = report._render_qweb_pdf([self.livre.id])
        self.assertTrue(len(result[0]) > 0)
```

Lancer les tests :

```bash
odoo-bin --test-enable -d ma_base -i bibliotheque
```

---

## 15. Scheduled Actions (CRON)

```python
class BibliothequeLivre(models.Model):
    _inherit = 'bibliotheque.livre'

    def action_relance_emprunts(self):
        """Relance les emprunts en retard"""
        emprunts = self.env['bibliotheque.emprunt'].search([
            ('date_retour', '<', fields.Date.today()),
            ('state', '=', 'emprunte'),
        ])
        for emp in emprunts:
            emp.message_post(
                body="⚠️ Emprunt en retard !"
            )

    def action_nettoyage_archives(self):
        """Nettoie les emprunts de plus de 3 ans"""
        limit = fields.Date.today() - timedelta(days=3*365)
        self.env['bibliotheque.emprunt'].search([
            ('date_emprunt', '<', limit),
            ('state', '=', 'retourne'),
        ]).unlink()
```

`data/cron.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="cron_relance_emprunts" model="ir.cron">
        <field name="name">Relance emprunts en retard</field>
        <field name="model_id" ref="model_bibliotheque_livre"/>
        <field name="state">code</field>
        <field name="code">model.action_relance_emprunts()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="numbercall">-1</field>
        <field name="active">True</field>
        <field name="priority">5</field>
    </record>

    <record id="cron_nettoyage" model="ir.cron">
        <field name="name">Nettoyage archives emprunts</field>
        <field name="model_id" ref="model_bibliotheque_livre"/>
        <field name="state">code</field>
        <field name="code">model.action_nettoyage_archives()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">months</field>
        <field name="numbercall">-1</field>
        <field name="active">True</field>
    </record>
</odoo>
```

---

## 16. Mixins intégrés

```python
class MonModele(models.Model):
    _name = 'mon.modele'
    _inherit = [
        'mail.thread',           # Suivi des discussions + historique
        'mail.activity.mixin',   # Activités (tâches, rappels)
        'portal.mixin',          # Accès portail
        'rating.mixin',          # Notation (étoiles)
        'image.mixin',           # Image multi-tailles
    ]
```

**`mail.thread`** ajoute :
- `message_ids` : messages / discussions
- `message_post()` : poster un message
- `tracking` : suivi des modifications de champs

**`mail.activity.mixin`** ajoute :
- `activity_ids` : activités liées
- `activity_state` : état des activités

**`portal.mixin`** ajoute :
- Accès aux enregistrements via le portail
- Token de sécurité

**`image.mixin`** ajoute :
- `image_1920`, `image_1024`, `image_512`, `image_256`, `image_128`
- Redimensionnement automatique

---

## 17. Personnalisation avancée

```python
class ResUsers(models.Model):
    _inherit = 'res.users'

    # Champ lié avec readonly=False (permet d'écrire via le lien)
    email = fields.Char(
        related='partner_id.email', readonly=False
    )

    # Champ dépendant du contexte
    @api.depends_context('uid')
    def _compute_is_self(self):
        for rec in self:
            rec.is_self = rec.id == self.env.uid

    is_self = fields.Boolean(compute='_compute_is_self')

    # Ordre personnalisé
    _order = 'partner_id.name, login'
```

---

## 18. Pièges et bonnes pratiques

```python
# ✅ BON : boucle avec champ relationnel (pas de N+1)
for rec in self:
    for ligne in rec.ligne_ids:
        ...

# ❌ MAUVAIS : recherche dans une boucle (N+1 queries)
for rec in self:
    lignes = self.env['ligne'].search([('parent_id', '=', rec.id)])
    ...

# ✅ BON : mapped pour agréger
total = sum(self.mapped('ligne_ids.total'))

# ✅ BON : sudo uniquement quand nécessaire
records.sudo().write(...)

# ✅ BON : float_compare pour les flottants
from odoo.tools import float_compare

if float_compare(rec.montant, 0, precision_digits=2) == 0:
    # égal à zéro
    pass
if float_compare(rec.montant, rec.total, precision_digits=2) >= 0:
    # >=
    pass

# ✅ BON : read_group pour les agrégations
aggs = self.env['vente.ligne'].read_group(
    [('vente_id', 'in', self.ids)],
    ['total:sum', 'quantite:avg'],
    ['vente_id']
)

# ✅ BON : browse au lieu de search quand on a les IDs
records = self.env['res.partner'].browse([1, 2, 3])

# ✅ BON : _rec_name pour l'affichage dans les Many2one
_rec_name = 'titre'
```

### Anti-patterns à éviter

```python
# ❌ NE PAS FAIRE : bouton avec action fenêtre redondante
def action_bouton(self):
    return {
        'type': 'ir.actions.act_window',
        'res_model': self._name,
        'view_mode': 'form',
        'res_id': self.id,
        # Préférer un simple return True
    }

# ❌ NE PAS FAIRE : onchange qui sauvegarde
@api.onchange('champ')
def _onchange_bad(self):
    self.autre_champ = 42
    # Cela montre une valeur modifiée mais ne persiste pas
    # L'utilisateur doit sauvegarder manuellement

# ❌ NE PAS FAIRE : create sans super()
@api.model_create_multi
def create(self, vals_list):
    # Oubli de super() -> pas d'enregistrement
    return self

# ✅ BON : toujours retourner super()
@api.model_create_multi
def create(self, vals_list):
    for vals in vals_list:
        vals['ref'] = self.env['ir.sequence'].next_by_code('test')
    return super().create(vals_list)
```

### Outils utiles

```python
# --- Date helper ---
from odoo import fields
today = fields.Date.today()
now = fields.Datetime.now()
context_today = fields.Date.context_today(self)
context_now = fields.Datetime.context_timestamp(self, datetime.now())

# --- Tools ---
from odoo.tools import (
    float_compare, float_is_zero,
    float_round, html2plaintext,
    email_split, email_normalize,
    format_amount, format_date,
    get_lang,
)

# --- Html2plaintext ---
plain = html2plaintext(html_content)
```

---

## 19. Serveur Odoo

```bash
# Lancer Odoo
odoo-bin --addons-path=addons,custom \
         -d ma_base \
         -i bibliotheque \
         --dev=all

# Mode debug
odoo-bin --addons-path=addons,custom \
         -d ma_base \
         --log-level=debug

# Installer un module
odoo-bin --addons-path=addons,custom \
         -d ma_base \
         -i bibliotheque

# Mettre à jour un module
odoo-bin --addons-path=addons,custom \
         -d ma_base \
         -u bibliotheque

# Mode shell interactif
odoo-bin shell --addons-path=addons,custom -d ma_base
```

### Dans le shell interactif

```python
>>> self.env['bibliotheque.livre'].search([])
>>> self.env.user
>>> self.env.company
>>> liv = self.env['bibliotheque.livre'].create({'titre': "Test", 'pages': 100})
>>> liv.read()
```

---

> **Ressources** :
> [Documentation officielle Odoo](https://www.odoo.com/documentation/17.0/)
> [Odoo Developers](https://www.odoo.com/documentation/17.0/developer.html)
> [Odoo Apps](https://apps.odoo.com/)
