import base64
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import ezdxf
except ImportError:
    ezdxf = None
    _logger.warning("La librairie 'ezdxf' n'est pas installée. "
                     "Installez-la avec : pip install ezdxf")


# Table de correspondance des codes de version DXF vers un nom lisible
DXF_VERSION_NAMES = {
    "AC1006": "R10",
    "AC1009": "R11/R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "AutoCAD 2000",
    "AC1018": "AutoCAD 2004",
    "AC1021": "AutoCAD 2007",
    "AC1024": "AutoCAD 2010",
    "AC1027": "AutoCAD 2013",
    "AC1032": "AutoCAD 2018",
}

# Table de correspondance des codes d'unités DXF ($INSUNITS)
DXF_UNITS = {
    0: "Non spécifiées",
    1: "Pouces",
    2: "Pieds",
    3: "Miles",
    4: "Millimètres",
    5: "Centimètres",
    6: "Mètres",
    7: "Kilomètres",
    8: "Micropouces",
    9: "Mils",
    10: "Yards",
    11: "Angströms",
    12: "Nanomètres",
    13: "Microns",
    14: "Décimètres",
    15: "Décamètres",
    16: "Hectomètres",
    17: "Gigamètres",
    18: "Unités astronomiques",
    19: "Années-lumière",
    20: "Parsecs",
}


class ConstructionDwgMetadata(models.Model):
    _name = "construction.dwg.metadata"
    _description = "Métadonnées extraites d'un fichier DXF"
    _rec_name = "dwg_file_id"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # --- Version et unités ---
    version_code = fields.Char(string="Code version DXF", readonly=True)
    version_name = fields.Char(string="Version DXF", readonly=True)
    units_code = fields.Integer(string="Code unités", readonly=True)
    units_name = fields.Char(string="Unités", readonly=True)

    # --- Dates ---
    dxf_creation_date = fields.Datetime(string="Date de création (DXF)", readonly=True)
    dxf_update_date = fields.Datetime(string="Dernière modification (DXF)", readonly=True)

    # --- Projet / auteur ---
    project_name = fields.Char(string="Nom du projet (DXF)", readonly=True)
    custom_properties = fields.Text(
        string="Propriétés personnalisées",
        readonly=True,
        help="Stocké en JSON : {clé: valeur}",
    )

    # --- Géométrie ---
    insertion_base_x = fields.Float(string="Point d'insertion X", readonly=True)
    insertion_base_y = fields.Float(string="Point d'insertion Y", readonly=True)
    insertion_base_z = fields.Float(string="Point d'insertion Z", readonly=True)

    ext_min_x = fields.Float(string="Limites min X", readonly=True)
    ext_min_y = fields.Float(string="Limites min Y", readonly=True)
    ext_min_z = fields.Float(string="Limites min Z", readonly=True)
    ext_max_x = fields.Float(string="Limites max X", readonly=True)
    ext_max_y = fields.Float(string="Limites max Y", readonly=True)
    ext_max_z = fields.Float(string="Limites max Z", readonly=True)

    # --- Statistiques ---
    nb_layers = fields.Integer(string="Nombre de calques", readonly=True)
    nb_blocks = fields.Integer(string="Nombre de blocs", readonly=True)
    nb_entities_modelspace = fields.Integer(string="Nombre d'entités (modelspace)", readonly=True)
    nb_text_styles = fields.Integer(string="Nombre de styles de texte", readonly=True)
    nb_linetypes = fields.Integer(string="Nombre de types de lignes", readonly=True)

    file_size_bytes = fields.Integer(string="Taille du fichier (octets)", readonly=True)

    extracted_at = fields.Datetime(
        string="Date d'extraction", default=fields.Datetime.now, readonly=True
    )

    # ---------------------------------------------------------
    # Utilitaires
    # ---------------------------------------------------------

    @staticmethod
    def _julian_to_datetime(julian_value):
        """Convertit une date julienne AutoCAD (ex: $TDCREATE) en datetime Python."""
        if not julian_value:
            return None
        try:
            epoch = datetime(1858, 11, 17)  # époque julienne modifiée
            jd = float(julian_value) - 2400000.5
            return epoch + timedelta(days=jd)
        except (ValueError, OverflowError, TypeError):
            return None

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait les métadonnées du champ dxf_file d'un enregistrement
        construction.dwg.files et crée/met à jour le record de métadonnées associé.
        """
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur. "
                "Contactez votre administrateur système."
            )

        dwg_file.ensure_one()

        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les métadonnées.")

        file_bytes = base64.b64decode(dwg_file.dxf_file)

        # ezdxf.readfile nécessite un chemin disque, on passe donc par un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=True) as tmp:
            tmp.write(file_bytes)
            tmp.flush()

            try:
                doc = ezdxf.readfile(tmp.name)
            except IOError as e:
                raise UserError(f"Impossible de lire le fichier DXF : {e}")
            except ezdxf.DXFStructureError as e:
                raise UserError(f"Fichier DXF invalide ou corrompu : {e}")

            header = doc.header

            def hget(var, default=None):
                return header.get(var, default)

            version_code = doc.dxfversion
            units_code = hget("$INSUNITS", 0)

            insbase = list(hget("$INSBASE", (0, 0, 0)))
            extmin = list(hget("$EXTMIN", (0, 0, 0)))
            extmax = list(hget("$EXTMAX", (0, 0, 0)))

            custom_props = {}
            try:
                custom_props = dict(doc.header.custom_vars.properties)
            except AttributeError:
                pass

            import json
            vals = {
                "dwg_file_id": dwg_file.id,
                "version_code": version_code,
                "version_name": DXF_VERSION_NAMES.get(version_code, "Inconnue"),
                "units_code": units_code,
                "units_name": DXF_UNITS.get(units_code, "Inconnue"),
                "dxf_creation_date": self._julian_to_datetime(hget("$TDCREATE")),
                "dxf_update_date": self._julian_to_datetime(hget("$TDUPDATE")),
                "project_name": hget("$PROJECTNAME", "") or None,
                "custom_properties": json.dumps(custom_props, ensure_ascii=False),
                "insertion_base_x": insbase[0] if len(insbase) > 0 else 0.0,
                "insertion_base_y": insbase[1] if len(insbase) > 1 else 0.0,
                "insertion_base_z": insbase[2] if len(insbase) > 2 else 0.0,
                "ext_min_x": extmin[0] if len(extmin) > 0 else 0.0,
                "ext_min_y": extmin[1] if len(extmin) > 1 else 0.0,
                "ext_min_z": extmin[2] if len(extmin) > 2 else 0.0,
                "ext_max_x": extmax[0] if len(extmax) > 0 else 0.0,
                "ext_max_y": extmax[1] if len(extmax) > 1 else 0.0,
                "ext_max_z": extmax[2] if len(extmax) > 2 else 0.0,
                "nb_layers": len(doc.layers),
                "nb_blocks": len(doc.blocks),
                "nb_entities_modelspace": len(doc.modelspace()),
                "nb_text_styles": len(doc.styles),
                "nb_linetypes": len(doc.linetypes),
                "file_size_bytes": len(file_bytes),
                "extracted_at": fields.Datetime.now(),
            }

        # Un seul enregistrement de métadonnées par fichier DWG : on met à jour s'il existe déjà
        existing = self.search([("dwg_file_id", "=", dwg_file.id)], limit=1)
        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)