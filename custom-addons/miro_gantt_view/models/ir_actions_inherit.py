# -*- coding: utf-8 -*-
# Reference: https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/ir_actions.py

from odoo import fields, models

class ActWindowViewInherit(models.Model):
    """
    ActWindowViewInherit - Extension of ir.actions.act_window.view
    ==============================================================

    This class extends the standard Odoo model 'ir.actions.act_window.view'
    to add support for the custom "miro_gantt" view type.

    Key Features:
    ------------
    - Adds "miro_gantt" as a new available selection option in the view_mode field.
    - Configures cascade deletion behavior: when a miro_gantt view is removed,
      associated action window references are automatically deleted.

    This allows Odoo window actions to reference miro_gantt views alongside
    standard Odoo view types (form, tree, kanban, graph, etc.).
    """
    _inherit = "ir.actions.act_window.view"

    # Extend the view_mode selection field to include the new miro_gantt type
    view_mode = fields.Selection(
        selection_add=[
            ("miro_gantt", "Miro Gantt"),
        ],
        ondelete={"miro_gantt": "cascade"},
    )
