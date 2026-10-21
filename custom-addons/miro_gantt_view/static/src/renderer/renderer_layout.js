/** @odoo-module **/

/**
 * renderer_layout.js
 *
 * Layout computation for the Gantt renderer.
 * Extracted from GanttRenderer to keep the main renderer file focused.
 */

import {
  ROW_HEIGHT,
  EMPTY_ROW_COUNT,
  MAX_RENDERED_ROWS,
} from "@miro_gantt_view/utils/config";
import { computeRowLayout } from "@miro_gantt_view/utils/group_by";

/**
 * Computes the full row layout from scratch.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function computeFullLayout(renderer) {
  renderer._fullRowLayout = computeRowLayout(
    renderer.records,
    renderer.groups,
    renderer.dateRange,
    renderer.hasGroups,
    (key) => renderer.model.isGroupCollapsed(key),
    {
      rangeStart: renderer.dateRange.start,
      colUnit: renderer.zoomCfg.colUnit,
      laneStore: renderer.model._laneAssignments,
    },
  );
  if (renderer._fullRowLayout.length > MAX_RENDERED_ROWS) {
    renderer._fullRowLayout = renderer._fullRowLayout.slice(
      0,
      MAX_RENDERED_ROWS,
    );
  }
  if (
    renderer._fullRowLayout.length === 0 &&
    !renderer.model.loading &&
    !renderer.model.loadError
  ) {
    for (let i = 0; i < EMPTY_ROW_COUNT; i++) {
      renderer._fullRowLayout.push({
        type: "band",
        empty: true,
        records: [],
        lanes: 1,
        height: ROW_HEIGHT,
        group: null,
      });
    }
  }

  let bandRow = 0;
  for (const item of renderer._fullRowLayout) {
    item.rowIndex = item.type === "band" ? bandRow++ : -1;
  }
}

/**
 * Computes a lightweight signature of every input that can affect the
 * rendered DOM. Runs BEFORE the layout is computed; an unchanged signature
 * lets renderGantt skip both layout computation and DOM rebuild.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {string} The signature
 */
export function inputsSignature(renderer) {
  const { model, state } = renderer;
  const scrollEl = renderer.scrollArea?.el;
  const drag = renderer._dragState;
  const dragRecord = drag ? drag.record : null;
  // Sidebar columns to encode: the dynamic `sidebar_column_fields` when
  // declared, else the historical fixed columns.
  const declaredFields = model?.metaData?.sidebarColumnFields || [];
  const fieldDefs = model?.metaData?.sidebarColumnFieldDefs || [];
  const colKeys = declaredFields.length
    ? fieldDefs.map((def) => def.name)
    : ["start", "end", "duration", "status", "progress"];
  const parts = [
    state.zoom,
    state.sidebarVisible,
    state.sidebarWidth,
    "F" + colKeys.map((k) => (state.sidebarFields?.[k] ? "1" : "0")).join(""),
    state.sortOrder || "",
    renderer.dateRange.start.getTime(),
    renderer.totalColumns,
    renderer._focusDate.getTime(),
    model.revision,
    renderer._highlightRecordId ?? "",
    renderer._highlightLabel ?? "",
    model.loading ? "L" : "",
    model.loadError ? "E" : "",
    dragRecord ? dragRecord.id : "",
    dragRecord ? dragRecord.start.getTime() : "",
    dragRecord ? dragRecord.end.getTime() : "",
    drag ? drag.targetGroupKey : "",
    drag ? drag.mode : "",
    scrollEl ? scrollEl.clientWidth : "",
    scrollEl ? scrollEl.clientHeight : "",
  ];
  const collapsed = model.collapsedGroups;
  if (collapsed && collapsed.size) {
    parts.push("C", [...collapsed].sort().join(","));
  }
  return parts.join("|");
}
