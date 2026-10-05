#!/bin/bash

set -e

# ==========================================
# Colors for output
# ==========================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==========================================
# Configuration
# ==========================================
ADDONS_PATH="${ADDONS_PATH:-./odoo/addons}"

# ==========================================
# Function: print_error
# ==========================================
print_error() {
    echo -e "${RED}Erreur : $1${NC}"
}

# ==========================================
# Function: print_success
# ==========================================
print_success() {
    echo -e "${GREEN}$1${NC}"
}

# ==========================================
# Function: print_info
# ==========================================
print_info() {
    echo -e "${YELLOW}$1${NC}"
}

# ==========================================
# Function: validate_module_name
# ==========================================
validate_module_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-z][a-z0-9_]*$ ]]; then
        print_error "Le nom du module doit commencer par une lettre minuscule et ne contenir que des lettres minuscules, des chiffres et des underscores."
        exit 1
    fi
}

# ==========================================
# Vérification des paramètres
# ==========================================
if [ $# -ne 1 ]; then
    echo "Usage : $0 nom_du_module"
    echo "Exemple: $0 my_custom_module"
    exit 1
fi

MODULE_NAME="$1"
MODULE_PATH="$ADDONS_PATH/$MODULE_NAME"

# ==========================================
# Validation du nom du module
# ==========================================
validate_module_name "$MODULE_NAME"

# ==========================================
# Vérification du dossier addons
# ==========================================
if [ ! -d "$ADDONS_PATH" ]; then
    print_error "Le dossier '$ADDONS_PATH' n'existe pas."
    echo "Astuce : Définissez la variable ADDONS_PATH ou créez le dossier."
    exit 1
fi

# ==========================================
# Vérification si le module existe déjà
# ==========================================
if [ -d "$MODULE_PATH" ]; then
    print_error "Le module '$MODULE_NAME' existe déjà dans '$ADDONS_PATH'."
    exit 1
fi

# ==========================================
# Nettoyage automatique en cas d'échec
# ==========================================
cleanup_on_error() {
    print_error "Une erreur est survenue, suppression du module partiellement créé."
    rm -rf "$MODULE_PATH"
}
trap cleanup_on_error ERR

print_info "Création du module : $MODULE_NAME"

# ==========================================
# Création des dossiers
# ==========================================
mkdir -p "$MODULE_PATH/models"
mkdir -p "$MODULE_PATH/views"
mkdir -p "$MODULE_PATH/security"
mkdir -p "$MODULE_PATH/data"
mkdir -p "$MODULE_PATH/demo"
mkdir -p "$MODULE_PATH/static/src/css"
mkdir -p "$MODULE_PATH/static/src/js"
mkdir -p "$MODULE_PATH/static/src/img"
mkdir -p "$MODULE_PATH/wizard"
mkdir -p "$MODULE_PATH/report"
mkdir -p "$MODULE_PATH/controllers"

# ==========================================
# Création des fichiers
# ==========================================
touch "$MODULE_PATH/README.md"
touch "$MODULE_PATH/__init__.py"
touch "$MODULE_PATH/__manifest__.py"

touch "$MODULE_PATH/models/__init__.py"
touch "$MODULE_PATH/models/models.py"

touch "$MODULE_PATH/views/menu.xml"
touch "$MODULE_PATH/views/views.xml"
touch "$MODULE_PATH/views/templates.xml"

touch "$MODULE_PATH/security/ir.model.access.csv"
touch "$MODULE_PATH/security/security.xml"

touch "$MODULE_PATH/data/data.xml"
touch "$MODULE_PATH/demo/demo.xml"

touch "$MODULE_PATH/controllers/__init__.py"
touch "$MODULE_PATH/controllers/controllers.py"

touch "$MODULE_PATH/wizard/__init__.py"
touch "$MODULE_PATH/wizard/wizard.py"

# ==========================================
# __init__.py
# ==========================================
cat > "$MODULE_PATH/__init__.py" <<EOF
from . import models
from . import controllers
EOF

# ==========================================
# models/__init__.py
# ==========================================
cat > "$MODULE_PATH/models/__init__.py" <<EOF
from . import models
EOF

# ==========================================
# models/models.py
# ==========================================
cat > "$MODULE_PATH/models/models.py" <<EOF
from odoo import models, fields, api

class ${MODULE_NAME^}Model(models.Model):
    _name = '${MODULE_NAME}.model'
    _description = '${MODULE_NAME^} Model'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')
EOF

# ==========================================
# controllers/__init__.py
# ==========================================
cat > "$MODULE_PATH/controllers/__init__.py" <<EOF
from . import controllers
EOF

# ==========================================
# controllers/controllers.py
# ==========================================
cat > "$MODULE_PATH/controllers/controllers.py" <<EOF
from odoo import http
from odoo.http import request

class ${MODULE_NAME^}Controller(http.Controller):

    @http.route('/${MODULE_NAME}/test', type='http', auth='public')
    def test(self, **kwargs):
        return "<h1>Hello ${MODULE_NAME^}</h1>"
EOF

# ==========================================
# __manifest__.py
# Ordre de chargement corrigé :
# security -> views.xml (crée l'action) -> menu.xml (l'utilise) -> data
# Assets déclarés via la clé 'assets' (méthode Odoo 15+), plus besoin
# de templates.xml pour charger le JS/CSS.
# ==========================================
AUTHOR="${AUTHOR:-L. M. Rabemiafara, Miro K.E.}"
CATEGORY="${CATEGORY:-Tools}"

cat > "$MODULE_PATH/__manifest__.py" <<EOF
{
    'name': '${MODULE_NAME//_/ }',
    'version': '17.0.1.0.0',
    'summary': '${MODULE_NAME//_/ }',
    'description': '''
Module ${MODULE_NAME//_/ }
''',
    'author': '$AUTHOR',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'category': '$CATEGORY',
    'depends': ['base'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/menu.xml',
        'data/data.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '${MODULE_NAME}/static/src/js/${MODULE_NAME}.js',
            '${MODULE_NAME}/static/src/css/${MODULE_NAME}.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
EOF

# ==========================================
# security/security.xml
# Correction : on crée la catégorie de module avant de la référencer,
# au lieu de référencer 'base.module_category_<name>' qui n'existe pas.
# ==========================================
cat > "$MODULE_PATH/security/security.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <data noupdate="0">
        <!-- Module Category -->
        <record id="module_category_${MODULE_NAME}" model="ir.module.category">
            <field name="name">${MODULE_NAME//_/ }</field>
            <field name="sequence">20</field>
        </record>

        <!-- Security Groups -->
        <record id="group_${MODULE_NAME}_user" model="res.groups">
            <field name="name">${MODULE_NAME//_/ } User</field>
            <field name="category_id" ref="module_category_${MODULE_NAME}"/>
        </record>

        <record id="group_${MODULE_NAME}_manager" model="res.groups">
            <field name="name">${MODULE_NAME//_/ } Manager</field>
            <field name="implied_ids" eval="[(4, ref('group_${MODULE_NAME}_user'))]"/>
            <field name="category_id" ref="module_category_${MODULE_NAME}"/>
        </record>
    </data>
</odoo>
EOF

# ==========================================
# ir.model.access.csv
# Accès ouvert à tout utilisateur interne (base.group_user) par défaut,
# avec les 4 droits (lecture, écriture, création, suppression).
# ==========================================
cat > "$MODULE_PATH/security/ir.model.access.csv" <<EOF
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_${MODULE_NAME}_user,${MODULE_NAME}.user,model_${MODULE_NAME}_model,base.group_user,1,1,1,1
EOF

# ==========================================
# views/views.xml (chargé avant menu.xml)
# ==========================================
cat > "$MODULE_PATH/views/views.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <!-- Action -->
    <record id="action_${MODULE_NAME}_list" model="ir.actions.act_window">
        <field name="name">${MODULE_NAME//_/ }</field>
        <field name="res_model">${MODULE_NAME}.model</field>
        <field name="view_mode">tree,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Create your first ${MODULE_NAME//_/ }
            </p>
        </field>
    </record>

    <!-- Tree View -->
    <record id="view_${MODULE_NAME}_tree" model="ir.ui.view">
        <field name="name">${MODULE_NAME}.tree</field>
        <field name="model">${MODULE_NAME}.model</field>
        <field name="arch" type="xml">
            <tree>
                <field name="name"/>
                <field name="active"/>
            </tree>
        </field>
    </record>

    <!-- Form View -->
    <record id="view_${MODULE_NAME}_form" model="ir.ui.view">
        <field name="name">${MODULE_NAME}.form</field>
        <field name="model">${MODULE_NAME}.model</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="active"/>
                        <field name="description" colspan="2"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
</odoo>
EOF

# ==========================================
# views/menu.xml (chargé après views.xml, car il utilise l'action)
# ==========================================
cat > "$MODULE_PATH/views/menu.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <menuitem id="menu_${MODULE_NAME}_root"
              name="${MODULE_NAME//_/ }"
              sequence="10"/>

    <menuitem id="menu_${MODULE_NAME}_config"
              name="Configuration"
              parent="menu_${MODULE_NAME}_root"
              sequence="10"/>

    <menuitem id="menu_${MODULE_NAME}_list"
              name="${MODULE_NAME//_/ }"
              parent="menu_${MODULE_NAME}_root"
              action="action_${MODULE_NAME}_list"
              sequence="20"/>
</odoo>
EOF

# ==========================================
# views/templates.xml
# Conservé pour d'éventuels templates QWeb (portail, rapports, etc.)
# mais ne charge plus le JS/CSS : c'est géré par 'assets' dans le manifest.
# ==========================================
cat > "$MODULE_PATH/views/templates.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <!-- Vos templates QWeb ici -->
</odoo>
EOF

# ==========================================
# data.xml
# ==========================================
cat > "$MODULE_PATH/data/data.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <data noupdate="1">
        <!-- Your data here -->
    </data>
</odoo>
EOF

# ==========================================
# demo.xml
# ==========================================
cat > "$MODULE_PATH/demo/demo.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <data>
        <!-- Your demo data here -->
    </data>
</odoo>
EOF

# ==========================================
# README.md
# ==========================================
cat > "$MODULE_PATH/README.md" <<EOF
# ${MODULE_NAME//_/ }

## Description
Module ${MODULE_NAME//_/ } for Odoo 17

## Installation
1. Place the module in your addons directory
2. Update the apps list
3. Install the module

## Configuration
No special configuration required.

## Features
- Feature 1
- Feature 2

## Author
${AUTHOR}

## License
LGPL-3
EOF

# ==========================================
# Static JS (module ES6 natif, remplace odoo.define obsolète)
# ==========================================
cat > "$MODULE_PATH/static/src/js/${MODULE_NAME}.js" <<EOF
/** @odoo-module **/

console.log('${MODULE_NAME} loaded');
EOF

# ==========================================
# Static CSS
# ==========================================
cat > "$MODULE_PATH/static/src/css/${MODULE_NAME}.css" <<EOF
/* ${MODULE_NAME} styles */
EOF

# ==========================================
# Final message
# ==========================================
trap - ERR
echo ""
echo "=========================================="
print_success "✅ Module créé avec succès !"
echo "=========================================="
echo "📦 Nom    : $MODULE_NAME"
echo "📁 Chemin : $MODULE_PATH"
echo ""
print_info "📝 Structure créée :"
tree -L 2 "$MODULE_PATH" 2>/dev/null || ls -la "$MODULE_PATH"
echo ""
echo "=========================================="
echo "🚀 Prochaines étapes :"
echo "1. Vérifiez le fichier __manifest__.py"
echo "2. Ajoutez vos modèles dans models/models.py"
echo "3. Personnalisez les vues dans views/"
echo "4. Mettez à jour la liste des applications :"
echo "   ./odoo-bin -u all -d votre_base"
echo "5. Installez le module :"
echo "   ./odoo-bin -i $MODULE_NAME -d votre_base"
echo "=========================================="