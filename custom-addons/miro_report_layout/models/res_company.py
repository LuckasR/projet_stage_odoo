from odoo import api, fields, models

MIRO_PRIMARY = '#1B2A41'    # bleu nuit
MIRO_SECONDARY = '#E8A317'  # ocre chantier


class ResCompany(models.Model):
    _inherit = 'res.company'

    miro_stat = fields.Char(
        "N° STAT", help="Numéro statistique (Madagascar), imprimé dans le pied "
                        "de page des documents avec le NIF et le RCS.")

    @api.model
    def _miro_apply_branding(self):
        """Mise en page Miro Construction sur les sociétés. Ne remplace que
        les valeurs d'usine : un nom, des couleurs ou une police déjà choisis
        sont conservés."""
        layout = self.env.ref('miro_report_layout.external_layout_miro')
        for company in self.search([]):
            vals = {'external_report_layout_id': layout.id}
            if company.name in ('My Company', 'YourCompany'):
                vals['name'] = "Miro Construction"
            if not company.primary_color:
                vals['primary_color'] = MIRO_PRIMARY
            if not company.secondary_color:
                vals['secondary_color'] = MIRO_SECONDARY
            if not company.display_invoice_amount_total_words:
                vals['display_invoice_amount_total_words'] = True
            company.write(vals)
        # La feuille de style par société est produite par un template que ce
        # module étend. Pendant son installation (ou sa mise à jour), Odoo
        # n'applique les extensions de vues que des modules déjà chargés, ou
        # de celui que désigne `install_module` : sans lui, la branche Miro
        # serait absente et les couleurs perdues.
        self.env.registry.clear_cache('templates')
        self.with_context(install_module='miro_report_layout')._update_asset_style()
