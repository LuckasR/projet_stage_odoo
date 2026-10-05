/** @odoo-module **/
/**
 * Menu déroulant « Visualiser » de la fiche plan (construction.dwg.files).
 *
 * Remplace un bouton par visualiseur dans l'en-tête : les entrées viennent
 * du serveur (get_viewer_menu), chaque module y ajoute la sienne en Python,
 * sans retoucher la vue.
 */
import { Component, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class ConstructionViewerMenu extends Component {
    static template = "miro_construction_project.ViewerMenu";
    static components = { Dropdown, DropdownItem };
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ items: [], loaded: false });
    }

    /** Liste rechargée à chaque ouverture : elle suit l'état du plan
     *  (DXF converti, détections terminées...). */
    async beforeOpen() {
        const record = this.props.record;
        if (record.isDirty || record.isNew) {
            await record.save();
        }
        if (!record.resId) {
            this.state.items = [];
        } else {
            this.state.items = await this.orm.call(
                record.resModel, "get_viewer_menu", [record.resId]);
        }
        this.state.loaded = true;
    }

    async open(item) {
        const record = this.props.record;
        const action = await this.orm.call(
            record.resModel, "action_open_viewer", [record.resId, item.key]);
        await this.action.doAction(action);
    }
}

registry.category("view_widgets").add("construction_viewer_menu", {
    component: ConstructionViewerMenu,
});
