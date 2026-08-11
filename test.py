import subprocess
from pathlib import Path

oda = "/home/luckas/Téléchargements/ODAFileConverter_QT6_lnxX64_8.3dll_27.1.AppImage"

input_dir = "/home/luckas/Documents/Stage/code/odoo17/input"
output_dir = "/home/luckas/Documents/Stage/code/odoo17/output"

command = [
    oda,
    input_dir,
    output_dir,
    "ACAD2018",
    "DXF",
    "0",          # pas de recherche récursive
    "1",          # audit
    "*.dwg"       # convertir uniquement les fichiers DWG
]

result = subprocess.run(command, capture_output=False, text=True)

print("Code retour :", result.returncode)
print("Sortie :", result.stdout)
print("Erreurs :", result.stderr)