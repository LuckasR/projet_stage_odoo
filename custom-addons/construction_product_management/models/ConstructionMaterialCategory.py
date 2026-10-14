from odoo import api, fields, models

class ConstructionMaterialCategory(models.Model):
    _name = 'construction.material.category'
    _description = 'Catégorie de matériau de construction'
    _order = 'sequence, name'

    name = fields.Char(
        string="Nom",
        required=True,
        index=True,
    )

    code = fields.Char(
        string="Code",
        required=True,
        index=True,
    )

    sequence = fields.Integer(
        string="Séquence",
        default=10,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    parent_id = fields.Many2one(
        'construction.material.category',
        string="Catégorie parente",
        ondelete='restrict',
    )

    child_ids = fields.One2many(
        'construction.material.category',
        'parent_id',
        string="Sous-catégories",
    )

    description = fields.Text(
        string="Description",
    )

    product_tmpl_ids = fields.One2many(
        'product.template', 'material_category_id', string="Produits")
    product_count = fields.Integer(compute='_compute_product_count')

    def _compute_product_count(self):
        for rec in self:
            rec.product_count = self.env['product.template'].search_count(
                [('material_category_id', 'child_of', rec.id)])

    @api.depends('name', 'parent_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ("%s / %s" % (rec.parent_id.name, rec.name)
                                if rec.parent_id else rec.name)

    @api.model
    def _for_legacy_code(self, code, create=True):
        """Catégorie correspondant à une valeur de l'ancienne liste fixe
        (ciment, sable, gravier...), créée si absente."""
        category = self.with_context(active_test=False).search([('code', '=', code)], limit=1)
        if not category and create:
            labels = dict(self.env['construction.material.type']._fields['category'].selection)
            category = self.create({'code': code, 'name': labels.get(code, code)})
        return category

    @api.model
    def _backfill_material_categories(self):
        """Reprise, à chaque mise à jour : types et produits reçoivent la
        catégorie de matériau de leur ancienne valeur fixe. Idempotent ; une
        catégorie déjà choisie n'est jamais remplacée."""
        for mtype in self.env['construction.material.type'].with_context(active_test=False) \
                .search([('material_category_id', '=', False)]):
            mtype.material_category_id = self._for_legacy_code(mtype.category)
        products = self.env['product.template'].with_context(active_test=False).search([
            ('material_category_id', '=', False),
            ('construction_material_type_id', '!=', False)])
        for product in products:
            product.material_category_id = product.construction_material_type_id.material_category_id
