/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { GanttModel } from "@miro_gantt_view/model/model";
import { GanttRenderer } from "@miro_gantt_view/renderer/renderer";

/**
 * Deux réglages du Gantt pris dans le contexte de l'action, sans modifier le
 * module miro_gantt_view :
 *
 *   miro_gantt_initial_date (AAAA-MM-JJ) : date sur laquelle le Gantt s'ouvre,
 *       plutôt qu'aujourd'hui — le début du chantier ;
 *   miro_gantt_limit : nombre de barres chargées par page (81 par défaut),
 *       pour afficher toutes les phases d'un chantier d'un coup.
 */
patch(GanttRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        const initial = this.env.searchModel?.context?.miro_gantt_initial_date;
        if (initial) {
            const date = new Date(`${initial}T00:00:00`);
            if (!isNaN(date.getTime())) {
                this._focusDate = date;
            }
        }
    },
});

patch(GanttModel.prototype, {
    async load(searchParams) {
        const limit = searchParams?.context?.miro_gantt_limit;
        if (limit && searchParams.limit === undefined && !this._miroLimitApplied) {
            this.limit = limit;
            this._miroLimitApplied = true;
        }
        return super.load(...arguments);
    },
});
