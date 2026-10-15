/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const FILTERS = [
    { key: "all", label: "Tous" },
    { key: "to_order", label: "À commander" },
    { key: "shortage", label: "Stock insuffisant" },
    { key: "overrun", label: "Surconsommation" },
    { key: "no_product", label: "Produit à choisir" },
];

const GROUPS = [
    { key: "ouvrage", label: "Par ouvrage" },
    { key: "level", label: "Par niveau" },
    { key: "phase", label: "Par phase" },
];

/**
 * Tableau de bord des besoins en matériaux d'un projet : coût prévu,
 * avancement de l'approvisionnement (commandé / reçu / consommé), matériaux
 * en rupture ou en surconsommation, répartition par ouvrage, niveau, phase.
 * Toutes les données viennent d'un seul appel : project.project.get_material_dashboard.
 */
export class MaterialDashboard extends Component {
    static template = "miro_construction_bom.MaterialDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.filters = FILTERS;
        this.groupTabs = GROUPS;
        this.state = useState({
            loading: true,
            data: null,
            search: "",
            filter: "all",
            group: "ouvrage",
        });
        this.projectId = this.props.action.context.default_project_id
            || this.props.action.context.active_id;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "project.project", "get_material_dashboard", [[this.projectId]]);
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Données affichées
    // ------------------------------------------------------------------
    get kpis() {
        return this.state.data.kpis;
    }

    get rows() {
        const q = this.state.search.toLowerCase().trim();
        return this.state.data.materials.filter((r) => {
            if (q && !`${r.name} ${r.category}`.toLowerCase().includes(q)) return false;
            switch (this.state.filter) {
                case "to_order": return !r.no_product && r.ordered < r.planned - 1e-6;
                case "shortage": return r.shortage > 0;
                case "overrun": return r.gap > 0;
                case "no_product": return r.no_product;
                default: return true;
            }
        });
    }

    filterCount(key) {
        const all = this.state.data.materials;
        switch (key) {
            case "to_order": return all.filter((r) => !r.no_product && r.ordered < r.planned - 1e-6).length;
            case "shortage": return this.kpis.shortage;
            case "overrun": return this.kpis.overrun;
            case "no_product": return this.kpis.no_product;
            default: return all.length;
        }
    }

    get groupRows() {
        const rows = this.state.data.groups[this.state.group] || [];
        const max = Math.max(...rows.map((g) => g.planned_cost), 1);
        return rows.map((g) => ({
            ...g,
            width: (100 * g.planned_cost) / max,
            consumedWidth: g.planned_cost ? Math.min(100, (100 * g.consumed_cost) / g.planned_cost) : 0,
        }));
    }

    /** Barre d'approvisionnement : consommé, puis reçu, puis commandé, sur le prévu. */
    pipeline(row) {
        const base = Math.max(row.planned, row.consumed, row.ordered, 1e-9);
        const pct = (v) => Math.max(0, Math.min(100, (100 * v) / base));
        const consumed = pct(row.consumed);
        const received = Math.max(0, pct(row.received) - consumed);
        const ordered = Math.max(0, pct(row.ordered) - pct(Math.max(row.received, row.consumed)));
        return { consumed, received, ordered, plannedMark: pct(row.planned) };
    }

    rowStatus(row) {
        if (row.no_product) return { cls: "is-warn", label: "Produit à choisir" };
        if (row.gap > 0) return { cls: "is-bad", label: "Surconsommation" };
        if (row.consumed >= row.planned - 1e-6 && row.planned) return { cls: "is-ok", label: "Consommé" };
        if (row.shortage > 0) return { cls: "is-bad", label: "Stock insuffisant" };
        if (row.received >= row.planned - 1e-6 && row.planned) return { cls: "is-ok", label: "Reçu" };
        if (row.ordered > 0) return { cls: "is-info", label: "Commandé" };
        return { cls: "is-neutral", label: "À commander" };
    }

    // ------------------------------------------------------------------
    // Formats
    // ------------------------------------------------------------------
    qty(value) {
        return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(value || 0);
    }

    money(value) {
        const c = this.state.data.currency;
        const amount = new Intl.NumberFormat("fr-FR", {
            minimumFractionDigits: c.digits, maximumFractionDigits: c.digits,
        }).format(value || 0);
        return c.position === "before" ? `${c.symbol} ${amount}` : `${amount} ${c.symbol}`;
    }

    pct(value) {
        return `${Math.round(value || 0)} %`;
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------
    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    setFilter(key) {
        this.state.filter = key;
    }

    setGroup(key) {
        this.state.group = key;
    }

    openNeeds(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `${row.name} — besoins`,
            res_model: "construction.material.need",
            views: [[false, "list"], [false, "pivot"], [false, "form"]],
            domain: [["id", "in", row.need_ids]],
            target: "current",
        });
    }

    openProduct(row, ev) {
        ev.stopPropagation();
        if (!row.product_id) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: row.product_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAllNeeds() {
        const action = await this.orm.call(
            "project.project", "action_view_material_needs", [[this.projectId]]);
        this.action.doAction(action);
    }

    async refreshNeeds() {
        const action = await this.orm.call(
            "project.project", "action_refresh_material_needs", [[this.projectId]]);
        await this.load();
        if (action && action.params) {
            this.notification.add(action.params.message, { type: "success" });
        }
    }

    async printReport() {
        const action = await this.orm.call(
            "project.project", "action_print_material_report", [[this.projectId]]);
        this.action.doAction(action);
    }

    async purchase() {
        const action = await this.orm.call(
            "project.project", "action_create_material_purchases", [[this.projectId]]);
        this.action.doAction(action, { onClose: () => this.load() });
    }

    openProject() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            res_id: this.projectId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("miro_construction_bom.material_dashboard", MaterialDashboard);
