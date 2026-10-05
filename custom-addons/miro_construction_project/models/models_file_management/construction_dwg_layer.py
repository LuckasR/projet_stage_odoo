import base64
import logging
import tempfile

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import ezdxf
except ImportError:
    ezdxf = None


class ConstructionDwgLayer(models.Model):
    _name = "construction.dwg.layer"
    _description = "Calque d'un fichier DXF"
    _rec_name = "name"
    _order = "name"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Nom du calque", required=True)
    color = fields.Integer(string="Couleur (code ACI)", default=7)
    linetype = fields.Char(string="Type de ligne", default="Continuous")
    lineweight = fields.Integer(
        string="Épaisseur de ligne (1/100 mm)",
        help="-1 = par défaut du calque, -2 = par bloc, -3 = par entité",
    )
    visible = fields.Boolean(string="Visible", default=True)
    entity_count = fields.Integer(string="Nombre d'objets")

    _sql_constraints = [
        (
            "unique_layer_per_file",
            "unique(dwg_file_id, name)",
            "Un calque de ce nom existe déjà pour ce fichier.",
        ),
    ]

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait les calques du fichier DXF associé à dwg_file et les stocke,
        en remplaçant les calques existants pour ce fichier (ré-extraction)."""
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur. "
                "Contactez votre administrateur système."
            )

        dwg_file.ensure_one()

        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les calques.")

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

            # Compter les entités par calque dans le modelspace
            # Note : ne compte pas les entités imbriquées dans des blocs (INSERT)
            entity_counts = {}
            for entity in doc.modelspace():
                layer_name = entity.dxf.layer
                entity_counts[layer_name] = entity_counts.get(layer_name, 0) + 1

            layer_vals = []
            for layer in doc.layers:
                layer_vals.append({
                    "dwg_file_id": dwg_file.id,
                    "name": layer.dxf.name,
                    "color": layer.color if layer.color is not None else 7,
                    "linetype": layer.dxf.linetype or "Continuous",
                    "lineweight": layer.dxf.get("lineweight", -1),
                    "visible": not layer.is_off(),
                    "entity_count": entity_counts.get(layer.dxf.name, 0),
                })

        # Supprime les calques précédents de ce fichier avant de recréer
        # (utile si on ré-analyse un fichier déjà traité)
        existing = self.search([("dwg_file_id", "=", dwg_file.id)])
        if existing:
            existing.unlink()

        return self.create(layer_vals)