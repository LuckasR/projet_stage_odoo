from odoo import models, fields


class ConstructionBom(models.Model):
    _name = 'construction.bom'
    _description = 'Nomenclature de construction'
    _order = 'name'

    _sql_constraints = [
        (
            'code_unique',
            'unique(code)',
            'La référence de la nomenclature doit être unique.'
        ),
    ]

    # Exemple : Béton armé pour 1 m³
    name = fields.Char(
        string='Nom',
        required=True
    )

    # Exemple : BETON-ARME-1M3
    code = fields.Char(
        string='Référence',
        copy=False
    )

    unit_id = fields.Many2one(
        'uom.uom',
        string='Unité de référence',
        required=True,
        ondelete='restrict'
    )

    quantity = fields.Float(
        string='Quantité de référence',
        default=1.0,
        required=True
    )

    line_ids = fields.One2many( 
        'construction.bom.line',
        'bom_id',
        string='Composants',
        copy=True
    )

    active = fields.Boolean(
        string='Actif',
        default=True
    )
    
    notes = fields.Text(
        string='Notes'
    )