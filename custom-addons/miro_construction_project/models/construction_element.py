import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

from ..service.element_sketch import (
    opening_summary, render_element_sketch, tremie_summary)
from .models_analysis.construction_element_type import UOM_SELECTION

_logger = logging.getLogger(__name__)

# Métrés portés en dur par l'élément : une caractéristique de type « quantité »
# n'est reconnue que si elle vise l'un d'eux.
QTY_FIELDS = ('beton_m3', 'acier_kg', 'coffrage_m2', 'surface_m2')


class ConstructionElement(models.Model):
    """Élément de construction (Semelle S1, Poteau P3…).

    Hiérarchie :  Projet
                    └── Task « Ouvrage » (project.task, is_ouvrage)   ← ouvrage_task_id
                          ├── Élément S1 (ce modèle)
                          │     └── Phases = sous-tâches de l'ouvrage, liées par construction_element_id
                          └── Élément S2 ...
    """
    _name = 'construction.element'
    _description = "Élément de construction"
    _order = 'ouvrage_task_id, key, name'

    name = fields.Char(required=True)
    key = fields.Char(
        "Clé d'identification", index=True, copy=False,
        help="Identifiant stable dans le projet (ex. : S1). Sert à mettre à jour l'élément "
             "lors d'une nouvelle révision du plan.")
    active = fields.Boolean(default=True)

    element_type_id = fields.Many2one(
        'construction.element.type', string="Type d'élément")
    ouvrage_task_id = fields.Many2one(
        'project.task', string="Ouvrage", domain="[('is_ouvrage', '=', True)]",
        index=True, ondelete='restrict')
    project_id = fields.Many2one(
        'project.project', string="Projet", related='ouvrage_task_id.project_id',
        store=True, index=True, readonly=True)
    level_id = fields.Many2one('construction.plan.level', string="Niveau", index=True)

    # --- Traçabilité de l'analyse --------------------------------------
    source_file_id = fields.Many2one(
        'construction.dwg.files', string="Plan source", readonly=True)
    source_page = fields.Integer("Page source", readonly=True)
    confidence = fields.Float("Confiance de l'analyse", digits=(3, 2), readonly=True)
    # Zone source [minx, miny, maxx, maxy] dans le repère du plan DXF, reprise
    # du brouillon : c'est elle qui permet de replacer l'élément validé sur
    # le plan dans le visualiseur (construction/footings/<dwg_file_id>).
    source_bbox = fields.Json("Zone source", readonly=True)
    # Mur détecté que cet élément représente. Le mur reste la source des
    # cotes (longueur, épaisseur, hauteur) : toute mise à jour du mur —
    # façade validée, coupe, saisie — est reportée ici.
    wall_id = fields.Many2one(
        'construction.wall', string="Mur d'origine", readonly=True,
        index=True, ondelete='set null')
    # Ouverture détectée (porte, fenêtre) que cet élément représente, suivie
    # comme le mur : une façade qui donne sa hauteur la reporte ici.
    opening_id = fields.Many2one(
        'construction.opening', string="Ouverture d'origine", readonly=True,
        index=True, ondelete='set null')

    # --- Dimensions -----------------------------------------------------
    # Reprises du brouillon à la génération. Sans elles, l'élément ne
    # porterait que ses métrés : impossible de vérifier d'où ils sortent, ni
    # de les recalculer après correction d'une cote.
    dimensions = fields.Json("Dimensions", copy=False)
    dim_l = fields.Float("Longueur (m)", compute='_compute_dim',
                         inverse='_inverse_dim', store=True)
    dim_w = fields.Float("Largeur (m)", compute='_compute_dim',
                         inverse='_inverse_dim', store=True,
                         help="Largeur de l'ouvrage, ou son épaisseur pour un mur.")
    dim_h = fields.Float("Hauteur (m)", compute='_compute_dim',
                         inverse='_inverse_dim', store=True)
    dimension_summary = fields.Char(
        "Dimensions relevées", compute='_compute_dimension_summary',
        help="Caractéristiques attendues par le type d'élément, avec leur unité.")
    # Schéma coté (vues en plan / coupe / élévation selon le type), redessiné
    # à chaque lecture depuis les dimensions : jamais stocké, donc toujours à
    # jour après correction d'une cote.
    # Trémies (vides) d'une dalle : leur surface est déjà déduite des métrés,
    # ce résumé et le schéma les rendent visibles.
    tremie_summary = fields.Char("Trémies", compute='_compute_tremie_summary')
    # Ouvertures percées dans le mur : leur surface est déduite du métré.
    opening_summary = fields.Char("Ouvertures", compute='_compute_sketch_svg')
    wall_opening_count = fields.Integer(
        "Nb d'ouvertures", compute='_compute_wall_opening_count')
    sketch_svg = fields.Html(
        "Représentation", compute='_compute_sketch_svg', sanitize=False)

    # --- Quantités ------------------------------------------------------
    reinforcement = fields.Char(
        "Ferraillage", help="Ferraillage type relevé sur le plan de détail.")
    qty_beton_m3 = fields.Float("Béton (m³)")
    qty_acier_kg = fields.Float("Acier (kg)")
    qty_coffrage_m2 = fields.Float("Coffrage (m²)")
    qty_surface_m2 = fields.Float(
        "Surface (m²)",
        help="Surface développée de l'ouvrage. Pour un mur : longueur × hauteur.")

    # Reflet des caractéristiques déclarées sur le type. Ces lignes ne se
    # créent ni ne se suppriment à la main : elles suivent le type. Seule leur
    # valeur se saisit ici.
    value_ids = fields.One2many(
        'construction.element.value', 'element_id', string="Caractéristiques")

    missing_field_ids = fields.Many2many(
        'construction.element.type.field', string="Caractéristiques manquantes",
        compute='_compute_missing_fields',
        help="Caractéristiques déclarées obligatoires sur le type d'élément et "
             "restées vides sur cet élément.")
    has_missing_fields = fields.Boolean(
        "Incomplet", compute='_compute_missing_fields', store=True)

    # --- Phases ---------------------------------------------------------
    task_ids = fields.One2many(
        'project.task', 'construction_element_id', string="Phases")
    task_count = fields.Integer(compute='_compute_task_count')
    progress = fields.Float("Avancement (%)", compute='_compute_progress')

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

    def _characteristic_value(self, line):
        """Valeur portée par l'élément pour une caractéristique de son type."""
        self.ensure_one()
        if line.nature == 'dimension':
            return (self.dimensions or {}).get(line.code, 0.0)
        return self['qty_%s' % line.code] if line.code in QTY_FIELDS else 0.0

    def _set_characteristic(self, line, value):
        """Écrit une caractéristique là où elle est réellement stockée.

        Les métrés restent dans leurs colonnes : ce sont elles que les gabarits
        de phases chiffrent (`qty_key`). Les dimensions vont dans le JSON. Les
        lignes de caractéristiques ne dupliquent donc aucune donnée, elles ne
        font que présenter ce stockage selon ce que le type déclare."""
        self.ensure_one()
        if line.nature == 'dimension':
            dims = dict(self.dimensions or {})
            dims[line.code] = value
            self.dimensions = dims
        elif line.code in QTY_FIELDS:
            self['qty_%s' % line.code] = value

    # ------------------------------------------------------------------
    # Synchronisation des caractéristiques avec le type
    # ------------------------------------------------------------------
    def _sync_value_lines(self):
        """Aligne les lignes de l'élément sur celles déclarées par son type.

        Une caractéristique ajoutée au type apparaît sur les éléments
        existants ; une caractéristique retirée disparaît. C'est ce qui évite
        d'avoir à ressaisir la configuration ouvrage par ouvrage."""
        Value = self.env['construction.element.value']
        for rec in self:
            expected = rec.element_type_id.field_ids
            current = rec.value_ids

            obsolete = current.filtered(lambda v: v.field_id not in expected)
            if obsolete:
                obsolete.unlink()

            known = current.mapped('field_id')
            Value.create([
                {'element_id': rec.id, 'field_id': line.id}
                for line in expected if line not in known
            ])

    @api.model
    def _sync_all_value_lines(self):
        """Rattrapage à la mise à jour du module, pour les éléments créés
        avant l'introduction des caractéristiques."""
        self.with_context(active_test=False).search([])._sync_value_lines()

    @api.model
    def _backfill_source_bbox(self):
        """Reprend la zone source des éléments générés avant l'introduction de
        `source_bbox` sur ce modèle : elle vit toujours sur leur brouillon
        d'origine (`construction.element.draft.source_bbox`), jamais purgé à
        la génération. Sans ce rattrapage, ces éléments restent invisibles
        dans le visualiseur de fondations bien qu'ils soient validés."""
        elements = self.with_context(active_test=False).search([
            ('source_bbox', 'in', (False, [])),
        ])
        if not elements:
            return

        drafts = self.env['construction.element.draft'].with_context(
            active_test=False).search([
                ('element_id', 'in', elements.ids),
                ('source_bbox', '!=', False),
            ])
        by_element = {d.element_id.id: d.source_bbox for d in drafts if d.source_bbox}

        updated = 0
        for element in elements:
            bbox = by_element.get(element.id)
            if bbox:
                element.source_bbox = bbox
                updated += 1

        if updated:
            _logger.info(
                "%d élément(s) de construction ont retrouvé leur zone source "
                "depuis leur brouillon d'origine", updated)

    def _apply_wall_measures(self, item):
        """Reporte les cotes et métrés d'un mur ou d'une ouverture (au format
        `_wall_to_item` / `_opening_to_item`) sur ses éléments, puis
        recalcule les heures des phases encore non commencées : elles ont pu être chiffrées sur un métré nul, avant que
        la hauteur ne soit connue."""
        quantities = item.get('quantities') or {}
        for rec in self:
            dims = dict(rec.dimensions or {})
            dims.update(item.get('dimensions') or {})
            vals = {'dimensions': dims}
            for key in QTY_FIELDS:
                if key in quantities:
                    vals['qty_%s' % key] = quantities[key]
            rec.write(vals)
            rec._refresh_phase_hours()

    def _refresh_phase_hours(self):
        """Heures prévues des phases non commencées, d'après les métrés
        actuels. Une phase entamée, terminée ou annulée n'est jamais touchée :
        ses heures ont pu être ajustées à la main."""
        for rec in self:
            for task in rec.task_ids.filtered(
                    lambda t: t.phase_template_line_id
                    and not t.x_avancement_global
                    and t.state not in ('1_done', '1_canceled')):
                hours = task.phase_template_line_id._compute_hours(rec)
                if abs((task.allocated_hours or 0.0) - hours) > 1e-6:
                    task.allocated_hours = hours

    def action_open_opening(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construction.opening',
            'res_id': self.opening_id.id,
            'view_mode': 'form',
        }

    def action_open_wall(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construction.wall',
            'res_id': self.wall_id.id,
            'view_mode': 'form',
        }

    @api.depends('wall_id.opening_ids')
    def _compute_wall_opening_count(self):
        for rec in self:
            rec.wall_opening_count = len(rec.wall_id.opening_ids)

    def action_view_wall_openings(self):
        """Ouvertures percées dans le mur de cet élément."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Ouvertures de %s") % (self.key or self.name),
            'res_model': 'construction.opening',
            'view_mode': 'tree,form',
            'domain': [('wall_id', '=', self.wall_id.id)],
            'context': {'default_wall_id': self.wall_id.id,
                        'default_level_id': self.wall_id.level_id.id,
                        'default_dwg_file_id': self.wall_id.dwg_file_id.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        elements = super().create(vals_list)
        elements._sync_value_lines()
        return elements

    def write(self, vals):
        res = super().write(vals)
        if 'element_type_id' in vals:
            self._sync_value_lines()
        return res

    @api.depends('dimensions',
                 'element_type_id.field_ids.required',
                 'element_type_id.field_ids.code',
                 'element_type_id.field_ids.nature',
                 'qty_beton_m3', 'qty_acier_kg', 'qty_coffrage_m2', 'qty_surface_m2')
    def _compute_missing_fields(self):
        for rec in self:
            missing = rec.element_type_id.field_ids.filtered(
                lambda line: line.required and not rec._characteristic_value(line))
            rec.missing_field_ids = missing
            rec.has_missing_fields = bool(missing)

    @api.depends('dimensions', 'element_type_id.field_ids.name',
                 'element_type_id.field_ids.uom', 'element_type_id.field_ids.nature')
    def _compute_dimension_summary(self):
        """Résumé lisible : « Longueur 1.20 m · Largeur 1.20 m · Hauteur 0.30 m ».

        Les caractéristiques affichées et leur ordre viennent du type
        d'élément : une semelle et un mur ne se décrivent pas pareil."""
        for rec in self:
            parts = []
            for line in rec.element_type_id.field_ids.filtered(
                    lambda l: l.nature == 'dimension'):
                value = (rec.dimensions or {}).get(line.code)
                parts.append("%s %s %s" % (
                    line.name, ("%.2f" % value) if value else "—",
                    dict(UOM_SELECTION).get(line.uom, '')))
            rec.dimension_summary = " · ".join(parts)

    @api.depends('dimensions', 'dim_l', 'dim_w', 'dim_h',
                 'element_type_id.code', 'key', 'name', 'wall_id.opening_ids.width', 'wall_id.opening_ids.height',
                 'wall_id.opening_ids.sill_height', 'wall_id.opening_ids.opening_type',
                 'wall_id.opening_ids.center_x', 'wall_id.opening_ids.center_y')
    def _compute_sketch_svg(self):
        for rec in self:
            openings = rec.wall_id._opening_layout() if rec.wall_id else []
            rec.opening_summary = opening_summary(openings) or False
            rec.sketch_svg = render_element_sketch(
                rec.element_type_id.code,
                {'l': rec.dim_l, 'w': rec.dim_w, 'h': rec.dim_h,
                 'tremies': (rec.dimensions or {}).get('tremies') or []},
                label=rec.key or rec.name or "", openings=openings)

    @api.depends('dimensions')
    def _compute_tremie_summary(self):
        for rec in self:
            rec.tremie_summary = tremie_summary(rec.dimensions) or False

    @api.constrains('key', 'project_id', 'level_id')
    def _check_key_unique(self):
        """Identité d'un élément : (projet, niveau, clé). P1 au RDC et P1 au R+1 sont distincts."""
        for rec in self.filtered(lambda r: r.key and r.project_id):
            if self.with_context(active_test=False).search_count([
                    ('id', '!=', rec.id),
                    ('project_id', '=', rec.project_id.id),
                    ('level_id', '=', rec.level_id.id or False),
                    ('key', '=', rec.key)]):
                raise ValidationError(_(
                    "La clé « %s » existe déjà dans ce projet pour ce niveau.") % rec.key)

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.depends('task_ids.x_avancement_global', 'task_ids.allocated_hours', 'task_ids.state')
    def _compute_progress(self):
        """Moyenne des avancements des phases (x_avancement_global),
        pondérée par les heures prévues (poids 1 si non renseignées)."""
        for rec in self:
            tasks = rec.task_ids.filtered(lambda t: t.state != '1_canceled')
            total = sum(t.allocated_hours or 1.0 for t in tasks)
            done = sum((t.allocated_hours or 1.0) * t.x_avancement_global for t in tasks)
            rec.progress = done / total if total else 0.0

    # ------------------------------------------------------------------
    # Génération des phases depuis le gabarit du type
    # ------------------------------------------------------------------
    def _generate_tasks(self):
        """Crée les phases manquantes (idempotent) en un seul create groupé,
        comme sous-tâches de la task Ouvrage, puis pose les dépendances.
        Ne supprime jamais rien."""
        Task = self.env['project.task']
        vals_list, meta = [], []

        for element in self:
            ouvrage = element.ouvrage_task_id
            template = element.element_type_id.phase_template_id
            if not ouvrage or not template:
                continue
            existing_types = set(element.task_ids.mapped('phase_type'))
            for line in template.line_ids.sorted('sequence'):
                if line.phase_type in existing_types:
                    continue
                vals_list.append({
                    'name': "%s - %s" % (element.key or element.name, line.name),
                    'project_id': ouvrage.project_id.id,
                    'parent_id': ouvrage.id,
                    'construction_element_id': element.id,
                    'phase_type': line.phase_type,
                    'phase_template_line_id': line.id,
                    'sequence': line.sequence,
                    'allocated_hours': line._compute_hours(element),
                })
                meta.append((element, line))

        if not vals_list:
            return Task
        tasks = Task.create(vals_list)

        if 'depend_on_ids' in Task._fields:
            created = {(el.id, line.id): task for (el, line), task in zip(meta, tasks)}
            for (element, line), task in zip(meta, tasks):
                dep_line = line.depends_on_line_id
                if not dep_line:
                    continue
                previous = created.get((element.id, dep_line.id)) or \
                    element.task_ids.filtered(
                        lambda t: t.phase_template_line_id == dep_line)[:1]
                if previous:
                    task.write({'depend_on_ids': [Command.link(previous.id)]})
        return tasks

    def action_generate_tasks(self):
        self._generate_tasks()
        return True

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Phases de %s") % self.name,
            'res_model': 'project.task',
            'view_mode': 'tree,form',
            'domain': [('construction_element_id', '=', self.id)],
            'context': {'default_construction_element_id': self.id,
                        'default_parent_id': self.ouvrage_task_id.id,
                        'default_project_id': self.project_id.id},
        }


class ConstructionElementValue(models.Model):
    """Caractéristique d'un élément : le reflet, sur un ouvrage donné, d'une
    ligne déclarée par son type.

    Ces lignes ne stockent PAS la valeur : elles la lisent et l'écrivent dans
    le stockage réel de l'élément (le JSON `dimensions` pour une dimension, la
    colonne `qty_*` pour un métré). C'est ce qui permet à la fiche de suivre
    ce que le type déclare, sans jamais dupliquer la donnée ni casser le
    chiffrage des phases, qui lit ces colonnes.

    On n'en ajoute ni n'en retire à la main : la liste vient du type
    (cf. `construction.element._sync_value_lines`)."""

    _name = 'construction.element.value'
    _description = "Caractéristique d'un élément de construction"
    _order = 'sequence, id'
    _rec_name = 'field_id'

    element_id = fields.Many2one(
        'construction.element', string="Élément",
        required=True, ondelete='cascade', index=True)
    field_id = fields.Many2one(
        'construction.element.type.field', string="Caractéristique",
        required=True, ondelete='cascade', index=True)

    sequence = fields.Integer(related='field_id.sequence', store=True)
    name = fields.Char(related='field_id.name', string="Libellé", readonly=True)
    code = fields.Char(related='field_id.code', string="Clé", readonly=True)
    nature = fields.Selection(related='field_id.nature', readonly=True)
    uom = fields.Selection(related='field_id.uom', string="Unité", readonly=True)
    required = fields.Boolean(related='field_id.required', string="Obligatoire",
                              readonly=True)

    value = fields.Float(
        "Valeur", compute='_compute_value', inverse='_inverse_value',
        help="Saisie ici, elle est écrite dans la dimension ou le métré "
             "correspondant de l'élément.")
    is_missing = fields.Boolean("Manquante", compute='_compute_value')

    _sql_constraints = [
        ('field_uniq', 'unique(element_id, field_id)',
         "Cette caractéristique figure déjà sur cet élément."),
    ]

    @api.depends('field_id', 'element_id.dimensions',
                 'element_id.qty_beton_m3', 'element_id.qty_acier_kg',
                 'element_id.qty_coffrage_m2', 'element_id.qty_surface_m2')
    def _compute_value(self):
        for line in self:
            line.value = line.element_id._characteristic_value(line.field_id)
            line.is_missing = line.required and not line.value

    def _inverse_value(self):
        for line in self:
            line.element_id._set_characteristic(line.field_id, line.value)
