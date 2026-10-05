# models/point.py

from odoo import models, fields, api
import math


class Point3D(models.Model):
    _name = "construction.point"
    _description = "Point 3D"

    name = fields.Char(
        string="Nom",
        required=True
    )

    x = fields.Float(
        string="X",
        default=0.0,
        required=True
    )

    y = fields.Float(
        string="Y",
        default=0.0,
        required=True
    )

    z = fields.Float(
        string="Z",
        default=0.0,
        required=True
    )

    active = fields.Boolean(
        default=True
    )

    def to_tuple(self):
        """Retourne les coordonnées du point."""
        self.ensure_one()
        return (self.x, self.y, self.z)

    def distance_to(self, other):
        """Calcule la distance entre deux points."""
        self.ensure_one()

        return math.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        )

    def copy_point(self):
        """Crée une copie du point."""
        self.ensure_one()

        return self.copy({
            "name": f"{self.name} (Copie)"
        })

    def equals(self, other, tolerance=1e-6):
        """Compare deux points."""
        self.ensure_one()

        return (
            abs(self.x - other.x) < tolerance and
            abs(self.y - other.y) < tolerance and
            abs(self.z - other.z) < tolerance
        )

    @api.model
    def from_tuple(self, coords):
        """Crée un point à partir d'un tuple."""
        if len(coords) == 2:
            return self.create({
                "name": "Nouveau point",
                "x": coords[0],
                "y": coords[1],
                "z": 0.0,
            })

        elif len(coords) == 3:
            return self.create({
                "name": "Nouveau point",
                "x": coords[0],
                "y": coords[1],
                "z": coords[2],
            })

        raise ValueError("Le tuple doit contenir 2 ou 3 coordonnées.")

    def __repr__(self):
        return f"Point3D({self.x}, {self.y}, {self.z})"