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


class ConstructionDwgBlock(models.Model):
    _name = "construction.dwg.block"
    _description = "Bloc (insertion) d'un fichier DXF"
    _rec_name = "block_name"
    _order = "block_name"

    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Fichier DWG/DXF",
        required=True,
        ondelete="cascade",
        index=True,
    )

    block_name = fields.Char(string="Nom du bloc", required=True, index=True)
    layer = fields.Char(string="Calque")

    # --- Position ---
    pos_x = fields.Float(string="Position X", digits=(16, 4))
    pos_y = fields.Float(string="Position Y", digits=(16, 4))
    pos_z = fields.Float(string="Position Z", digits=(16, 4))

    # --- Rotation / échelle ---
    rotation = fields.Float(string="Rotation (°)", digits=(16, 4))
    scale_x = fields.Float(string="Échelle X", default=1.0, digits=(16, 4))
    scale_y = fields.Float(string="Échelle Y", default=1.0, digits=(16, 4))
    scale_z = fields.Float(string="Échelle Z", default=1.0, digits=(16, 4))

    # --- Référence / attributs ---
    handle = fields.Char(string="Référence (handle DXF)")
    attributes = fields.Text(
        string="Attributs",
        help="Stocké en JSON : {tag: valeur}",
    )
    
    # --- Nouveaux champs pour plus d'informations ---
    block_description = fields.Char(string="Description du bloc")
    insert_count = fields.Integer(string="Nombre d'insertions", default=0)

    # ---------------------------------------------------------
    # Extraction
    # ---------------------------------------------------------

    @api.model
    def extract_from_dwg_file(self, dwg_file):
        """Extrait TOUS les blocs et leurs attributs du fichier DXF"""
        if ezdxf is None:
            raise UserError(
                "La librairie 'ezdxf' n'est pas installée sur le serveur. "
                "Contactez votre administrateur système."
            )

        dwg_file.ensure_one()

        if not dwg_file.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour extraire les blocs.")

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

            block_vals = []
            block_definitions = {}
            block_insertions = {}
            
            # Log pour débogage
            _logger.info(f"=== ANALYSE DU FICHIER DXF: {dwg_file.filename} ===")
            _logger.info(f"Nombre total d'entités: {len(doc.entities)}")
            
            # Lister tous les calques disponibles
            layers = [layer.dxf.name for layer in doc.layers]
            _logger.info(f"Calques disponibles: {layers}")

            # ---------------------------------------------------------
            # 1. Analyser TOUTES les définitions de blocs
            # ---------------------------------------------------------
            _logger.info("--- Extraction des définitions de blocs ---")
            for block_entity in doc.blocks:
                block_name = block_entity.name
                if block_name in {'*Model_Space', '*Paper_Space', '*Paper_Space0'}:
                    continue
                
                entity_count = len(block_entity)
                block_definitions[block_name] = {
                    'entity_count': entity_count,
                    'entities': []
                }
                
                for entity in block_entity:
                    entity_info = {
                        'type': entity.dxftype(),
                        'layer': entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',
                    }
                    block_definitions[block_name]['entities'].append(entity_info)
                
                _logger.info(f"  - Bloc '{block_name}': {entity_count} entités")

            # ---------------------------------------------------------
            # 2. Analyser TOUTES les insertions de blocs
            # ---------------------------------------------------------
            _logger.info("--- Extraction des insertions de blocs ---")
            
            # Parcourir TOUTES les entités du document
            for entity in doc.entities:
                if entity.dxftype() == 'INSERT':
                    insert_point = entity.dxf.insert
                    block_name = entity.dxf.name
                    layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'
                    
                    # Récupérer les attributs
                    attribs = {}
                    try:
                        for attrib in entity.attribs:
                            tag = attrib.dxf.tag.strip()
                            value = attrib.dxf.text.strip()
                            attribs[tag] = value
                            _logger.debug(f"    Attribut: {tag} = {value}")
                    except (AttributeError, TypeError) as e:
                        _logger.debug(f"    Pas d'attributs pour le bloc {block_name}: {e}")
                    
                    # Récupérer les attributs de style (si présents)
                    try:
                        if hasattr(entity, 'attribs_follow'):
                            _logger.debug(f"    Attributs suivent: {entity.attribs_follow}")
                    except:
                        pass
                    
                    # Compter les insertions par nom de bloc
                    if block_name not in block_insertions:
                        block_insertions[block_name] = []
                    block_insertions[block_name].append({
                        'position': (insert_point.x, insert_point.y, insert_point.z),
                        'layer': layer,
                        'attributes': attribs,
                        'handle': entity.dxf.handle,
                        'rotation': entity.dxf.get("rotation", 0.0),
                        'scale': (entity.dxf.get("xscale", 1.0), 
                                 entity.dxf.get("yscale", 1.0), 
                                 entity.dxf.get("zscale", 1.0))
                    })
                    
                    # Créer l'enregistrement pour cette insertion
                    block_vals.append({
                        "dwg_file_id": dwg_file.id,
                        "block_name": block_name,
                        "layer": layer,
                        "pos_x": insert_point.x,
                        "pos_y": insert_point.y,
                        "pos_z": insert_point.z,
                        "rotation": entity.dxf.get("rotation", 0.0),
                        "scale_x": entity.dxf.get("xscale", 1.0),
                        "scale_y": entity.dxf.get("yscale", 1.0),
                        "scale_z": entity.dxf.get("zscale", 1.0),
                        "handle": entity.dxf.handle,
                        "attributes": json.dumps(attribs, ensure_ascii=False) if attribs else False,
                        "block_description": f"Insertion de {block_name} sur calque {layer}",
                        "insert_count": 1,
                    })
                    
                    # Log détaillé
                    _logger.info(f"  - INSERT {block_name} sur calque '{layer}' à ({insert_point.x:.2f}, {insert_point.y:.2f})")
                    if attribs:
                        _logger.info(f"      Attributs: {attribs}")

            # ---------------------------------------------------------
            # 3. Analyser les calques pour trouver des blocs non-INSERT
            #    (parfois les blocs sont sur des calques spécifiques)
            # ---------------------------------------------------------
            _logger.info("--- Recherche d'entités par calque ---")
            for layer_name in layers:
                if layer_name == '0' and len(layers) > 1:
                    continue
                try:
                    entities_on_layer = doc.modelspace().query(f'*[layer=="{layer_name}"]')
                    if entities_on_layer:
                        _logger.info(f"  - Calque '{layer_name}': {len(entities_on_layer)} entités")
                        for entity in entities_on_layer[:5]:  # Afficher les 5 premiers
                            _logger.info(f"      {entity.dxftype()} sur calque '{layer_name}'")
                except Exception as e:
                    _logger.debug(f"Erreur sur calque {layer_name}: {e}")

            # ---------------------------------------------------------
            # 4. Récupérer les attributs des blocs qui ont des valeurs comme "1,111"
            # ---------------------------------------------------------
            _logger.info("--- Recherche d'attributs spécifiques ---")
            for block_name, insertions in block_insertions.items():
                for insertion in insertions:
                    if insertion['attributes']:
                        for tag, value in insertion['attributes'].items():
                            if ',' in value or ';' in value or any(c.isdigit() for c in value):
                                _logger.info(f"  - Valeur trouvée: {tag} = {value} dans le bloc {block_name}")

            # ---------------------------------------------------------
            # 5. Résumé
            # ---------------------------------------------------------
            _logger.info("=== RÉSUMÉ DE L'EXTRACTION ===")
            _logger.info(f"Définitions de blocs: {len(block_definitions)}")
            for name, info in block_definitions.items():
                _logger.info(f"  - {name}: {info['entity_count']} entités")
            
            _logger.info(f"Insertions de blocs: {sum(len(v) for v in block_insertions.values())}")
            for name, insertions in block_insertions.items():
                _logger.info(f"  - {name}: {len(insertions)} insertions")
            
            if block_vals:
                _logger.info(f"Total enregistrements créés: {len(block_vals)}")
            else:
                _logger.warning("AUCUN BLOC TROUVÉ ! Vérifiez le fichier DXF.")

        # Supprime les blocs précédents
        existing = self.search([("dwg_file_id", "=", dwg_file.id)])
        if existing:
            _logger.info(f"Suppression de {len(existing)} blocs existants")
            existing.unlink()

        if not block_vals:
            _logger.warning(f"Aucun bloc trouvé dans le fichier {dwg_file.filename}")
            return self.browse()

        # Créer les enregistrements
        result = self.create(block_vals)
        _logger.info(f"✅ Création de {len(result)} enregistrements de blocs")
        return result

    # ---------------------------------------------------------
    # Méthodes utilitaires
    # ---------------------------------------------------------

    @api.model
    def get_block_counts(self, dwg_file_id):
        """Retourne les statistiques des blocs"""
        blocks = self.search([("dwg_file_id", "=", dwg_file_id)])
        counts = {}
        for block in blocks:
            counts[block.block_name] = counts.get(block.block_name, 0) + 1
        return counts

    @api.model
    def get_blocks_by_layer(self, dwg_file_id, layer_name):
        """Retourne tous les blocs sur un calque spécifique"""
        return self.search([
            ("dwg_file_id", "=", dwg_file_id),
            ("layer", "=", layer_name)
        ])

    @api.model
    def get_blocks_with_attributes(self, dwg_file_id):
        """Retourne les blocs qui ont des attributs"""
        return self.search([
            ("dwg_file_id", "=", dwg_file_id),
            ("attributes", "!=", False)
        ])