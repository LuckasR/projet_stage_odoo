from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

QTY_KEYS = ('beton_m3', 'acier_kg', 'coffrage_m2')


class ConstructionElementDraft(models.Model):
    _name = 'construction.element.draft'
    _description = "Élément détecté (brouillon)"
    _rec_name = 'key'
    _order = 'confidence asc, key'

    analysis_id = fields.Many2one(
        'construction.analysis', required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        'project.project', related='analysis_id.project_id', store=True, readonly=True)
    key = fields.Char("Clé", required=True, index=True)
    type_code = fields.Char("Type détecté")
    type_id = fields.Many2one('construction.element.type', string="Type")
    quantities = fields.Json("Quantités")
    dimensions = fields.Json("Dimensions")
    confidence = fields.Float("Confiance", digits=(3, 2))
    source_page = fields.Integer("Page source")
    source_bbox = fields.Json("Zone source")
    issue = fields.Char("Anomalie")
    change_type = fields.Selection(
        [('new', "Nouveau"), ('modified', "Modifié"), ('unchanged', "Inchangé")],
        string="Évolution", default='new')
    state = fields.Selection(
        [('pending', "À valider"),
         ('validated', "Validé"),
         ('rejected', "Rejeté"),
         ('generated', "Généré")],
        default='pending', required=True, index=True)
    element_id = fields.Many2one('construction.element', string="Élément", readonly=True)

    # Quantités éditables dans la vue de revue (stockées dans le JSON)
    qty_beton_m3 = fields.Float(compute='_compute_qty', inverse='_inverse_qty')
    qty_acier_kg = fields.Float(compute='_compute_qty', inverse='_inverse_qty')
    qty_coffrage_m2 = fields.Float(compute='_compute_qty', inverse='_inverse_qty')

    _sql_constraints = [
        ('key_analysis_uniq', 'unique(analysis_id, key)',
         "Cette clé existe déjà dans l'analyse."),
    ]

    @api.depends('quantities')
    def _compute_qty(self):
        for rec in self:
            q = rec.quantities or {}
            rec.qty_beton_m3 = q.get('beton_m3', 0.0)
            rec.qty_acier_kg = q.get('acier_kg', 0.0)
            rec.qty_coffrage_m2 = q.get('coffrage_m2', 0.0)

    def _inverse_qty(self):
        for rec in self:
            rec.quantities = {
                'beton_m3': rec.qty_beton_m3,
                'acier_kg': rec.qty_acier_kg,
                'coffrage_m2': rec.qty_coffrage_m2,
            }

    @api.constrains('state', 'type_id')
    def _check_type_when_validated(self):
        for rec in self:
            if rec.state in ('validated', 'generated') and not rec.type_id:
                raise ValidationError(_("Le type de « %s » doit être renseigné.") % rec.key)

    # ------------------------------------------------------------------
    # Validation humaine
    # ------------------------------------------------------------------
    def action_validate(self):
        missing = self.filtered(lambda d: not d.type_id)
        if missing:
            raise UserError(_("Type inconnu pour : %s") % ', '.join(missing.mapped('key')))
        self.filtered(lambda d: d.state in ('pending', 'rejected')).write({'state': 'validated'})

    def action_reject(self):
        self.filtered(lambda d: d.state in ('pending', 'validated')).write({'state': 'rejected'})

    def action_reset(self):
        self.filtered(lambda d: d.state in ('validated', 'rejected')).write({'state': 'pending'})

    # ------------------------------------------------------------------
    # Génération : brouillons validés -> éléments -> tâches
    # ------------------------------------------------------------------
    def _prepare_element_vals(self, work):
        self.ensure_one()
        q = self.quantities or {}
        vals = {
            'key': self.key,
            'type_id': self.type_id.id,
            'work_id': work.id,
            'source_file_id': self.analysis_id.file_id.id,
            'source_page': self.source_page,
            'confidence': self.confidence,
        }
        for k in QTY_KEYS:
            vals['qty_%s' % k] = q.get(k, 0.0)
        return vals

    def action_generate(self):
        """Idempotent : upsert par (projet, clé), tâches créées seulement si absentes."""
        drafts = self.filtered(lambda d: d.state == 'validated')
        if not drafts:
            raise UserError(_("Aucun brouillon validé à générer."))

        Element = self.env['construction.element']
        Work = self.env['construction.work']
        works = {}
        all_elements = Element

        for analysis in drafts.mapped('analysis_id'):
            project = analysis.project_id
            if not project:
                raise UserError(_("Le plan n'est rattaché à aucun projet."))
            existing = {
                e.key: e for e in Element.search([
                    ('work_id.project_id', '=', project.id), ('key', '!=', False)])
            }
            to_create, to_create_drafts = [], self.browse()

            for draft in drafts.filtered(lambda d, a=analysis: d.analysis_id == a):
                wname = draft.type_id.work_name
                wkey = (project.id, wname)
                if wkey not in works:
                    works[wkey] = Work.search(
                        [('project_id', '=', project.id), ('name', '=', wname)], limit=1
                    ) or Work.create({'project_id': project.id, 'name': wname})
                vals = draft._prepare_element_vals(works[wkey])

                element = existing.get(draft.key)
                if element:
                    # Mise à jour : on ne supprime ni ne déplace rien
                    element.write({k: v for k, v in vals.items() if k != 'work_id'})
                    draft.write({'element_id': element.id, 'state': 'generated'})
                    all_elements |= element
                else:
                    if 'name' in Element._fields:
                        vals['name'] = draft.key
                    to_create.append(vals)
                    to_create_drafts |= draft

            if to_create:
                created = Element.create(to_create)  # création groupée
                for draft, element in zip(to_create_drafts, created):
                    draft.write({'element_id': element.id, 'state': 'generated'})
                all_elements |= created

        all_elements._generate_tasks()
        return True
