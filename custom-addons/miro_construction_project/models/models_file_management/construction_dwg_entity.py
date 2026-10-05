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


# Types géométriques principaux
GEOMETRY_TYPES = (
    'POINT', 'LINE', 'CIRCLE', 'ARC', 'ELLIPSE',
    'LWPOLYLINE', 'POLYLINE', 'SPLINE',
    '3DFACE', '3DSOLID', 'MESH', 'SURFACE',
)

# Objets non géométriques (organisation / annotation)
ANNOTATION_TYPES = (
    'TEXT', 'MTEXT', 'INSERT', 'HATCH',
    'DIMENSION', 'LEADER', 'MLEADER', 'IMAGE', 'WIPEOUT',
)

ALL_SUPPORTED_TYPES = GEOMETRY_TYPES + ANNOTATION_TYPES


class ConstructionDwgEntity(models.Model):
    _name = "construction.dwg.entity"
    _description = "Entité géométrique/annotation d'un fichier DXF"
    _rec_name = "handle"
    _order = "entity_type, id"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    entity_type = fields.Selection(
        [(t, t) for t in ALL_SUPPORTED_TYPES],
        string="Type DXF",
        required=True,
        index=True,
    )
    category = fields.Selection(
        [
            ('geometry', 'Géométrie'),
            ('annotation', 'Annotation / Organisation'),
        ],
        string="Catégorie",
        compute="_compute_category",
        store=True,
    )

    layer = fields.Char(string="Calque", index=True)
    handle = fields.Char(string="Référence (handle DXF)")

    # Champ générique contenant les données spécifiques au type
    # (coordonnées, rayon, texte, points de contrôle, etc.)
    data = fields.Text(
        string="Données (JSON)",
        help="Contenu spécifique au type d'entité, stocké en JSON.",
    )

    # Champs communs utiles pour filtrer/rechercher sans parser le JSON
    pos_x = fields.Float(string="Position/Centre X", digits=(16, 4))
    pos_y = fields.Float(string="Position/Centre Y", digits=(16, 4))
    pos_z = fields.Float(string="Position/Centre Z", digits=(16, 4))

    @api.depends('entity_type')
    def _compute_category(self):
        for rec in self:
            rec.category = 'geometry' if rec.entity_type in GEOMETRY_TYPES else 'annotation'

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait toutes les entités supportées du fichier DXF associé
        et les stocke, en remplaçant les entités existantes pour ce fichier."""
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur."
            )

        dwg_file.ensure_one()
        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les entités.")

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

            entity_vals = []
            for entity in doc.modelspace():
                dxftype = entity.dxftype()
                if dxftype not in ALL_SUPPORTED_TYPES:
                    continue  # on ignore les types non listés (INSERT déjà géré ailleurs)
                if dxftype == 'INSERT':
                    continue  # déjà couvert par construction.dwg.block

                vals = self._extract_entity_data(entity, dxftype)
                if vals:
                    vals.update({
                        "dwg_file_id": dwg_file.id,
                        "entity_type": dxftype,
                        "layer": entity.dxf.layer,
                        "handle": entity.dxf.handle,
                    })
                    entity_vals.append(vals)

        existing = self.search([("dwg_file_id", "=", dwg_file.id)])
        if existing:
            existing.unlink()

        return self.create(entity_vals)

    @api.model
    def _extract_entity_data(self, entity, dxftype):
        """Retourne un dict {data: json, pos_x/y/z: ...} selon le type d'entité."""
        try:
            if dxftype == 'POINT':
                p = entity.dxf.location
                return {"pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                        "data": json.dumps({"location": [p.x, p.y, p.z]})}

            if dxftype == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                return {"pos_x": s.x, "pos_y": s.y, "pos_z": s.z,
                        "data": json.dumps({"start": [s.x, s.y, s.z], "end": [e.x, e.y, e.z]})}

            if dxftype == 'CIRCLE':
                c = entity.dxf.center
                return {"pos_x": c.x, "pos_y": c.y, "pos_z": c.z,
                        "data": json.dumps({"center": [c.x, c.y, c.z], "radius": entity.dxf.radius})}

            if dxftype == 'ARC':
                c = entity.dxf.center
                return {"pos_x": c.x, "pos_y": c.y, "pos_z": c.z,
                        "data": json.dumps({
                            "center": [c.x, c.y, c.z],
                            "radius": entity.dxf.radius,
                            "start_angle": entity.dxf.start_angle,
                            "end_angle": entity.dxf.end_angle,
                        })}

            if dxftype == 'ELLIPSE':
                c = entity.dxf.center
                return {"pos_x": c.x, "pos_y": c.y, "pos_z": c.z,
                        "data": json.dumps({
                            "center": [c.x, c.y, c.z],
                            "major_axis": list(entity.dxf.major_axis),
                            "ratio": entity.dxf.ratio,
                            "start_param": entity.dxf.start_param,
                            "end_param": entity.dxf.end_param,
                        })}

            if dxftype == 'LWPOLYLINE':
                points = [list(p) for p in entity.get_points()]
                return {"data": json.dumps({"points": points, "closed": entity.closed})}

            if dxftype == 'POLYLINE':
                points = [list(v.dxf.location) for v in entity.vertices]
                return {"data": json.dumps({"points": points, "closed": entity.is_closed})}

            if dxftype == 'SPLINE':
                control_points = [list(p) for p in entity.control_points]
                return {"data": json.dumps({
                    "control_points": control_points,
                    "knots": list(entity.knots) if entity.knots else [],
                    "degree": entity.dxf.degree,
                })}

            if dxftype == '3DFACE':
                verts = [list(entity.dxf.get(f"vtx{i}")) for i in range(4)
                         if entity.dxf.hasattr(f"vtx{i}")]
                return {"data": json.dumps({"vertices": verts})}

            if dxftype in ('3DSOLID', 'MESH', 'SURFACE'):
                # Géométrie complexe : on stocke juste le handle/type, pas le détail brut
                return {"data": json.dumps({"note": "geometrie_complexe_non_detaillee"})}

            if dxftype == 'TEXT':
                p = entity.dxf.insert
                return {"pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                        "data": json.dumps({"text": entity.dxf.text, "height": entity.dxf.height})}

            if dxftype == 'MTEXT':
                p = entity.dxf.insert
                return {"pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                        "data": json.dumps({"text": entity.text, "height": entity.dxf.char_height})}

            if dxftype == 'HATCH':
                return {"data": json.dumps({
                    "pattern_name": entity.dxf.pattern_name,
                    "solid_fill": bool(entity.dxf.solid_fill),
                })}

            if dxftype == 'DIMENSION':
                return {"data": json.dumps({
                    "text": entity.dxf.text if entity.dxf.hasattr("text") else "",
                    "measurement": entity.get_measurement() if hasattr(entity, "get_measurement") else None,
                })}

            if dxftype in ('LEADER', 'MLEADER'):
                return {"data": json.dumps({"note": f"{dxftype}_non_detaille"})}

            if dxftype == 'IMAGE':
                p = entity.dxf.insert
                return {"pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                        "data": json.dumps({"image_def_handle": str(entity.dxf.image_def_handle)})}

            if dxftype == 'WIPEOUT':
                return {"data": json.dumps({"note": "wipeout_zone_masquee"})}

        except Exception as e:
            _logger.warning("Erreur extraction entité %s (%s) : %s", dxftype, entity.dxf.handle, e)
            return {"data": json.dumps({"error": str(e)})}

        return None

    # ---------------------------------------------------------
    # Statistiques
    # ---------------------------------------------------------

    @api.model
    def get_entity_counts_by_type(self, dwg_file_id):
        """Retourne {entity_type: count} pour un fichier donné."""
        entities = self.search([("dwg_file_id", "=", dwg_file_id)])
        counts = {}
        for e in entities:
            counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        return counts