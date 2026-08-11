# models/line.py

from odoo import models, fields, api
import math


class ConstructionLine(models.Model):
    _name = "construction.line"
    _description = "Ligne 3D"

    name = fields.Char(
        string="Nom",
        required=True
    )

    start_id = fields.Many2one(
        "construction.point",
        string="Point de début",
        required=True,
        ondelete="cascade"
    )

    end_id = fields.Many2one(
        "construction.point",
        string="Point de fin",
        required=True,
        ondelete="cascade"
    )

    length = fields.Float(
        string="Longueur",
        compute="_compute_length",
        store=True
    )

    direction_x = fields.Float(
        string="Vecteur X",
        compute="_compute_direction",
        store=True
    )

    direction_y = fields.Float(
        string="Vecteur Y",
        compute="_compute_direction",
        store=True
    )

    direction_z = fields.Float(
        string="Vecteur Z",
        compute="_compute_direction",
        store=True
    )

    @api.depends(
        "start_id.x", "start_id.y", "start_id.z",
        "end_id.x", "end_id.y", "end_id.z"
    )
    def _compute_length(self):
        for line in self:
            dx = line.end_id.x - line.start_id.x
            dy = line.end_id.y - line.start_id.y
            dz = line.end_id.z - line.start_id.z

            line.length = math.sqrt(
                dx ** 2 +
                dy ** 2 +
                dz ** 2
            )

    @api.depends(
        "start_id.x", "start_id.y", "start_id.z",
        "end_id.x", "end_id.y", "end_id.z"
    )
    def _compute_direction(self):
        for line in self:
            line.direction_x = line.end_id.x - line.start_id.x
            line.direction_y = line.end_id.y - line.start_id.y
            line.direction_z = line.end_id.z - line.start_id.z

    def direction_vector(self):
        self.ensure_one()
        return (
            self.direction_x,
            self.direction_y,
            self.direction_z,
        )

    def is_parallel(self, other):
        self.ensure_one()

        dx1 = self.direction_x
        dy1 = self.direction_y

        dx2 = other.direction_x
        dy2 = other.direction_y

        return math.isclose(
            dx1 * dy2,
            dy1 * dx2,
            abs_tol=1e-6
        )

    def is_parallel3D(self, other):
        self.ensure_one()

        dx1 = self.direction_x
        dy1 = self.direction_y
        dz1 = self.direction_z

        dx2 = other.direction_x
        dy2 = other.direction_y
        dz2 = other.direction_z

        return (
            math.isclose(dx1 * dy2, dy1 * dx2, abs_tol=1e-6)
            and
            math.isclose(dx1 * dz2, dz1 * dx2, abs_tol=1e-6)
            and
            math.isclose(dy1 * dz2, dz1 * dy2, abs_tol=1e-6)
        )

    def have_same_length(self, other):
        self.ensure_one()

        return math.isclose(
            self.length,
            other.length,
            abs_tol=1e-6
        )

    def are_connected(self, other):
        self.ensure_one()

        return (
            self.start_id == other.start_id
            or self.start_id == other.end_id
            or self.end_id == other.start_id
            or self.end_id == other.end_id
        )

    def to_dict(self):
        self.ensure_one()

        return {
            "start": (
                self.start_id.x,
                self.start_id.y,
                self.start_id.z,
            ),
            "end": (
                self.end_id.x,
                self.end_id.y,
                self.end_id.z,
            ),
            "length": self.length,
        }