import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Nomenclatures livrées (mrp.bom natives). Chacune « fabrique » un produit
# ouvrage (« Béton dosé à 350 kg/m³ (1 m³) »), créé s'il manque. Les matériaux
# sont désignés par le CODE de leur catégorie (construction.material.category) :
# la ligne reçoit le premier article de cette catégorie, ou un article
# générique du même nom créé pour l'occasion.
#   code bom: (libellé, unité de référence, phase visée, [
#       (code catégorie, libellé catégorie, quantité, unité, coefficient)])
DEFAULT_BOMS = {
    'MIRO-BET-350': ("Béton dosé à 350 kg/m³ (1 m³)", 'uom.product_uom_cubic_meter', 'coulage', [
        ('ciment', "Ciment", 350.0, 'uom.product_uom_kgm', 1.0),
        ('sable', "Sable", 0.40, 'uom.product_uom_cubic_meter', 1.05),
        ('gravier', "Gravier / Gravillon", 0.80, 'uom.product_uom_cubic_meter', 1.05),
        ('eau', "Eau", 175.0, 'uom.product_uom_litre', 1.0),
    ]),
    'MIRO-ARM-HA': ("Armatures haute adhérence (1 kg)", 'uom.product_uom_kgm', 'ferraillage', [
        # 10 % de chutes et de recouvrements
        ('acier', "Acier / Fer à béton", 1.0, 'uom.product_uom_kgm', 1.10),
        ('fil_acier', "Fil d'acier (ligature)", 0.01, 'uom.product_uom_kgm', 1.0),
    ]),
    'MIRO-COF-BOIS': ("Coffrage bois (1 m²)", 'uom.uom_square_meter', 'coffrage', [
        # Panneau réemployé 5 fois
        ('contreplaque', "Contreplaqué", 1.0, 'uom.uom_square_meter', 0.20),
        ('clou', "Clou", 0.05, 'uom.product_uom_kgm', 1.0),
    ]),
    'MIRO-MAC-PARP': ("Maçonnerie de parpaings (1 m²)", 'uom.uom_square_meter', 'elevation', [
        ('parpaing', "Parpaing / Bloc béton", 10.0, 'uom.product_uom_unit', 1.05),
        ('mortier', "Mortier", 0.02, 'uom.product_uom_cubic_meter', 1.10),
    ]),
}


class ConstructionBomDefaults(models.Model):
    _inherit = 'mrp.bom'

    @api.model
    def _install_default_boms(self):
        """Crée les nomenclatures livrées si absentes (par leur code), puis les
        rattache aux phases de même code qui n'ont pas encore de
        nomenclature. Ne remplace jamais un choix existant. Idempotent."""
        boms = {}
        for code, (name, unit, phase_type, lines) in DEFAULT_BOMS.items():
            bom = self.with_context(active_test=False).search([('code', '=', code)], limit=1)
            if not bom:
                uom = self.env.ref(unit)
                line_vals = []
                for seq, (cat_code, cat_name, qty, line_uom, coef) in enumerate(lines, 1):
                    category = self._default_category(cat_code, cat_name)
                    line_vals.append((0, 0, {
                        'sequence': seq * 10,
                        'product_id': self._default_component(category, self.env.ref(line_uom)).id,
                        'material_category_id': category.id,
                        'product_qty': qty,
                        'product_uom_id': self.env.ref(line_uom).id,
                        'coefficient': coef}))
                bom = self.create({
                    'code': code,
                    'product_tmpl_id': self._default_work_product(name, uom).id,
                    'product_qty': 1.0,
                    'product_uom_id': uom.id,
                    'type': 'normal',
                    'construction_ok': True,
                    'bom_line_ids': line_vals,
                })
            boms[phase_type] = bom

        self._install_wall_template(boms.get('elevation'))

        Line = self.env['construction.phase.template.line']
        for phase_type, bom in boms.items():
            for line in Line.search([('phase_type', '=', phase_type), ('bom_id', '=', False)]):
                native = self._native_uom(line.qty_key)
                if native and native.category_id == bom.product_uom_id.category_id:
                    line.bom_id = bom

        # Phases déjà générées avant ce module : leurs besoins sont calculés
        # une fois (les phases commencées sont laissées telles quelles).
        tasks = self.env['project.task'].search([
            ('construction_element_id', '!=', False),
            ('phase_template_line_id.bom_id', '!=', False),
            ('material_need_ids', '=', False)])
        if tasks:
            refreshed = tasks._refresh_material_needs()
            _logger.info("Besoins matériaux calculés pour %d phase(s) existante(s)",
                         len(refreshed))

    @api.model
    def _default_category(self, code, name):
        Category = self.env['construction.material.category'].with_context(active_test=False)
        return Category.search([('code', '=', code)], limit=1) \
            or Category.create({'code': code, 'name': name})

    @api.model
    def _default_component(self, category, uom):
        """Premier article de la catégorie dont l'unité est convertible, sinon
        un article générique stockable, à remplacer par le vrai produit."""
        product = self.env['product.product'].search([
            ('material_category_id', 'child_of', category.id),
            ('uom_id.category_id', '=', uom.category_id.id)], limit=1)
        return product or self.env['product.product'].create({
            'name': category.name,
            'detailed_type': 'product',
            'uom_id': uom.id,
            'uom_po_id': uom.id,
            'material_category_id': category.id,
            'sale_ok': False,
        })

    @api.model
    def _default_work_product(self, name, uom):
        """Produit « ouvrage » que la recette fabrique : ni vendu, ni acheté."""
        Template = self.env['product.template'].with_context(active_test=False)
        return Template.search([('name', '=', name), ('uom_id', '=', uom.id)], limit=1) \
            or Template.create({
                'name': name,
                'detailed_type': 'consu',
                'uom_id': uom.id,
                'uom_po_id': uom.id,
                'sale_ok': False,
                'purchase_ok': False,
            })

    @api.model
    def _install_wall_template(self, bom):
        """Gabarit « Mur maçonné » (élévation au m² de surface nette), donné au
        type Mur s'il n'a encore aucun gabarit : sans phase, un mur ne
        consommerait aucun matériau."""
        Template = self.env['construction.phase.template']
        template = Template.with_context(active_test=False).search(
            [('name', '=', "Mur maçonné")], limit=1)
        if not template:
            template = Template.create({'name': "Mur maçonné", 'line_ids': [(0, 0, {
                'sequence': 10, 'name': "Élévation", 'phase_type': 'elevation',
                'qty_key': 'surface_m2', 'rate_per_hour': 1.5,
                'bom_id': bom.id if bom else False})]})
        wall_type = self.env['construction.element.type'].search([('code', '=', 'mur')], limit=1)
        if wall_type and not wall_type.phase_template_id:
            wall_type.phase_template_id = template
            _logger.info("Type Mur : gabarit « Mur maçonné » attribué")
