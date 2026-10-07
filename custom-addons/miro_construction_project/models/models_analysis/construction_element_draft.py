from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.queue_job.job import identity_exact

from ...service.element_sketch import (
    opening_summary, render_element_sketch, tremie_summary)

QTY_KEYS = ('beton_m3', 'acier_kg', 'coffrage_m2', 'surface_m2')
GENERATE_CHUNK_SIZE = 50  # éléments par job de génération


class ConstructionElementDraft(models.Model):
    _name = 'construction.element.draft'
    _description = "Élément détecté (brouillon)"
    _rec_name = 'key'
    _order = 'confidence asc, key'

    # Clés de métré reconnues par le circuit des phases. Exposé ici pour que
    # les caractéristiques d'un type d'élément puissent valider les leurs.
    _QUANTITY_KEYS = QTY_KEYS

    analysis_id = fields.Many2one(
        'construction.analysis', required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        'project.project', related='analysis_id.project_id', store=True, readonly=True)
    key = fields.Char("Clé", required=True, index=True)
    type_code = fields.Char("Type détecté")
    type_id = fields.Many2one('construction.element.type', string="Type")
    level_id = fields.Many2one('construction.plan.level', string="Niveau")
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
    # Mur détecté dont provient ce brouillon (moteur « murs » uniquement).
    # Tant que le brouillon n'est pas généré, ses cotes et métrés suivent le
    # mur (cf. construction.wall._sync_elements).
    wall_id = fields.Many2one(
        'construction.wall', string="Mur d'origine", readonly=True,
        index=True, ondelete='set null')
    # Ouverture détectée dont provient ce brouillon (moteur « ouvertures »),
    # suivie de la même façon (cf. construction.opening._sync_elements).
    opening_id = fields.Many2one(
        'construction.opening', string="Ouverture d'origine", readonly=True,
        index=True, ondelete='set null')

    tremie_summary = fields.Char("Trémies", compute='_compute_sketch')
    opening_summary = fields.Char("Ouvertures", compute='_compute_sketch')
    sketch_svg = fields.Html(
        "Représentation", compute='_compute_sketch', sanitize=False,
        help="Schéma coté de l'ouvrage détecté (trémies d'une dalle comprises).")

    # Ferraillage type de l'ouvrage, lu sur le plan de détail (tableau
    # « FERRAILLAGE TYPE » ou légende « Poutre : 4 HA14 ... »).
    reinforcement = fields.Char("Ferraillage")

    # Quantités éditables dans la vue de revue (stockées dans le JSON)
    qty_beton_m3 = fields.Float(compute='_compute_qty', inverse='_inverse_qty')
    qty_acier_kg = fields.Float(compute='_compute_qty', inverse='_inverse_qty')
    qty_coffrage_m2 = fields.Float(compute='_compute_qty', inverse='_inverse_qty')
    qty_surface_m2 = fields.Float(compute='_compute_qty', inverse='_inverse_qty')

    # Dimensions relevées sur le plan, éditables de la même façon. Une vue en
    # plan ne montre JAMAIS la hauteur d'un ouvrage : c'est ici qu'elle se
    # saisit, et c'est elle qui débloque le calcul des métrés.
    dim_l = fields.Float(
        "Longueur (m)", compute='_compute_dim', inverse='_inverse_dim')
    dim_w = fields.Float(
        "Largeur (m)", compute='_compute_dim', inverse='_inverse_dim',
        help="Largeur de l'ouvrage, ou son épaisseur pour un mur.")
    dim_h = fields.Float(
        "Hauteur (m)", compute='_compute_dim', inverse='_inverse_dim',
        help="Non lisible sur une vue en plan : à saisir avant de calculer "
             "les métrés.")

    @api.constrains('analysis_id', 'key', 'level_id')
    def _check_key_unique(self):
        for rec in self:
            if self.search_count([
                    ('id', '!=', rec.id),
                    ('analysis_id', '=', rec.analysis_id.id),
                    ('level_id', '=', rec.level_id.id or False),
                    ('key', '=', rec.key)]):
                raise ValidationError(_(
                    "La clé « %s » existe déjà dans l'analyse pour ce niveau.") % rec.key)

    @api.depends('dimensions', 'type_id.code', 'type_code', 'key', 'wall_id.opening_ids.width', 'wall_id.opening_ids.height',
                 'wall_id.opening_ids.sill_height', 'wall_id.opening_ids.opening_type',
                 'wall_id.opening_ids.center_x', 'wall_id.opening_ids.center_y')
    def _compute_sketch(self):
        for rec in self:
            dims = rec.dimensions or {}
            openings = rec.wall_id._opening_layout() if rec.wall_id else []
            rec.tremie_summary = tremie_summary(dims) or False
            rec.opening_summary = opening_summary(openings) or False
            rec.sketch_svg = render_element_sketch(
                rec.type_id.code or rec.type_code,
                {'l': dims.get('l', 0.0), 'w': dims.get('w', dims.get('ep', 0.0)),
                 'h': dims.get('h', 0.0), 'tremies': dims.get('tremies') or []},
                label=rec.key or "", openings=openings)

    @api.depends('quantities')
    def _compute_qty(self):
        for rec in self:
            q = rec.quantities or {}
            rec.qty_beton_m3 = q.get('beton_m3', 0.0)
            rec.qty_acier_kg = q.get('acier_kg', 0.0)
            rec.qty_coffrage_m2 = q.get('coffrage_m2', 0.0)
            rec.qty_surface_m2 = q.get('surface_m2', 0.0)

    def _inverse_qty(self):
        for rec in self:
            rec.quantities = {
                'beton_m3': rec.qty_beton_m3,
                'acier_kg': rec.qty_acier_kg,
                'coffrage_m2': rec.qty_coffrage_m2,
                'surface_m2': rec.qty_surface_m2,
            }

    @api.depends('dimensions')
    def _compute_dim(self):
        for rec in self:
            d = rec.dimensions or {}
            rec.dim_l = d.get('l', 0.0)
            # Le moteur « murs » nomme l'épaisseur « ep », les autres « w ».
            rec.dim_w = d.get('w', d.get('ep', 0.0))
            rec.dim_h = d.get('h', 0.0)

    def _inverse_dim(self):
        for rec in self:
            dims = dict(rec.dimensions or {})
            dims['l'] = rec.dim_l
            dims['ep' if 'ep' in dims else 'w'] = rec.dim_w
            dims['h'] = rec.dim_h
            rec.dimensions = dims

    def _apply_type_defaults(self):
        """Complète les caractéristiques que le plan n'a pas données, avec les
        valeurs par défaut du type d'élément.

        C'est ce qui évite de ressaisir la même hauteur sur des dizaines de
        semelles : la nomenclature du projet la fixe une fois, le type la
        porte, le brouillon la reçoit. Une valeur déjà relevée sur le plan
        n'est jamais remplacée."""
        for rec in self:
            dims = dict(rec.dimensions or {})
            qty = dict(rec.quantities or {})
            touched = False

            for line in rec.type_id.field_ids.filtered('default_value'):
                target = dims if line.nature == 'dimension' else qty
                if not target.get(line.code):
                    target[line.code] = line.default_value
                    touched = True

            if touched:
                rec.dimensions = dims
                rec.quantities = qty
        return self

    def _missing_required_fields(self):
        """Caractéristiques obligatoires encore vides, par brouillon."""
        missing = {}
        for rec in self:
            empty = [
                line for line in rec.type_id.field_ids.filtered('required')
                if not (rec.dimensions or {}).get(line.code)
                and not (rec.quantities or {}).get(line.code)
            ]
            if empty:
                missing[rec] = empty
        return missing

    def action_compute_quantities(self):
        """Calcule les métrés à partir des dimensions saisies.

        Une vue en plan ne montre pas la hauteur des ouvrages : le moteur
        laisse donc les métrés vides et signale l'anomalie. Les valeurs par
        défaut du type sont d'abord appliquées, puis les formules du type
        (cf. `_compute_quantities`), sans écraser un métré saisi à la main."""
        computed = self._compute_quantities()

        message = (_("Métrés calculés sur %s ouvrage(s).") % len(computed)
                   if computed else
                   _("Aucun métré calculable : saisissez d'abord la hauteur."))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Calcul des métrés"), 'message': message,
                       'sticky': False,
                       'type': 'success' if computed else 'warning'},
        }

    def _compute_quantities(self, apply_defaults=True):
        """Métrés manquants, selon la nature de l'ouvrage :

          - baie         surface = L × h
          - dalle        surface nette (trémies déduites) ; béton = surface × ép. ;
                         coffrage = sous-face
          - poutre       béton = L × l × h ; coffrage = fond + 2 joues = (2h + l) × L
          - mur          surface = (L − baies) × h ; volume = surface × ép. ;
                         pas de coffrage (maçonnerie)
          - autres       béton = L × l × h ; coffrage = 2(L + l) × h

        puis acier = béton × ratio du type. Retourne les brouillons chiffrés.

        `apply_defaults=False` chiffre seulement ce que le plan a donné, sans
        combler une cote manquante par la valeur par défaut du type : c'est
        le cas d'un chiffrage automatique, qui ne doit pas masquer une
        hauteur non relevée."""
        if apply_defaults:
            self._apply_type_defaults()
        computed = self.browse()
        for rec in self:
            qty = dict(rec.quantities or {})
            code = rec.type_id.code or rec.type_code
            l, w, h = rec.dim_l, rec.dim_w, rec.dim_h
            if rec.opening_id:
                # Une baie ne se chiffre ni en béton ni en coffrage : son
                # métré est sa surface (largeur × hauteur).
                if l and h:
                    if not qty.get('surface_m2'):
                        qty['surface_m2'] = round(l * h, 3)
                    rec.quantities = qty
                    computed |= rec
                continue
            if code == 'dalle':
                surface = qty.get('surface_m2') or (l * w)
                if not (surface and h):
                    continue
                values = {'surface_m2': surface, 'beton_m3': surface * h,
                          'coffrage_m2': surface}
            elif code == 'mur':
                if not (l and w and h):
                    continue
                openings = (rec.dimensions or {}).get('ouvertures_m') or 0.0
                surface = max(l - openings, 0.0) * h
                values = {'surface_m2': surface, 'beton_m3': surface * w}
            else:
                if not (l and w and h):
                    continue
                coffrage = ((2 * h + w) * l if code == 'poutre'
                            else 2 * (l + w) * h)
                values = {'beton_m3': l * w * h, 'coffrage_m2': coffrage}
            for key, value in values.items():
                if not qty.get(key):
                    qty[key] = round(value, 3)
            ratio = rec.type_id.steel_ratio_kg_m3
            if ratio and not qty.get('acier_kg'):
                qty['acier_kg'] = round(qty['beton_m3'] * ratio, 1)
            rec.quantities = qty
            computed |= rec
        return computed

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

        # Les valeurs par défaut du type comblent ce que le plan n'a pas
        # montré : on les applique avant de contrôler, sinon on refuserait
        # une hauteur que le type sait déjà donner.
        self._apply_type_defaults()

        incomplete = self._missing_required_fields()
        if incomplete:
            details = "\n".join(
                "- %s (%s) : %s" % (
                    draft.key, draft.type_id.name,
                    ", ".join(line.display_name for line in lines))
                for draft, lines in incomplete.items())
            raise UserError(_(
                "Caractéristiques obligatoires manquantes. Renseignez-les, ou "
                "donnez-leur une valeur par défaut sur le type d'élément "
                "(Configuration > Types d'éléments).\n\n%s") % details)

        self.filtered(lambda d: d.state in ('pending', 'rejected')).write({'state': 'validated'})

    def action_reject(self):
        self.filtered(lambda d: d.state in ('pending', 'validated')).write({'state': 'rejected'})

    def action_reset(self):
        self.filtered(lambda d: d.state in ('validated', 'rejected')).write({'state': 'pending'})

    # ------------------------------------------------------------------
    # Génération : brouillons validés -> éléments -> phases (par lots, en jobs)
    # ------------------------------------------------------------------
    def _prepare_element_vals(self, ouvrage):
        self.ensure_one()
        q = self.quantities or {}
        vals = {
            'name': self.key,
            'key': self.key,
            'element_type_id': self.type_id.id,
            'level_id': self.level_id.id,
            'ouvrage_task_id': ouvrage.id,
            'source_file_id': self.analysis_id.file_id.id,
            'source_page': self.source_page,
            'confidence': self.confidence,
            # Les dimensions suivent le brouillon jusqu'à l'élément : sans
            # elles, impossible de vérifier d'où sortent les métrés ni de les
            # recalculer après correction d'une cote.
            'dimensions': dict(self.dimensions or {}),
            # La position suit aussi : c'est elle qui permet de replacer
            # l'élément validé sur le plan dans le visualiseur.
            'source_bbox': list(self.source_bbox or []),
            'wall_id': self.wall_id.id,
            'opening_id': self.opening_id.id,
            'reinforcement': self.reinforcement,
        }
        for k in QTY_KEYS:
            vals['qty_%s' % k] = q.get(k, 0.0)
        return vals

    def _ouvrage_name(self):
        """« Fondation », ou « Poteaux - RDC » si le type crée un ouvrage par niveau."""
        self.ensure_one()
        name = self.type_id.work_name
        if self.type_id.ouvrage_per_level and self.level_id:
            name = "%s - %s" % (name, self.level_id.name)
        return name

    def _get_or_create_ouvrage(self, project, name):
        """Task « Ouvrage » du projet (ex. : Fondation), créée si absente."""
        Task = self.env['project.task']
        return Task.search([
            ('project_id', '=', project.id),
            ('is_ouvrage', '=', True),
            ('name', '=', name),
        ], limit=1) or Task.create({
            'name': name,
            'project_id': project.id,
            'is_ouvrage': True,
        })

    def action_generate(self):
        """Point d'entrée UI : crée les tasks Ouvrage tout de suite (peu nombreuses,
        évite les doublons entre jobs parallèles) puis découpe le reste en jobs."""
        drafts = self.filtered(lambda d: d.state == 'validated')
        if not drafts:
            raise UserError(_("Aucun brouillon validé à générer."))
        reference = drafts.filtered(lambda d: not d.analysis_id.file_id.is_execution_plan)
        if reference:
            raise UserError(_(
                "Ces brouillons viennent d'un plan de référence (architecture) : "
                "seuls les plans d'exécution (fondation, coffrage, détails) "
                "génèrent des tâches et des phases. Rejetez-les, ou classez le "
                "plan dans un type de famille « Exécution ».\n\n%s")
                % ", ".join(reference.mapped('key')))
        for draft in drafts:
            if not draft.analysis_id.project_id:
                raise UserError(_("Le plan n'est rattaché à aucun projet."))
            draft._get_or_create_ouvrage(
                draft.analysis_id.project_id, draft._ouvrage_name())

        for start in range(0, len(drafts), GENERATE_CHUNK_SIZE):
            chunk = drafts[start:start + GENERATE_CHUNK_SIZE]
            chunk.with_delay(
                description=_("Génération de %s élément(s) et de leurs phases") % len(chunk),
                identity_key=identity_exact,
            )._job_generate()
        return True

    def _job_generate(self):
        """Exécuté par le worker. Idempotent : upsert par (projet, clé),
        phases créées seulement si absentes, rien n'est jamais supprimé."""
        drafts = self.exists().filtered(lambda d: d.state == 'validated')
        if not drafts:
            return _("Rien à générer (déjà traité).")

        Element = self.env['construction.element']
        all_elements = Element
        ouvrages = {}

        for analysis in drafts.mapped('analysis_id'):
            project = analysis.project_id
            existing = {
                (e.key, e.level_id.id): e for e in Element.search([
                    ('project_id', '=', project.id), ('key', '!=', False)])
            }
            to_create, to_create_drafts = [], self.browse()

            for draft in drafts.filtered(lambda d, a=analysis: d.analysis_id == a):
                okey = (project.id, draft._ouvrage_name())
                if okey not in ouvrages:
                    ouvrages[okey] = draft._get_or_create_ouvrage(project, okey[1])
                vals = draft._prepare_element_vals(ouvrages[okey])

                element = existing.get((draft.key, draft.level_id.id))
                if element:
                    # Mise à jour : on ne déplace pas l'élément et on ne renomme pas
                    element.write({k: v for k, v in vals.items()
                                   if k not in ('ouvrage_task_id', 'name')})
                    draft.write({'element_id': element.id, 'state': 'generated'})
                    all_elements |= element
                else:
                    to_create.append(vals)
                    to_create_drafts |= draft

            if to_create:
                created = Element.create(to_create)  # création groupée
                for draft, element in zip(to_create_drafts, created):
                    draft.write({'element_id': element.id, 'state': 'generated'})
                all_elements |= created

        tasks = all_elements._generate_tasks()
        return _("%s élément(s) traités, %s phase(s) créées.") % (
            len(all_elements), len(tasks))
