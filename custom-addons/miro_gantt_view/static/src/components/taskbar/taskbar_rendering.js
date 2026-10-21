
/** @odoo-module **/
import { renderToElement } from "@web/core/utils/render";
import { renderDateColumns } from "@miro_gantt_view/utils/grid";
import { isDragTarget } from "@miro_gantt_view/utils/drag_and_drop";
import {
  buildGroupRowData,
  buildTaskRowData,
  attachTaskRowEvents,
} from "@miro_gantt_view/utils/row";
import {
  buildSidebarBodyData,
  attachSidebarGroupRowEvents,
} from "@miro_gantt_view/components/sidebar/sidebar";
import { ROW_HEIGHT } from "@miro_gantt_view/utils/config";

/**
 * Renders the left sidebar (row headers) via the Gantt.SidebarBody table
 * template (shared colgroup with the header sidebar). Interactive events
 * (collapse toggle, login-less avatar fallbacks) are attached after
 * rendering, per row.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element|null} The sidebar <table>, or null if no rows
 */
function renderRowHeaders(renderer) {
  if (!renderer._rowLayout.length) return null;
  const table = renderToElement(
    "miro_gantt_view.Gantt.SidebarBody",
    buildSidebarBodyData(renderer),
  );

  // Group rows: collapse/expand toggle + avatar fallback.
  for (const row of table.querySelectorAll("[data-group-path]")) {
    attachSidebarGroupRowEvents(renderer, row, row.dataset.groupPath);
  }
  return table;
}



/**
 * Renders the main Gantt grid area via QWeb templates.
 * Includes date background grid, group rows, and task bars (pills).
 * Events are attached after rendering via attachTaskRowEvents.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element} The Gantt columns wrapper
 */
function renderGanttColumns(renderer) {
  const wrapper = document.createElement("div");
  wrapper.className = "o_gantt_view_columns";
  wrapper.style.position = "relative";
  wrapper.style.overflow = "hidden";
  const dateGrid = renderDateColumns(renderer);
  if (dateGrid) wrapper.appendChild(dateGrid);
  let currentDepth0El = null;
  let currentChildEl = null;
  for (const item of renderer._rowLayout) {
    if (item.type === "group") {
      const depth = item.group.depth || 0;
      const data = buildGroupRowData(renderer, item, depth);
      const row = renderToElement("miro_gantt_view.Gantt.GroupRow", data);
      if (depth === 0) {
        currentChildEl = null;
        const groupWrapper = document.createElement("div");
        groupWrapper.className = "o_gantt_view_group_wrapper";
        groupWrapper.dataset.groupPath = String(item.group.path);
        if (isDragTarget(renderer._dragState, item.group.path))
          groupWrapper.classList.add("o_miro_drag_hover");
        groupWrapper.appendChild(row);
        wrapper.appendChild(groupWrapper);
        currentDepth0El = groupWrapper;
      } else {
        const childWrapper = document.createElement("div");
        childWrapper.className = "o_gantt_view_child_wrapper";
        childWrapper.dataset.groupPath = String(item.group.path);
        if (isDragTarget(renderer._dragState, item.group.path))
          childWrapper.classList.add("o_miro_drag_hover");
        childWrapper.appendChild(row);
        if (currentDepth0El) currentDepth0El.appendChild(childWrapper);
        else wrapper.appendChild(childWrapper);
        currentChildEl = childWrapper;
      }
    } else if (item.type === "band" && item.empty) {
      // Empty placeholder band (no data): same zebra styling and layout as a
      // real band row, but without a pill, so the empty grid cells stay
      // visible even when there is no task to display.
      const row = renderEmptyTaskRow(renderer);
      if (currentChildEl) currentChildEl.appendChild(row);
      else if (currentDepth0El) currentDepth0El.appendChild(row);
      else wrapper.appendChild(row);
    } else if (item.type === "band") {
      // Real band: one row containing every visible record of the leaf group,
      // stacked on vertical lanes. All pills share the row; the row carries the
      // record ids / lane count for drag targeting.
      const row = renderTaskBand(renderer, item);
      if (currentChildEl) currentChildEl.appendChild(row);
      else if (currentDepth0El) currentDepth0El.appendChild(row);
      else wrapper.appendChild(row);
    }
  }
  return wrapper;
}


/**
 * Renders an empty task row, displayed when there are no tasks to show.
 * Mirrors a real task row (same height/zebra/cursor) but without a pill so
 * the empty grid cells stay visible even when there is no data.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element} The empty task row element
 */
function renderEmptyTaskRow(renderer) {
  const row = document.createElement("div");
  row.className = "o_gantt_view_task_row o_gantt_view_empty_row";
  row.dataset.recordIds = "";
  row.dataset.bandLanes = "1";
  row.style.position = "relative";
  row.style.width = "100%";
  row.style.height = ROW_HEIGHT + "px";
  return row;
}



/**
 * Renders a band row: one row containing every visible record of the leaf
 * group, with each task pill on its OWN row (lane). The row carries the band
 * metadata needed by the drag-and-drop indicator:
 *   - data-record-ids: csv of the record ids (used to exclude the dragged
 *     record's own band from the insertion index)
 *   - data-band-lanes: number of lanes (used to clamp the target lane)
 *   - data-group-path: leaf group path of the band
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} item - The band layout item ({ records, lanes, height, group })
 * @returns {Element} The band row element
 */
function renderTaskBand(renderer, item) {
  const row = document.createElement("div");
  row.className = "o_gantt_view_task_row";
  row.dataset.recordIds = item.records.map((r) => r.id).join(",");
  row.dataset.bandLanes = String(item.lanes || 1);

  row.style.height = item.height + "px";
  row.style.containIntrinsicSize = "auto " + item.height + "px";


  if (item.group && item.group.path != null) {
    row.dataset.groupPath = String(item.group.path);
  }
  row.style.position = "relative";
  row.style.width = "100%";
  row.style.height = item.height + "px";
  for (const record of item.records) {
    const data = buildTaskRowData(renderer, record, {
      lane: item.laneMap && item.laneMap.get(record.id),
    });
    const wrapper = renderToElement(
      "miro_gantt_view.Gantt.TaskBandPill",
      data,
    );
    attachTaskRowEvents(renderer, wrapper, record);
    row.appendChild(wrapper);
  }
  return row;
}


export { renderRowHeaders, renderGanttColumns, renderEmptyTaskRow, renderTaskBand }
