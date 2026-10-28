from odoo import _, api, fields, models
from odoo.tools import float_round


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
    # Tableau de bord des matériaux
    # ------------------------------------------------------------------
    @api.model
    def _material_status(self, row):
        """État d'un matériau (libellé, classe) : le plus urgent l'emporte."""
        eps = 1e-6
        if row['no_product']:
            return _("Produit à choisir"), 'warn'
        if row['gap'] > 0:
            return _("Surconsommation"), 'bad'
        if row['planned'] and row['consumed'] >= row['planned'] - eps:
            return _("Consommé"), 'ok'
        if row['shortage'] > 0:
            return _("Stock insuffisant"), 'bad'
        if row['planned'] and row['received'] >= row['planned'] - eps:
            return _("Reçu"), 'ok'
        if row['ordered'] > 0:
            return _("Commandé"), 'info'
        return _("À commander"), 'neutral'

    def action_print_material_report(self):
        """Rapport PDF des besoins en matériaux : état, approvisionnement,
        répartitions et points d'attention."""
        self.ensure_one()
        return self.env.ref('miro_construction_bom.action_report_material_needs').report_action(self)

    def action_open_material_dashboard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'miro_construction_bom.material_dashboard',
            'name': _("Besoins en matériaux — %s") % self.name,
            'context': {'default_project_id': self.id},
        }

    def get_material_dashboard(self):
        """Données du tableau de bord : un seul appel, tout agrégé ici.

        Les quantités sont dans l'unité du PRODUIT (ce qu'on achète et
        stocke) ; les besoins sans produit sont regroupés par catégorie, à
        part. Les coûts sont au coût du produit (standard_price)."""
        self.ensure_one()
        needs = self.material_need_ids
        currency = self.company_id.currency_id or self.env.company.currency_id

        def bucket():
            return {'planned': 0.0, 'ordered': 0.0, 'received': 0.0, 'consumed': 0.0,
                    'remaining': 0.0, 'gap': 0.0, 'planned_cost': 0.0,
                    'consumed_cost': 0.0, 'need_ids': [], 'elements': set()}

        materials, groups = {}, {'ouvrage': {}, 'level': {}, 'phase': {}}
        for need in needs:
            key = ('p', need.product_id.id) if need.product_id else ('c', need.category_id.id)
            row = materials.setdefault(key, bucket())
            cost = need.product_id.standard_price or 0.0
            row['planned'] += need.product_qty
            row['ordered'] += need.qty_ordered
            row['received'] += need.qty_received
            row['consumed'] += need.qty_consumed
            row['remaining'] += need.qty_remaining
            row['gap'] += need.qty_gap
            row['planned_cost'] += need.planned_cost
            row['consumed_cost'] += need.qty_consumed * cost
            row['need_ids'].append(need.id)
            row['elements'].add(need.element_id.id)
            for kind, label in (('ouvrage', need.ouvrage_task_id.name),
                                ('level', need.level_id.name),
                                ('phase', need.task_id.phase_template_line_id.name or need.phase_type)):
                grp = groups[kind].setdefault(label or _("Non classé"), {
                    'planned_cost': 0.0, 'consumed_cost': 0.0, 'count': 0})
                grp['planned_cost'] += need.planned_cost
                grp['consumed_cost'] += need.qty_consumed * cost
                grp['count'] += 1

        rows = []
        for (kind, res_id), row in materials.items():
            sample = self.env['construction.material.need'].browse(row['need_ids'][0])
            product = sample.product_id
            stock = product.qty_available if product else 0.0
            shortage = max(row['remaining'] - stock - max(row['ordered'] - row['received'], 0.0), 0.0)
            # La somme de dizaines de besoins traîne des résidus flottants
            # (7406,7400000001 contre 7406,74 en stock) : sans arrondi à la
            # précision de l'unité, on afficherait « Stock insuffisant, manque 0 ».
            shortage = float_round(shortage, precision_rounding=(
                product.uom_id.rounding if product else 0.01) or 0.01)
            rows.append({
                'key': '%s%s' % (kind, res_id),
                'product_id': product.id or False,
                'name': product.display_name if product else _("Produit à choisir"),
                'category': sample.category_id.display_name or '',
                'uom': (product.uom_id.name if product else sample.uom_id.name) or '',
                'planned': row['planned'], 'ordered': row['ordered'],
                'received': row['received'], 'consumed': row['consumed'],
                'remaining': row['remaining'], 'gap': row['gap'],
                'stock': stock, 'shortage': shortage,
                'unit_cost': product.standard_price if product else 0.0,
                'planned_cost': row['planned_cost'], 'consumed_cost': row['consumed_cost'],
                'element_count': len(row['elements'] - {False}),
                'need_ids': row['need_ids'],
                'no_product': not product,
            })
            rows[-1]['status'], rows[-1]['status_class'] = self._material_status(rows[-1])
        rows.sort(key=lambda r: (not r['no_product'], -r['planned_cost'], r['name']))

        def ratio(part, whole):
            return round(100.0 * part / whole, 1) if whole else 0.0

        planned_cost = sum(r['planned_cost'] for r in rows)
        weight = lambda field: sum(r[field] * r['unit_cost'] for r in rows)
        return {
            'project': {'id': self.id, 'name': self.name},
            'currency': {'symbol': currency.symbol, 'position': currency.position,
                         'digits': currency.decimal_places},
            'kpis': {
                'planned_cost': planned_cost,
                'consumed_cost': sum(r['consumed_cost'] for r in rows),
                'material_count': len(rows),
                'need_count': len(needs),
                'element_count': len(needs.element_id),
                # Avancement de l'approvisionnement, pondéré par la valeur
                'pct_ordered': ratio(weight('ordered'), weight('planned')),
                'pct_received': ratio(weight('received'), weight('planned')),
                'pct_consumed': ratio(weight('consumed'), weight('planned')),
                'no_product': sum(1 for r in rows if r['no_product']),
                'overrun': sum(1 for r in rows if r['gap'] > 0),
                'shortage': sum(1 for r in rows if r['shortage'] > 0),
            },
            'materials': rows,
            'groups': {
                kind: sorted(({'name': name, **vals} for name, vals in data.items()),
                             key=lambda g: -g['planned_cost'])
                for kind, data in groups.items()},
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_view_material_needs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Besoins matériaux — %s") % self.name,
            'res_model': 'construction.material.need', 'view_mode': 'tree,pivot,form',
            'views': [(False, 'tree'), (False, 'pivot'), (False, 'form')],
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
            'views': [(False, 'form')], 'target': 'new', 'context': {'default_project_id': self.id},
        }
