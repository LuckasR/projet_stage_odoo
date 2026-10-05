
# construction.analysis
#         │
#         ├── lance le job
#         │
#         ├── appelle le moteur d'analyse
#         │
#         ├── récupère le JSON
#         │
#         ├── transforme le JSON en brouillons
#         │
#         └── permet de valider/générer les éléments

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
QTY_KEYS = ('beton_m3', 'acier_kg', 'coffrage_m2', 'surface_m2')


class ConstructionAnalysis(models.Model):
    _name = 'construction.analysis'
    _description = "Analyse de plan"
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    file_id = fields.Many2one(
        'construction.dwg.files', string="Plan DWG/DXF", required=True, ondelete='cascade')
    project_id = fields.Many2one(
        'project.project', related='file_id.project_id', store=True, readonly=True)
    revision = fields.Char("Indice de révision")
    engine = fields.Selection(
        [('blocks', "Blocs DXF et leurs attributs"),
         ('footings', "Fondations (géométrie des calques)"),
         ('walls', "Murs détectés")],
        string="Moteur d'analyse", default='blocks', required=True,
        help="Comment les éléments sont lus dans le plan : à partir des blocs "
             "et de leurs attributs, ou à partir de la géométrie des calques "
             "de fondation (S-SEM, S-SEM-FIL, S-LON).")
    state = fields.Selection(
        [('draft', "À lancer"),
         ('running', "En file / en cours"),
         ('done', "Terminée"),
         ('failed', "Échec")],
        default='draft', required=True, tracking=True)
    
    started_at = fields.Datetime("Mise en file")
    finished_at = fields.Datetime("Fin")
    error_log = fields.Text("Journal d'erreur")
    manual_json = fields.Text(
        "JSON de test",
        help="Si rempli, l'analyse utilise ce JSON au lieu du moteur réel "
             "(test de la chaîne complète sans moteur).")
    result_json = fields.Text("Dernier résultat JSON", readonly=True)
    draft_ids = fields.One2many('construction.element.draft', 'analysis_id', string="Brouillons")
    draft_count = fields.Integer(compute='_compute_draft_count')

    @api.depends('file_id', 'revision')
    def _compute_name(self):
        for rec in self:
            rec.name = "%s%s" % (
                rec.file_id.display_name or _("Analyse"),
                " (%s)" % rec.revision if rec.revision else "")

    @api.depends('draft_ids')
    def _compute_draft_count(self):
        for rec in self:
            rec.draft_count = len(rec.draft_ids)

    # ------------------------------------------------------------------
    # Lancement : on met le job en file, on ne bloque jamais l'utilisateur
    # ------------------------------------------------------------------
    def action_start(self):
        for rec in self:
            if rec.state == 'running':
                raise UserError(_("L'analyse « %s » est déjà en file ou en cours.") % rec.name)
            rec.write({
                'state': 'running',
                'started_at': fields.Datetime.now(),
                'finished_at': False,
                'error_log': False,
            })
            rec.with_delay(
                description=_("Analyse d'éléments : %s") % rec.name,
                identity_key=identity_exact,
            )._job_run_analysis()
        return True

    def action_retry(self):
        self.write({'state': 'draft'})
        return self.action_start()

    def _job_run_analysis(self):
        """Exécuté par le worker queue_job."""
        self.ensure_one()
        if self.state != 'running':
            return _("Analyse ignorée (état : %s).") % self.state
        try:
            with self.env.cr.savepoint():
                data = self._analyze_plan()
                self.result_json = json.dumps(data, ensure_ascii=False)
                self._process_result(data)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Analyse %s en échec", self.id)
            self.write({
                'state': 'failed',
                'finished_at': fields.Datetime.now(),
                'error_log': str(exc),
            })
            return _("Échec : %s") % exc
        return _("%s brouillon(s) créés/mis à jour.") % len(self.draft_ids)

    # ------------------------------------------------------------------
    # Moteur d'analyse : surchargé dans construction_analysis_dxf.py
    # ------------------------------------------------------------------
    def _analyze_plan(self):
        """Doit retourner un dict au format :
        {"schema_version": 1,
         "elements": [{"key": "S1", "type": "semelle",
                       "quantities": {"beton_m3": .., "acier_kg": .., "coffrage_m2": ..},
                       "dimensions": {...}, "confidence": 0.9, "issue": "...",
                       "level": "RDC",   (code ou nom d'un construction.plan.level, optionnel)
                       "source": {"page": 1, "bbox": [x1, y1, x2, y2]}}]}
        """
        self.ensure_one()
        if self.manual_json:
            try:
                return json.loads(self.manual_json)
            except ValueError as exc:
                raise ValidationError(_("JSON de test invalide : %s") % exc)
        raise NotImplementedError(_("Moteur d'analyse non branché."))

    # ------------------------------------------------------------------
    # Traitement du résultat -> brouillons (jamais d'éléments ni de tâches)
    # ------------------------------------------------------------------
    def _process_result(self, data):
        self.ensure_one()
        if not isinstance(data, dict):
            raise ValidationError(_("Le résultat doit être un objet JSON."))
        if data.get('schema_version', SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValidationError(_(
                "Version de schéma non supportée : %s (attendu : %s).")
                % (data.get('schema_version'), SCHEMA_VERSION))
        items = data.get('elements')
        if not isinstance(items, list):
            raise ValidationError(_("Le champ « elements » doit être une liste."))

        types = {t.code: t for t in self.env['construction.element.type'].search([])}
        levels = self._level_lookup()
        project_elements = {}
        if self.project_id:
            project_elements = {
                (e.key, e.level_id.id): e
                for e in self.env['construction.element'].search([
                    ('project_id', '=', self.project_id.id),
                    ('key', '!=', False)])
            }
        existing_drafts = {(d.key, d.level_id.id): d for d in self.draft_ids}

        to_create, seen, errors, unchanged = [], set(), [], []
        for item in items:
            key = str(item.get('key') or '').strip()
            level = levels.get(str(item.get('level') or '').strip().lower())
            ident = (key, level.id if level else False)
            if not key or ident in seen:
                errors.append(_("Élément ignoré (clé vide ou en double) : %s") % (key or item))
                continue
            seen.add(ident)

            code = (item.get('type') or '').strip().lower()
            etype = types.get(code)
            quantities = {k: float(v) for k, v in (item.get('quantities') or {}).items()
                          if isinstance(v, (int, float))}
            source = item.get('source') or {}
            element = project_elements.get(ident)
            vals = {
                'key': key,
                'type_code': code,
                'type_id': etype.id if etype else False,
                'level_id': level.id if level else False,
                'quantities': quantities,
                'dimensions': item.get('dimensions') or {},
                'confidence': float(item.get('confidence') or 0.0),
                'source_page': source.get('page') or 0,
                'source_bbox': source.get('bbox') or [],
                'element_id': element.id if element else False,
                # Objet source dont le brouillon suit les mises à jour
                # (moteur « murs » : le mur détecté).
                'wall_id': item.get('wall_id') or False,
                # Idem pour le moteur « ouvertures » : l'ouverture détectée.
                'opening_id': item.get('opening_id') or False,
                'change_type': self._detect_change(element, quantities),
                'issue': item.get('issue')
                         or (False if etype else _("Type « %s » inconnu") % code),
            }
            draft = existing_drafts.get(ident)
            # Élément déjà généré et identique à ce que l'analyse relève :
            # rien à faire valider. Cas typique : la relance des murs après
            # validation d'une façade, dont la hauteur a déjà été reportée sur
            # les éléments par construction.wall._sync_elements.
            if element and vals['change_type'] == 'unchanged':
                unchanged.append(key)
                if draft and draft.state == 'pending':
                    draft.unlink()
                continue
            if draft:
                if draft.state in ('validated', 'generated'):
                    continue  # on ne touche jamais à ce qui est déjà validé
                draft.write(vals)
            elif self._supersede_source_drafts(vals):
                to_create.append(dict(vals, analysis_id=self.id))

        if to_create:
            self.env['construction.element.draft'].create(to_create)

        if unchanged:
            self.message_post(body=_(
                "%d élément(s) déjà à jour, sans brouillon à valider : %s")
                % (len(unchanged), ', '.join(sorted(unchanged))))

        missing = [ident[0] for ident in project_elements if ident not in seen]
        if missing:
            self.message_post(body=_(
                "Éléments existants absents de cette analyse (à vérifier, "
                "jamais supprimés automatiquement) : %s") % ', '.join(sorted(missing)))

        self.write({
            'state': 'done',
            'finished_at': fields.Datetime.now(),
            'error_log': "\n".join(errors) or False,
        })

    def _supersede_source_drafts(self, vals):
        """Un mur ou une ouverture complété par un second plan (façade après
        vue en plan) remonte dans l'analyse de ce second plan. Son brouillon
        encore en attente dans l'analyse du premier plan est alors remplacé,
        plutôt que de laisser deux brouillons à valider pour un même ouvrage.

        Retourne False si un brouillon déjà VALIDÉ existe ailleurs : il est
        tenu à jour par la synchronisation de l'objet source, il n'y a rien à
        refaire valider."""
        self.ensure_one()
        source = [(name, '=', vals[name]) for name in ('wall_id', 'opening_id')
                  if vals.get(name)]
        if not source:
            return True
        others = self.env['construction.element.draft'].search(source + [
            ('analysis_id', '!=', self.id),
            ('key', '=', vals['key']),
            ('state', 'in', ('pending', 'validated')),
        ])
        if others.filtered(lambda d: d.state == 'validated'):
            return False
        others.unlink()
        return True

    @api.model
    def _purge_unchanged_drafts(self):
        """Rattrapage : supprime les brouillons en attente qui ne font que
        redire un élément déjà généré (créés par les relances d'analyse
        antérieures à leur filtrage dans `_process_result`). Un brouillon
        modifié, nouveau, validé ou rejeté n'est jamais touché."""
        drafts = self.env['construction.element.draft'].search([
            ('state', '=', 'pending'),
            ('change_type', '=', 'unchanged'),
            ('element_id', '!=', False),
        ])
        if drafts:
            _logger.info("%d brouillon(s) inchangé(s) sans objet supprimé(s)",
                         len(drafts))
            drafts.unlink()

    @api.model
    def _level_lookup(self):
        """{code ou nom en minuscules: niveau} pour résoudre le champ « level » du JSON."""
        lookup = {}
        for lvl in self.env['construction.plan.level'].search([]):
            if lvl.code:
                lookup[lvl.code.strip().lower()] = lvl
            lookup[lvl.name.strip().lower()] = lvl
        return lookup

    @api.model
    def _detect_change(self, element, quantities):
        if not element:
            return 'new'
        for key in QTY_KEYS:
            if abs((getattr(element, 'qty_%s' % key, 0.0) or 0.0)
                   - (quantities.get(key) or 0.0)) > 1e-6:
                return 'modified'
        return 'unchanged'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_validate_confident(self, threshold=0.9):
        for rec in self:
            rec.draft_ids.filtered(
                lambda d: d.state == 'pending' and d.type_id
                and d.confidence >= threshold).write({'state': 'validated'})

    def action_generate(self):
        self.ensure_one()
        self.draft_ids.action_generate()

    def action_view_drafts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Brouillons"),
            'res_model': 'construction.element.draft',
            'view_mode': 'tree,form',
            'domain': [('analysis_id', '=', self.id)],
            'context': {'default_analysis_id': self.id},
        }
