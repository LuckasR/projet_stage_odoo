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


ANNOTATION_TYPES = [
    ('TEXT', 'Texte simple'),
    ('MTEXT', 'Texte multiligne'),
    ('DIMENSION', 'Cotation'),
    ('LEADER', "Ligne d'indication"),
    ('MLEADER', "Ligne d'indication avancée"),
]


class ConstructionDwgAnnotation(models.Model):
    _name = "construction.dwg.annotation"
    _description = "Annotation textuelle d'un fichier DXF"
    _rec_name = "text_content"
    _order = "annotation_type, id"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    annotation_type = fields.Selection(
        ANNOTATION_TYPES,
        string="Type d'annotation",
        required=True,
        index=True,
    )
    layer = fields.Char(string="Calque", index=True)
    handle = fields.Char(string="Référence (handle DXF)")

    text_content = fields.Text(string="Contenu texte")
    text_style = fields.Char(string="Style de texte")
    text_height = fields.Float(string="Hauteur de texte", digits=(16, 4))
    rotation = fields.Float(string="Rotation (°)", digits=(16, 4))

    # Position d'ancrage (insertion point pour TEXT/MTEXT, point de définition pour DIMENSION/LEADER)
    pos_x = fields.Float(string="Position X", digits=(16, 4))
    pos_y = fields.Float(string="Position Y", digits=(16, 4))
    pos_z = fields.Float(string="Position Z", digits=(16, 4))

    # Spécifique aux cotations (DIMENSION)
    dimension_measurement = fields.Float(
        string="Valeur mesurée (cotation)",
        digits=(16, 4),
        help="Valeur numérique de la cotation, si applicable.",
    )
    dimension_type = fields.Char(
        string="Type de cotation",
        help="Linéaire, angulaire, rayon, diamètre, etc.",
    )

    # Fourre-tout pour données additionnelles spécifiques au type
    extra_data = fields.Text(string="Données additionnelles (JSON)")

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait toutes les annotations (TEXT, MTEXT, DIMENSION, LEADER, MLEADER)
        du fichier DXF associé à dwg_file, en remplaçant les annotations existantes."""
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur. "
                "Contactez votre administrateur système."
            )

        dwg_file.ensure_one()

        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les annotations.")

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

            annotation_vals = []
            msp = doc.modelspace()

            # --- TEXT ---
            for entity in msp.query("TEXT"):
                try:
                    p = entity.dxf.insert
                    annotation_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "annotation_type": "TEXT",
                        "layer": getattr(entity.dxf, "layer", "0"),
                        "handle": getattr(entity.dxf, "handle", False),
                        "text_content": entity.dxf.text,
                        "text_style": getattr(entity.dxf, "style", False),
                        "text_height": getattr(entity.dxf, "height", 0.0),
                        "rotation": getattr(entity.dxf, "rotation", 0.0),
                        "pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                    })
                except Exception:
                    _logger.exception(
                        "Erreur extraction TEXT (handle=%s)",
                        getattr(entity.dxf, "handle", "?")
                    )

            # --- MTEXT ---
            for entity in msp.query("MTEXT"):
                try:
                    p = entity.dxf.insert
                    # entity.text peut contenir des codes de formatage MTEXT (\P, \A1;, etc.)
                    # on utilise plain_text() si disponible pour un texte propre
                    try:
                        content = entity.plain_text()
                    except AttributeError:
                        content = entity.text

                    annotation_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "annotation_type": "MTEXT",
                        "layer": getattr(entity.dxf, "layer", "0"),
                        "handle": getattr(entity.dxf, "handle", False),
                        "text_content": content,
                        "text_style": getattr(entity.dxf, "style", False),
                        "text_height": getattr(entity.dxf, "char_height", 0.0),
                        "rotation": getattr(entity.dxf, "rotation", 0.0),
                        "pos_x": p.x, "pos_y": p.y, "pos_z": p.z,
                    })
                except Exception:
                    _logger.exception(
                        "Erreur extraction MTEXT (handle=%s)",
                        getattr(entity.dxf, "handle", "?")
                    )

            # --- DIMENSION ---
            for entity in msp.query("DIMENSION"):
                try:
                    measurement = None
                    try:
                        measurement = entity.get_measurement()
                    except Exception:
                        pass

                    # Le point de définition (defpoint) sert de position de référence
                    defpoint = getattr(entity.dxf, "defpoint", None)
                    px, py, pz = (defpoint.x, defpoint.y, defpoint.z) if defpoint else (0.0, 0.0, 0.0)

                    annotation_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "annotation_type": "DIMENSION",
                        "layer": getattr(entity.dxf, "layer", "0"),
                        "handle": getattr(entity.dxf, "handle", False),
                        "text_content": entity.dxf.text if entity.dxf.hasattr("text") else "",
                        "dimension_measurement": measurement or 0.0,
                        "dimension_type": str(getattr(entity.dxf, "dimtype", "")),
                        "pos_x": px, "pos_y": py, "pos_z": pz,
                    })
                except Exception:
                    _logger.exception(
                        "Erreur extraction DIMENSION (handle=%s)",
                        getattr(entity.dxf, "handle", "?")
                    )

            # --- LEADER ---
            for entity in msp.query("LEADER"):
                try:
                    vertices = [list(v) for v in entity.vertices] if hasattr(entity, "vertices") else []
                    p = vertices[0] if vertices else [0.0, 0.0, 0.0]
                    annotation_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "annotation_type": "LEADER",
                        "layer": getattr(entity.dxf, "layer", "0"),
                        "handle": getattr(entity.dxf, "handle", False),
                        "pos_x": p[0], "pos_y": p[1], "pos_z": p[2] if len(p) > 2 else 0.0,
                        "extra_data": json.dumps({"vertices": vertices}),
                    })
                except Exception:
                    _logger.exception(
                        "Erreur extraction LEADER (handle=%s)",
                        getattr(entity.dxf, "handle", "?")
                    )

            # --- MLEADER ---
            for entity in msp.query("MLEADER"):
                try:
                    content = ""
                    try:
                        if entity.context.mtext:
                            content = entity.context.mtext.plain_text()
                    except Exception:
                        pass

                    p = (0.0, 0.0, 0.0)
                    try:
                        insert = entity.context.mtext.insert if entity.context.mtext else None
                        if insert:
                            p = (insert.x, insert.y, insert.z)
                    except Exception:
                        pass

                    annotation_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "annotation_type": "MLEADER",
                        "layer": getattr(entity.dxf, "layer", "0"),
                        "handle": getattr(entity.dxf, "handle", False),
                        "text_content": content,
                        "pos_x": p[0], "pos_y": p[1], "pos_z": p[2],
                    })
                except Exception:
                    _logger.exception(
                        "Erreur extraction MLEADER (handle=%s)",
                        getattr(entity.dxf, "handle", "?")
                    )

            _logger.info(
                "Annotations extraites pour %s : %d", dwg_file.filename, len(annotation_vals)
            )

        # Supprime les annotations précédentes de ce fichier avant de recréer
        existing = self.search([("dwg_file_id", "=", dwg_file.id)])
        if existing:
            existing.unlink()

        if not annotation_vals:
            return self.browse()

        return self.create(annotation_vals)

    # ---------------------------------------------------------
    # Statistiques
    # ---------------------------------------------------------

    @api.model
    def get_annotation_counts(self, dwg_file_id):
        """Retourne {annotation_type: count} pour un fichier donné."""
        annotations = self.search([("dwg_file_id", "=", dwg_file_id)])
        counts = {}
        for a in annotations:
            counts[a.annotation_type] = counts.get(a.annotation_type, 0) + 1
        return counts

    @api.model
    def search_text(self, dwg_file_id, keyword):
        """Recherche un mot-clé dans le contenu textuel des annotations
        (utile pour retrouver un label de pièce, une référence, etc.)."""
        return self.search([
            ("dwg_file_id", "=", dwg_file_id),
            ("text_content", "ilike", keyword),
        ])