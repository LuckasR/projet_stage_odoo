from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ...service.dxf_layers import ELEMENT_TYPE_ROLE, ROLES, LayerConfig

ROLE_SELECTION = [(code, "%s — %s" % (group, label)) for code, label, group, _names in ROLES] + [
    (ELEMENT_TYPE_ROLE, "Moteur « blocs » — Type d'élément"),
]


class ConstructionDxfLayerConvention(models.Model):
    """Convention de nommage des calques d'un bureau d'études : pour chaque
    rôle que cherchent les moteurs d'analyse (« mur extérieur »,
    « poteau »...), les noms de calque qui le désignent.

    La convention « All » ne porte aucun nom : elle réunit ceux de toutes
    les autres. C'est la convention par défaut d'un chantier ; en choisir
    une autre sur le chantier limite l'analyse à ses seuls noms."""
    _name = 'construction.dxf.layer.convention'
    _description = "Convention de calques DXF"
    _order = 'is_all desc, sequence, name'

    name = fields.Char("Convention", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_all = fields.Boolean(
        "Toutes les conventions", readonly=True, copy=False,
        help="Convention « All » : elle réunit les noms de calque de toutes les "
             "autres conventions actives.")
    note = fields.Text("Usage", help="Bureau d'études, architecte ou type de plans concernés.")
    line_ids = fields.One2many('construction.dxf.layer.name', 'convention_id', string="Noms de calque")
    effective_line_ids = fields.Many2many(
        'construction.dxf.layer.name', compute='_compute_effective_line_ids',
        string="Noms pris en compte")
    line_count = fields.Integer("Noms", compute='_compute_effective_line_ids')
    project_count = fields.Integer("Chantiers", compute='_compute_project_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Une convention de calques porte déjà ce nom."),
    ]

    def _effective_lines(self):
        """Noms que l'analyse prend en compte avec cette convention."""
        self.ensure_one()
        if self.is_all:
            return self.search([('is_all', '=', False)]).line_ids
        return self.line_ids

    def _compute_effective_line_ids(self):
        for convention in self:
            lines = convention._effective_lines()
            convention.effective_line_ids = lines
            convention.line_count = len(lines)

    def _compute_project_count(self):
        counts = dict(self.env['project.project']._read_group(
            [('dxf_layer_convention_id', 'in', self.ids)],
            ['dxf_layer_convention_id'], ['__count']))
        for convention in self:
            convention.project_count = counts.get(convention, 0)

    @api.model
    def _get_all(self):
        # Par l'identifiant XML seulement : sert de valeur par défaut au champ
        # du chantier, évaluée à la création de la colonne, quand la table des
        # conventions n'existe pas encore (la migration complète ensuite).
        return (self.env.ref('miro_construction_project.dxf_layer_convention_all',
                             raise_if_not_found=False)
                or self.browse())

    def _layer_config(self):
        """Configuration transmise aux moteurs d'analyse (Python pur, sans
        Odoo) : noms par rôle, et par type d'élément pour le moteur
        « blocs »."""
        self.ensure_one()
        names, element_types = defaultdict(list), defaultdict(list)
        lines = self._effective_lines().sorted(
            lambda l: (l.convention_id.sequence, l.sequence, l.id))
        for line in lines:
            if line.role == ELEMENT_TYPE_ROLE:
                element_types[line.element_type_id.id].append(line.name)
            else:
                names[line.role].append(line.name)
        return LayerConfig(names, element_types, label=self.name)

    @api.constrains('is_all')
    def _check_single_all(self):
        if self.search_count([('is_all', '=', True)]) > 1:
            raise ValidationError(_("Il ne peut y avoir qu'une convention « All »."))

    def write(self, vals):
        if 'active' in vals and not vals['active'] and self.filtered('is_all'):
            raise UserError(_("La convention « All » ne peut pas être archivée."))
        return super().write(vals)

    def unlink(self):
        if self.filtered('is_all'):
            raise UserError(_("La convention « All » ne peut pas être supprimée."))
        return super().unlink()

    def action_open_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Chantiers — %s") % self.name,
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [('dxf_layer_convention_id', '=', self.id)],
        }


class ConstructionDxfLayerName(models.Model):
    """Un nom de calque qui désigne un rôle dans une convention. Le joker
    « * » remplace n'importe quelle suite de caractères (« A-MUR-EXT* »
    reconnaît « A-MUR-EXT-RDC ») ; majuscules et accents sont ignorés."""
    _name = 'construction.dxf.layer.name'
    _description = "Nom de calque DXF"
    _order = 'convention_id, role, sequence, id'
    _rec_name = 'name'

    convention_id = fields.Many2one(
        'construction.dxf.layer.convention', string="Convention", required=True,
        ondelete='cascade', index=True, domain=[('is_all', '=', False)])
    sequence = fields.Integer(default=10)
    role = fields.Selection(ROLE_SELECTION, string="Ce que cherche l'analyse", required=True,
                            index=True)
    element_type_id = fields.Many2one(
        'construction.element.type', string="Type d'élément", ondelete='cascade',
        help="Moteur « blocs » : un bloc placé sur ce calque est détecté comme un "
             "élément de ce type.")
    name = fields.Char(
        "Nom du calque", required=True,
        help="Nom exact du calque, ou avec le joker * (ex. : A-MUR-EXT*). "
             "Majuscules et accents ne comptent pas.")
    active = fields.Boolean(default=True)

    @api.constrains('role', 'element_type_id', 'convention_id', 'name')
    def _check_line(self):
        for line in self:
            if line.convention_id.is_all:
                raise ValidationError(_(
                    "La convention « All » réunit les autres : ajoutez le nom « %s » "
                    "dans une convention précise.") % line.name)
            if (line.role == ELEMENT_TYPE_ROLE) != bool(line.element_type_id):
                raise ValidationError(_(
                    "« %s » : un type d'élément est requis pour le moteur « blocs », et "
                    "seulement pour lui.") % line.name)
            if not (line.name or '').strip(' *'):
                raise ValidationError(_("Un nom de calque ne peut pas être vide ou n'être qu'un joker."))


class ProjectProject(models.Model):
    _inherit = 'project.project'

    dxf_layer_convention_id = fields.Many2one(
        'construction.dxf.layer.convention', string="Convention de calques DXF",
        default=lambda self: self.env['construction.dxf.layer.convention']._get_all(),
        help="Noms de calque cherchés par l'analyse des plans DXF de ce chantier. "
             "« All » prend en compte toutes les conventions ; une convention précise "
             "limite l'analyse à ses seuls noms.")


class ConstructionDwgFiles(models.Model):
    _inherit = 'construction.dwg.files'

    dxf_layer_convention_id = fields.Many2one(
        related='project_id.dxf_layer_convention_id', string="Convention de calques")

    def _layer_config(self):
        """Noms de calque à chercher dans ce plan : convention du chantier,
        « All » à défaut."""
        self.ensure_one()
        convention = (self.project_id.dxf_layer_convention_id
                      or self.env['construction.dxf.layer.convention']._get_all())
        return convention._layer_config() if convention else LayerConfig.default()


class ConstructionElementType(models.Model):
    _inherit = 'construction.element.type'

    dxf_layer_name_ids = fields.One2many(
        'construction.dxf.layer.name', 'element_type_id', string="Calques DXF",
        help="Moteur « blocs » : un bloc placé sur l'un de ces calques est détecté "
             "comme un élément de ce type. Les noms sont rangés par convention.")
