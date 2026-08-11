import base64
import subprocess
import tempfile
import logging
from pathlib import Path

from odoo import api, models, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

_logger = logging.getLogger(__name__)

class ConstructionDwgFile(models.Model):
    _name = "construction.dwg.files"
    _description = "Gestion des fichiers DWG"
    _rec_name = "filename"
    

    ALLOWED_EXTENSIONS = ('.dwg', '.dxf')

    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        required=True,
        ondelete="cascade",
    )

    filename = fields.Char(string="Nom du fichier", required=True)
    file = fields.Binary(string="Fichier DWG/DXF", required=True, attachment=True)
    dxf_filename = fields.Char(string="Nom du fichier DXF", readonly=True)
    dxf_file = fields.Binary(string="Fichier DXF", attachment=True, readonly=True)
    metadata_id = fields.One2many(
        "construction.dwg.metadata",
        "dwg_file_id",
        string="Métadonnées DXF",
    )
    
    imported_at = fields.Datetime(
        string="Date d'import", default=fields.Datetime.now, readonly=True
    )
    
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("imported", "Importé"),
            ("analysed", "Analysé"),
            ("error", "Erreur"),
        ],
        default="draft",
    )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def _check_dwg_signature(self, file_bytes):
        """Vérifie que le fichier est bien un DWG valide via sa signature binaire."""
        if file_bytes[:2] != b'AC':
            raise ValidationError(
                "Le fichier ne semble pas être un fichier DWG valide (signature invalide)."
            )

    def _check_dxf_signature(self, file_bytes):
        """Vérifie sommairement qu'un fichier DXF a l'air valide (fichier texte ASCII)."""
        try:
            file_bytes[:50].decode('ascii')
        except UnicodeDecodeError:
            raise ValidationError(
                "Le fichier ne semble pas être un fichier DXF valide (contenu non-ASCII détecté)."
            )

    @api.constrains('filename', 'file')
    def _check_file_content(self):
        for record in self:
            if not record.filename or not record.file:
                continue
            ext = Path(record.filename).suffix.lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError(
                    f"Extension non autorisée : '{ext}'. "
                    f"Formats acceptés : {', '.join(self.ALLOWED_EXTENSIONS)}"
                )
            file_bytes = base64.b64decode(record.file)
            if ext == '.dwg':
                record._check_dwg_signature(file_bytes)
            elif ext == '.dxf':
                record._check_dxf_signature(file_bytes)

    # ---------------------------------------------------------
    # Traitement du fichier (conversion ou copie directe)
    # ---------------------------------------------------------
    
    
    def action_process_file(self):
        """Point d'entrée : convertit si DWG, copie directement si DXF."""
        for record in self:
            try:
                ext = Path(record.filename).suffix.lower()
                if ext == '.dwg':
                    record._convert_dwg_to_dxf()
                elif ext == '.dxf':
                    record._store_dxf_directly()
                else:
                    raise UserError(f"Extension non gérée : {ext}")
                record.state = "imported"
                record._extract_dxf_metadata()
            except Exception as e:
                record.state = "error"
                _logger.exception("Erreur de traitement pour %s", record.filename)
                raise UserError(f"Erreur lors du traitement : {e}")

    def _extract_dxf_metadata(self):
            """Extrait les métadonnées du DXF généré et les stocke."""
            self.ensure_one()
            try:
                self.env['construction.dwg.metadata'].extract_from_dwg_file(self)
                self.state = "analysed"
            except UserError as e:
                _logger.warning("Extraction de métadonnées échouée pour %s : %s", self.filename, e)
                # On ne bloque pas l'import si l'extraction échoue, le state reste 'imported'
                
            
    def _store_dxf_directly(self):
        """Cas où le fichier importé est déjà un DXF : pas de conversion nécessaire."""
        self.ensure_one()
        self.dxf_filename = self.filename
        self.dxf_file = self.file  # déjà en base64, on copie tel quel

    def _convert_dwg_to_dxf(self):
        """Cas où le fichier importé est un DWG : conversion via ODA File Converter."""
        self.ensure_one()
        oda_path = self.env['ir.config_parameter'].sudo().get_param(
            'construction_dwg.oda_path',
            default='/opt/oda/ODAFileConverter.AppImage'
        )

        if not oda_path or not Path(oda_path).exists():
            raise UserError(
                "Le chemin vers ODA File Converter n'est pas configuré ou est invalide. "
                "Vérifiez le paramètre système 'construction_dwg.oda_path'."
            )

        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            input_dir.mkdir()
            output_dir.mkdir()

            dwg_path = input_dir / self.filename
            dwg_path.write_bytes(base64.b64decode(self.file))

            command = [
                oda_path,
                str(input_dir),
                str(output_dir),
                "ACAD2018",
                "DXF",
                "0",   # pas de recherche récursive
                "1",   # audit
                "*.dwg",
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                raise UserError(
                    f"ODA Converter a échoué (code {result.returncode}) : {result.stderr}"
                )

            dxf_files = list(output_dir.glob("*.dxf"))
            if not dxf_files:
                raise UserError("Aucun fichier DXF n'a été généré.")

            dxf_path = dxf_files[0]
            self.dxf_filename = dxf_path.name
            self.dxf_file = base64.b64encode(dxf_path.read_bytes())

            
    def action_visualize(self):
        self.ensure_one()

        if not self.dxf_file:
            raise UserError(
                "Aucun fichier DXF disponible pour ce document. "
                "Vérifiez que le fichier a bien été traité."
            )
        
        construction_frontend_url = config.get(
            'construction_frontend_url' 
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"{construction_frontend_url}/viewer/{self.id}",
            "target": "new",
        }
        

    # ---------------------------------------------------------
    # Création
    # ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.action_process_file()
        return records
    
    