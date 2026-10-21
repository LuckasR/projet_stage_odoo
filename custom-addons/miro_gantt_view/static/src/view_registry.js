/** @odoo-module **/
//  Reference: https://github.com/odoo/odoo/tree/17.0/addons/web/static/src/views/list/list_view.js

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { GanttRenderer } from "@miro_gantt_view/renderer/renderer";
import { GanttArchParser } from "@miro_gantt_view/arch_parser";
import { GanttController } from "@miro_gantt_view/controller/controller";
import { GanttModel } from "@miro_gantt_view/model/model";

// Reference to the Odoo view registry
const viewRegistry = registry.category("views");

/**
 * ganttView
 *
 * Miro Gantt view definition for Odoo's view registry.
 * Registers the "miro_gantt" view type so it can be used in window actions
 * alongside standard views (form, tree, kanban, etc.).
 *
 * Provides:
 *   - ArchParser: parses <miro_gantt> XML arch and extracts configuration
 *   - Model: loads records and builds the group tree
 *   - Renderer: renders the interactive Gantt chart
 *   - Controller: wires model, layout, search bar, and pager
 *
 * The props() function serves as the factory: it parses the arch XML on first
 * render (when no state exists) and constructs the modelParams object.
 * On subsequent renders, it reuses the stored metadata state.
 */
export const ganttView = {
  type: "miro_gantt",
  display_name: _t("miro Gantt"),
  icon: "fa fa-tasks",
  multiRecord: true,
  Controller: GanttController,
  Renderer: GanttRenderer,
  Model: GanttModel,
  ArchParser: GanttArchParser,
  searchMenuTypes: ["filter", "groupBy", "favorite"],

  /**
   * Builds the props object for the controller.
   * If state is available (from a previous render), reuses the stored metaData.
   * Otherwise, freshly parses the arch XML to extract view configuration.
   *
   * @param {Object} genericProps - Standard view props (arch, fields, resModel, state, etc.)
   * @param {Object} view - The view definition object
   * @returns {Object} Props object for the controller
   */
  props: (genericProps, view) => {
    let modelParams;
    if (genericProps.state) {
      // Reuse previously parsed metadata from saved state
      modelParams = genericProps.state.metaData;
    } else {
      // First render: parse the arch XML to extract configuration
      const { arch, fields, resModel } = genericProps;
      const parser = new view.ArchParser();
      const archInfo = parser.parse(arch, fields);

      let formViewId = archInfo.formViewId;
      if (!formViewId) {
        const formView = (genericProps.config?.views || []).find(
          (v) => v[1] === "form",
        );
        if (formView) {
          formViewId = formView[0];
        }
      }

      modelParams = {
        canCreate: archInfo.canCreate,
        canEdit: archInfo.canEdit,
        canDelete: archInfo.canDelete,
        createAction: archInfo.createAction || null,
        formViewId,
        dateStart: archInfo.dateStart,
        dateEnd: archInfo.dateEnd,
        coloredBy: archInfo.coloredBy,
        defaultTitle: archInfo.defaultTitle,
        sidebarLabelField: archInfo.sidebarLabelField,
        taskbarLabelField: archInfo.taskbarLabelField,
        defaultGroupBy: archInfo.defaultGroupBy,
        defaultFilter: archInfo.defaultFilter,
        availableFilters: archInfo.availableFilters,
        statusField: archInfo.statusField,
        progressField: archInfo.progressField,
        durationField: archInfo.durationField,
        overdueField: archInfo.overdueField,
        sidebarColumnFields: archInfo.sidebarColumnFields,
        sequence: archInfo.sequence,
        fields: fields,
        fieldNames: archInfo.fieldNames,
        ganttPopup: archInfo.ganttPopup,
        resModel: resModel,
        fieldReadonlyExpr: archInfo.fieldReadonlyExpr,
      };
    }

    return {
      ...genericProps,
      modelParams,
      Model: view.Model,
      Renderer: view.Renderer,
    };
  },
};

// Register the miro_gantt view type in Odoo's view registry
viewRegistry.add("miro_gantt", ganttView);
