# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- Activation / classification -------------------------------------
    is_construction_material = fields.Boolean(
        string="Matériau de construction",
        default=False,
        help="Cocher pour activer les champs techniques spécifiques "
             "aux matériaux de construction (ciment, sable, gravier...).",
    )
    construction_material_type_id = fields.Many2one(
        'construction.material.type',
        string="Type de matériau",
        ondelete='restrict',
    )
    construction_category = fields.Selection(
        related='construction_material_type_id.category',
        string="Catégorie de matériau",
        store=True,
        readonly=True,
    )

    # --- Caractéristiques techniques dynamiques ----------------------------
    characteristic_ids = fields.One2many(
        'construction.material.characteristic',
        'product_tmpl_id',
        string="Caractéristiques techniques",
    )

    technical_note = fields.Text(string="Note technique")

    # --- Contraintes ------------------------------------------------------
    @api.constrains('is_construction_material', 'construction_material_type_id')
    def _check_construction_material_type(self):
        for product in self:
            if product.is_construction_material and not product.construction_material_type_id:
                raise ValidationError(
                    "Veuillez sélectionner un type de matériau pour un "
                    "produit marqué comme 'Matériau de construction' : %s" % product.name
                )

    # --- Onchange -----------------------------------------------------------
    @api.onchange('construction_material_type_id')
    def _onchange_construction_material_type_id(self):
        """Pré-remplit is_construction_material et génère les lignes
        de caractéristiques correspondant au type de matériau choisi."""
        if self.construction_material_type_id and not self.is_construction_material:
            self.is_construction_material = True
        self._sync_characteristics()

    @api.onchange('is_construction_material')
    def _onchange_is_construction_material(self):
        if not self.is_construction_material:
            self.construction_material_type_id = False
            self.characteristic_ids = [(5, 0, 0)]

    # --- Helpers ------------------------------------------------------------
    def _sync_characteristics(self):
        """Ajoute une ligne vide pour chaque attribut du type de matériau
        qui n'a pas encore de ligne, sans toucher aux lignes existantes."""
        for product in self:
            if not product.construction_material_type_id:
                continue
            existing_attrs = product.characteristic_ids.mapped('attribute_id')
            missing_attrs = product.construction_material_type_id.attribute_ids - existing_attrs
            commands = [
                (0, 0, {'attribute_id': attr.id})
                for attr in missing_attrs
            ]
            if commands:
                product.characteristic_ids = commands