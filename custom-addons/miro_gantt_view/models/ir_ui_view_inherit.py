# -*- coding: utf-8 -*-
# Reference: https://github.com/odoo/odoo/blob/17.0/odoo/addons/base/models/ir_ui_view.py

from odoo import fields, models

class IrUIViewInherit(models.Model):
    """
    IrUIViewInherit - Extension of ir.ui.view
    ==========================================
    This class extends the standard Odoo model 'ir.ui.view' to add support
    for the custom "miro_gantt" view type in the view type selection field.
    Key Features:
    ------------
    - Adds "miro_gantt" as an allowed value in the 'type' selection field.
    - Overrides '_is_qweb_based_view' to ensure that the miro_gantt view type
      is recognized as a QWeb-based view (required for proper template rendering).

    This makes Odoo aware that miro_gantt is a valid view type that can be
    created, loaded, and rendered through Odoo's view mechanism.
    """
    _inherit = "ir.ui.view"

    # Add miro_gantt as an allowed view type in the selection field
    type = fields.Selection(
        selection_add=[("miro_gantt", "Gantt")],
        ondelete={"miro_gantt": "cascade"}
        )

    def _is_qweb_based_view(self, view_type):
        """
        Determines if a given view type is based on the QWeb rendering engine.
        This override tells Odoo that the miro_gantt custom view type should
        be treated as a QWeb-based view, which enables proper template loading
        and rendering through Odoo's view infrastructure.
        Args:
            view_type (str): The view type string to check (e.g., "form", "tree", "miro_gantt").

        Returns:
            bool: True if the view type is QWeb-based, False otherwise.
        """
        # Validate that view_type is indeed a string before proceeding
        if not isinstance(view_type, str):
            return super()._is_qweb_based_view(view_type)

        # Return True if the standard check passes OR if the type is miro_gantt
        return (
            super()._is_qweb_based_view(view_type)
            or view_type == "miro_gantt"
        )

    def _postprocess_access_rights(self, tree):
        """
       Override of '_postprocess_access_rights' to restrict Gantt view actions
        (create, edit, delete) based on groups.
        -----------------------------------------------
        Allows the declaration of optional attributes—'create_groups',
        'edit_groups', and 'delete_groups'—on the <miro_gantt> root element.
        These attributes contain a comma-separated list of group XML IDs
        (using OR logic). If the current user is not a member of any of
        these groups, the corresponding action is disabled on the client
        side (the 'create', 'edit', or 'delete' attribute is set to "0"),
        which hides the create button, makes the form read-only, and
        disables deletion.
        Since the manager role inherits from the user group, it remains
        fully enabled.
        """
        tree = super()._postprocess_access_rights(tree)
        for node in tree.xpath("//miro_gantt[@create_groups or @edit_groups or @delete_groups]"):
            for action, attr in (
                ("create", "create_groups"),
                ("edit", "edit_groups"),
                ("delete", "delete_groups"),
            ):
                groups = node.get(attr)
                if groups and not self.user_has_groups(groups):
                    node.set(action, "0")
        return tree
