from odoo import _, api, fields, models


class ConstructionProjectMaterial(models.Model):
    """Produit retenu pour un besoin générique sur un projet : « Ciment » ->
    « Ciment CPJ 42.5, sac de 50 kg ». Vaut aussi pour les sous-catégories
    qui n'ont pas leur propre choix."""
    _name = 'construction.project.material'
    _description = "Matériau retenu pour un projet"
    _order = 'project_id, category_id'

    project_id = fields.Many2one('project.project', required=True, ondelete='cascade', index=True)
    category_id = fields.Many2one(
        'construction.material.category', string="Besoin", required=True)
    product_id = fields.Many2one(
        'product.product', string="Produit retenu", required=True,
        domain="[('material_category_id', 'child_of', category_id)]")

    _sql_constraints = [
        ('category_uniq', 'unique(project_id, category_id)',
         "Un seul produit retenu par besoin et par projet."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._apply_to_needs()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._apply_to_needs()
        return res

    def _apply_to_needs(self):
        """Le produit retenu s'applique aux besoins pas encore commandés."""
        for rec in self:
            needs = self.env['construction.material.need'].search([
                ('project_id', '=', rec.project_id.id),
                ('category_id', 'child_of', rec.category_id.id)])
            choices = rec.project_id._material_choices()
            for need in needs.filtered(lambda n: not n._is_locked()):
                product = rec.project_id._product_for(need.category_id, choices)
                if product and product != need.product_id:
                    need.product_id = product


class ProjectProject(models.Model):
    _inherit = 'project.project'

    material_choice_ids = fields.One2many(
        'construction.project.material', 'project_id', string="Matériaux retenus")
    material_need_ids = fields.One2many(
        'construction.material.need', 'project_id', string="Besoins matériaux")
    material_need_count = fields.Integer(compute='_compute_material_stats')
    material_planned_cost = fields.Float(
        "Coût matériaux prévu", compute='_compute_material_stats')

    def _compute_material_stats(self):
        for project in self:
            needs = project.material_need_ids
            project.material_need_count = len(needs)
            project.material_planned_cost = sum(needs.mapped('planned_cost'))

    def _material_choices(self):
        self.ensure_one()
        return {c.category_id.id: c.product_id for c in self.material_choice_ids}

    def _product_for(self, category, choices=None):
        """Produit retenu pour une catégorie : le sien, sinon celui de la
        catégorie parente la plus proche."""
        choices = self._material_choices() if choices is None else choices
        while category:
            if category.id in choices:
                return choices[category.id]
            category = category.parent_id
        return self.env['product.product']

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_view_material_needs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Besoins matériaux — %s") % self.name,
            'res_model': 'construction.material.need', 'view_mode': 'tree,pivot,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'search_default_group_product': 1},
        }

    def action_refresh_material_needs(self):
        """Recalcule les besoins des phases non commencées du projet."""
        self.ensure_one()
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.id), ('construction_element_id', '!=', False),
            ('phase_template_line_id', '!=', False)])
        refreshed = tasks._refresh_material_needs()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Besoins matériaux"), 'type': 'success', 'sticky': False,
                       'message': _("%d phase(s) recalculée(s) ; les phases commencées "
                                    "gardent leurs besoins.") % len(refreshed)},
        }

    def action_create_material_purchases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Demandes de prix matériaux"),
            'res_model': 'construction.need.purchase.wizard', 'view_mode': 'form',
            'target': 'new', 'context': {'default_project_id': self.id},
        }
