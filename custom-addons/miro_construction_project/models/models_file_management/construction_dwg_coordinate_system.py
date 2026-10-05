import base64
import json
import logging
import tempfile

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import ezdxf
except ImportError:
    ezdxf = None


class ConstructionDwgCoordinateSystem(models.Model):
    _name = "construction.dwg.coordinate.system"
    _description = "Système de coordonnées d'un fichier DXF"
    _rec_name = "name"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Nom du SCU", default="Monde (WCS)")
    is_world_ucs = fields.Boolean(string="SCU Monde (WCS)", default=True)

    # --- Origine et axes du SCU ---
    origin_x = fields.Float(string="Origine X", digits=(16, 6))
    origin_y = fields.Float(string="Origine Y", digits=(16, 6))
    origin_z = fields.Float(string="Origine Z", digits=(16, 6))

    x_axis_x = fields.Float(string="Axe X - composante X", digits=(16, 6), default=1.0)
    x_axis_y = fields.Float(string="Axe X - composante Y", digits=(16, 6))
    x_axis_z = fields.Float(string="Axe X - composante Z", digits=(16, 6))

    y_axis_x = fields.Float(string="Axe Y - composante X", digits=(16, 6))
    y_axis_y = fields.Float(string="Axe Y - composante Y", digits=(16, 6), default=1.0)
    y_axis_z = fields.Float(string="Axe Y - composante Z", digits=(16, 6))

    # --- Angles ---
    angle_base = fields.Float(string="Angle de référence (°)", digits=(16, 4))
    angle_direction = fields.Selection(
        [('0', 'Sens antihoraire'), ('1', 'Sens horaire')],
        string="Sens des angles",
        default='0',
    )

    # --- Unités / système de mesure ---
    measurement_system = fields.Selection(
        [('0', 'Métrique'), ('1', 'Impérial')],
        string="Système de mesure",
    )

    # --- Géoréférencement (si disponible, ex: AutoCAD Map 3D / Civil 3D) ---
    is_geolocated = fields.Boolean(string="Géoréférencé", default=False)
    geo_design_point_x = fields.Float(string="Point de conception (X)", digits=(16, 6))
    geo_design_point_y = fields.Float(string="Point de conception (Y)", digits=(16, 6))
    geo_reference_point_x = fields.Float(string="Point de référence géo (longitude/X)", digits=(16, 8))
    geo_reference_point_y = fields.Float(string="Point de référence géo (latitude/Y)", digits=(16, 8))
    coordinate_system_name = fields.Char(
        string="Système de projection",
        help="Ex: nom EPSG ou système de projection utilisé (WGS84, Lambert93, etc.)",
    )

    extra_data = fields.Text(string="Données additionnelles (JSON)")

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait le(s) système(s) de coordonnées du fichier DXF associé,
        en remplaçant les enregistrements existants pour ce fichier."""
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur."
            )

        dwg_file.ensure_one()

        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les systèmes de coordonnées.")

        file_bytes = base64.b64decode(dwg_file.dxf_file)

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

            cs_vals = []

            # --- 1. SCU courant (WCS ou UCS actif), depuis le header ---
            try:
                ucsorg = hget("$UCSORG", (0.0, 0.0, 0.0))
                ucsxdir = hget("$UCSXDIR", (1.0, 0.0, 0.0))
                ucsydir = hget("$UCSYDIR", (0.0, 1.0, 0.0))
                angbase = hget("$ANGBASE", 0.0)
                angdir = hget("$ANGDIR", 0)
                measurement = hget("$MEASUREMENT", 0)

                is_world = (
                    tuple(ucsorg) == (0.0, 0.0, 0.0)
                    and tuple(ucsxdir) == (1.0, 0.0, 0.0)
                    and tuple(ucsydir) == (0.0, 1.0, 0.0)
                )

                cs_vals.append({
                    "dwg_file_id": dwg_file.id,
                    "name": "Monde (WCS)" if is_world else "SCU personnalisé (courant)",
                    "is_world_ucs": is_world,
                    "origin_x": ucsorg[0], "origin_y": ucsorg[1], "origin_z": ucsorg[2],
                    "x_axis_x": ucsxdir[0], "x_axis_y": ucsxdir[1], "x_axis_z": ucsxdir[2],
                    "y_axis_x": ucsydir[0], "y_axis_y": ucsydir[1], "y_axis_z": ucsydir[2],
                    "angle_base": angbase,
                    "angle_direction": str(angdir),
                    "measurement_system": str(measurement),
                })
            except Exception:
                _logger.exception(
                    "Erreur extraction du SCU courant (header) pour %s", dwg_file.filename
                )

            # --- 2. SCU nommés définis dans la table UCS ---
            try:
                for ucs in doc.tables.ucs:
                    origin = ucs.dxf.origin
                    xaxis = ucs.dxf.xaxis
                    yaxis = ucs.dxf.yaxis
                    cs_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "name": ucs.dxf.name or "SCU sans nom",
                        "is_world_ucs": False,
                        "origin_x": origin.x, "origin_y": origin.y, "origin_z": origin.z,
                        "x_axis_x": xaxis.x, "x_axis_y": xaxis.y, "x_axis_z": xaxis.z,
                        "y_axis_x": yaxis.x, "y_axis_y": yaxis.y, "y_axis_z": yaxis.z,
                    })
            except Exception:
                _logger.exception(
                    "Erreur extraction des SCU nommés (table UCS) pour %s", dwg_file.filename
                )

            # --- 3. Géoréférencement (objet GEODATA, si présent) ---
            try:
                geodata = None
                # GEODATA est attaché au modelspace via une extension dictionary
                msp = doc.modelspace()
                if hasattr(msp, "get_geodata"):
                    geodata = msp.get_geodata()

                if geodata is not None:
                    design_point = geodata.dxf.design_point
                    ref_point = getattr(geodata.dxf, "reference_point", None)
                    coord_system = getattr(geodata.dxf, "coordinate_system_definition", "") or ""

                    cs_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "name": "Géoréférencement (GEODATA)",
                        "is_world_ucs": False,
                        "is_geolocated": True,
                        "geo_design_point_x": design_point.x,
                        "geo_design_point_y": design_point.y,
                        "geo_reference_point_x": ref_point.x if ref_point else 0.0,
                        "geo_reference_point_y": ref_point.y if ref_point else 0.0,
                        "coordinate_system_name": coord_system[:200] if coord_system else False,
                        "extra_data": json.dumps({"raw_coordinate_system": coord_system}),
                    })
                    _logger.info(
                        "Géoréférencement détecté pour %s : %s",
                        dwg_file.filename, coord_system
                    )
            except Exception:
                # Absent dans la majorité des plans "simples" (non Civil 3D/Map 3D) : normal, pas grave
                _logger.debug(
                    "Pas de géoréférencement (GEODATA) trouvé pour %s", dwg_file.filename
                )

            _logger.info(
                "Systèmes de coordonnées extraits pour %s : %d",
                dwg_file.filename, len(cs_vals)
            )

        existing = self.search([("dwg_file_id", "=", dwg_file.id)])
        if existing:
            existing.unlink()

        if not cs_vals:
            return self.browse()

        return self.create(cs_vals)