import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Équipes livrées : (clé, libellé, [(métier, nombre)])
DEFAULT_CREWS = [
    ('coffrage_s', "Coffrage — petite équipe", [('trade_coffreur', 1), ('trade_manoeuvre', 1)]),
    ('coffrage_l', "Coffrage — équipe renforcée", [('trade_coffreur', 2), ('trade_manoeuvre', 2)]),
    ('ferraillage_s', "Ferraillage — petite équipe", [('trade_ferrailleur', 1), ('trade_manoeuvre', 1)]),
    ('ferraillage_l', "Ferraillage — équipe renforcée", [('trade_ferrailleur', 2), ('trade_manoeuvre', 1)]),
    ('coulage_s', "Coulage — petite équipe", [('trade_macon', 1), ('trade_manoeuvre', 3)]),
    ('coulage_l', "Coulage — équipe renforcée", [('trade_macon', 2), ('trade_manoeuvre', 5)]),
    ('maconnerie_s', "Maçonnerie — petite équipe", [('trade_macon', 1), ('trade_manoeuvre', 1)]),
    ('maconnerie_l', "Maçonnerie — équipe renforcée", [('trade_macon', 2), ('trade_manoeuvre', 2)]),
]
# Équipes (petite, renforcée) d'un type de phase
PHASE_CREWS = {
    'coffrage': ('coffrage_s', 'coffrage_l'),
    'decoffrage': ('coffrage_s', 'coffrage_l'),
    'ferraillage': ('ferraillage_s', 'ferraillage_l'),
    'coulage': ('coulage_s', 'coulage_l'),
    'elevation': ('maconnerie_s', 'maconnerie_l'),
}
# Couleurs du Gantt par famille d'équipe
CREW_COLORS = {'coffrage': '#E8A317', 'ferraillage': '#3B6EA8', 'coulage': '#1B2A41',
               'maconnerie': '#B5651D'}
# Une équipe deux fois plus nombreuse ne va pas deux fois plus vite
REINFORCED_FACTOR = 1.85
# Délai technique livré : décoffrage au plus tôt 7 jours après le coulage
DEFAULT_LAGS = {'decoffrage': 7.0}


class MiroCrewDefaults(models.Model):
    _inherit = 'miro.crew'

    @api.model
    def _install_defaults(self):
        self._link_employee_trades()
        crews = self._install_default_crews()
        self._install_default_rates(crews)
        Line = self.env['construction.phase.template.line']
        for phase_type, lag in DEFAULT_LAGS.items():
            Line.search([('phase_type', '=', phase_type)]).filtered(
                lambda l: not l.min_lag_days).write({'min_lag_days': lag})

    @api.model
    def _link_employee_trades(self):
        """Le métier saisi en texte libre (miro_hr_paie) devient le métier du
        planning : retrouvé par son nom, créé s'il n'existe pas."""
        Trade = self.env['miro.trade'].with_context(active_test=False)
        employees = self.env['hr.employee'].sudo().with_context(active_test=False).search([
            ('miro_trade_id', '=', False), ('miro_trade', '!=', False)])
        for employee in employees:
            name = employee.miro_trade.strip()
            trade = Trade.search([('name', '=ilike', name)], limit=1) or Trade.create({'name': name})
            employee.miro_trade_id = trade

    @api.model
    def _install_default_crews(self):
        crews = {}
        for key, name, members in DEFAULT_CREWS:
            xmlid = 'miro_construction_planning.crew_%s' % key
            crew = self.env.ref(xmlid, raise_if_not_found=False)
            if not crew:
                crew = self.create({'name': name, 'line_ids': [
                    (0, 0, {'trade_id': self.env.ref('miro_construction_planning.%s' % trade).id,
                            'quantity': qty}) for trade, qty in members]})
                self.env['ir.model.data'].create({
                    'module': 'miro_construction_planning', 'name': 'crew_%s' % key,
                    'model': 'miro.crew', 'res_id': crew.id, 'noupdate': True})
            if not crew.color:
                crew.color = CREW_COLORS.get(key.rsplit('_', 1)[0])
            crews[key] = crew
        return crews

    @api.model
    def _install_default_rates(self, crews):
        """Une cadence par ligne de gabarit et par type d'élément qui l'utilise :
        le rendement du gabarit devient celui de la petite équipe (par
        défaut), la renforcée produit ×1,85. Les durées actuelles des phases
        sont donc conservées."""
        Rate = self.env['miro.crew.rate']
        created = 0
        for line in self.env['construction.phase.template.line'].search([('rate_per_hour', '>', 0)]):
            pair = PHASE_CREWS.get(line.phase_type)
            if not pair:
                continue
            element_types = self.env['construction.element.type'].search([
                ('phase_template_id', '=', line.template_id.id)])
            for etype in element_types:
                for crew_key, factor, default in ((pair[0], 1.0, True), (pair[1], REINFORCED_FACTOR, False)):
                    crew = crews[crew_key]
                    if Rate.search_count([('phase_type', '=', line.phase_type),
                                          ('element_type_id', '=', etype.id),
                                          ('crew_id', '=', crew.id)]):
                        continue
                    Rate.with_context(miro_no_refresh=True).create({
                        'phase_type': line.phase_type, 'element_type_id': etype.id,
                        'crew_id': crew.id, 'rate': round(line.rate_per_hour * factor, 3),
                        'qty_key': line.qty_key, 'is_default': default,
                    })
                    created += 1
        if created:
            _logger.info("%d cadence(s) d'équipe créée(s) depuis les gabarits", created)
            self.env['project.task'].search([
                ('construction_element_id', '!=', False),
                ('phase_template_line_id', '!=', False)])._miro_refresh_labor()
