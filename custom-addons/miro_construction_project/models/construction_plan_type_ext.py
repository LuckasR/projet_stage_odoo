import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ConstructionPlanType(models.Model):
    _inherit = 'construction.plan.type'

    analyzer = fields.Selection(
        [('none', "Aucune analyse"),
         ('walls', "Détection de murs"),
         ('elements', "Éléments de construction (blocs DXF)"),
         ('footings', "Fondations (semelles, longrines)"),
         ('facade', "Façades (ouvertures, niveaux, cotes)")],
        string="Analyse automatique",
        help="Analyse lancée à l'import d'un plan de ce type. Un plan qui cumule plusieurs "
             "types lance l'union de leurs analyses (sans doublon).\n"
             "Pour ajouter une analyse : selection_add ici + méthode "
             "_enqueue_analysis_<code>() sur construction.dwg.files.")

    # Analyse livrée par une version antérieure et devenue inopérante. Le
    # moteur « blocs » ne peut plus rien trouver sur un plan de fondation :
    # semelles, poteaux et longrines sont désormais reconnus par leur
    # géométrie (cf. _clean_geometric_element_types), donc plus aucun type
    # d'élément n'a de mot-clé DXF à y chercher. Un plan FOND resté sur
    # « elements » ne lançait donc plus AUCUNE analyse.
    _STALE_ANALYZERS = {'FOND': ('elements', 'footings')}

    @api.model
    def _set_default_analyzers(self):
        """Renseigne les analyses par défaut sur les types existants. Ne modifie jamais
        une valeur déjà choisie (y compris « Aucune analyse »), à l'exception
        des valeurs livrées devenues inopérantes (cf. _STALE_ANALYZERS)."""
        defaults = {'ARCH': 'walls', 'FOND': 'footings', 'COFF': 'elements'}
        for code, analyzer in defaults.items():
            self.search([('code', '=', code), ('analyzer', '=', False)]).write(
                {'analyzer': analyzer})

        for code, (stale, corrected) in self._STALE_ANALYZERS.items():
            obsolete = self.search([('code', '=', code), ('analyzer', '=', stale)])
            if obsolete:
                obsolete.analyzer = corrected
                _logger.info(
                    "Type de plan %s : analyse « %s » devenue inopérante, "
                    "remplacée par « %s »", code, stale, corrected)

        fondation_types = self.search([('code', 'in', ['FOND', 'COFF'])])
        self._clean_geometric_element_types(fondation_types)

    # Mots-clés DXF livrés par une version antérieure du module. On ne retire
    # QUE ces valeurs-là : un mot-clé que l'utilisateur a choisi lui-même est
    # toujours respecté.
    _SHIPPED_DXF_KEYWORDS = {
        'semelle': {'dxf_block_keyword': 'SEMELLE', 'dxf_layer_keyword': 'SEMELLE'},
        'semelle_filante': {'dxf_layer_keyword': 'S-SEM-FIL'},
        'longrine': {'dxf_layer_keyword': 'S-LON'},
        'poteau': {},
    }

    @api.model
    def _clean_geometric_element_types(self, fondation_types):
        """Les ouvrages de fondation (semelle, poteau, semelle filante,
        longrine) sont reconnus par leur GÉOMÉTRIE sur les calques S-SEM,
        S-POT, S-SEM-FIL et S-LON — jamais par un bloc DXF.

        Les versions précédentes leur avaient donné des mots-clés : le moteur
        « blocs » les jugeait alors applicables au plan de fondation et
        échouait en les cherchant parmi les INSERT (« Aucun bloc du plan ne
        correspond aux types d'éléments applicables »), alors même que le
        moteur « fondations » savait les lire. On retire ces mots-clés et on
        rattache les types aux plans de fondation."""
        for code, keywords in self._SHIPPED_DXF_KEYWORDS.items():
            etype = self.env['construction.element.type'].search(
                [('code', '=', code)], limit=1)
            if not etype:
                continue
            for field_name, shipped_value in keywords.items():
                if etype[field_name] == shipped_value:
                    etype[field_name] = False
            if not etype.plan_type_ids and fondation_types:
                etype.plan_type_ids = fondation_types
