/** @odoo-module **/
import { renderToElement } from "@web/core/utils/render";
import { DAY_NAMES } from "@miro_gantt_view/utils/config";

/**
 * Computes column data for both the header cells and the date grid background.
 * Returns an array of { text, isToday, isDayOff } for each visible column.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object[]} Column data array
 */
export function buildColumnData(renderer) {
  const { start } = renderer.dateRange;
  const total = renderer.totalColumns;
  const zoom = renderer.state.zoom;
  const colUnit = renderer.zoomCfg.colUnit;
  const today = new Date();
  const todayStr = today.toDateString();
  const base = new Date(start);
  const columns = [];
  for (let i = 0; i < total; i++) {
    let d;
    if (zoom === "day") d = new Date(+base + i * 3600000);
    else if (colUnit === "year") {
      d = new Date(base);
      d.setFullYear(base.getFullYear() + i);
    } else if (colUnit === "month") {
      d = new Date(base);
      d.setMonth(base.getMonth() + i);
    } else if (zoom === "week" || zoom === "month" || zoom === "year") {
      d = new Date(base);
      d.setDate(base.getDate() + i);
    } else {
      d = new Date(base);
      d.setDate(base.getDate() + i);
    }
    let text;
    if (colUnit === "year") {
      text = String(d.getFullYear());
    } else if (colUnit === "month") {
      text = d.toLocaleDateString(undefined, { month: "short" });
    } else if (zoom === "day") text = String(i).padStart(2, "0");
    else if (zoom === "week")
      text = `${DAY_NAMES[d.getDay() === 0 ? 6 : d.getDay() - 1]} ${String(d.getDate()).padStart(2, "0")}`;
    else if (zoom === "month" || zoom === "year") text = String(d.getDate()).padStart(2, "0");
    else text = String(d.getDate());
    let isToday;
    if (colUnit === "year")
      isToday = d.getFullYear() === today.getFullYear();
    else if (colUnit === "month")
      isToday =
        d.getFullYear() === today.getFullYear() &&
        d.getMonth() === today.getMonth();
    else if (zoom === "day")
      isToday =
        d.toDateString() === todayStr && d.getHours() === today.getHours();
    else isToday = d.toDateString() === todayStr;
    const isDayOff =
      colUnit !== "month" &&
      colUnit !== "year" &&
      (zoom === "week" || zoom === "month" || zoom === "year") &&
      (d.getDay() === 6 || d.getDay() === 0);
    columns.push({ text, isToday, isDayOff });
  }
  return columns;
}

/**
 * Renders the background date grid via the GanttDateGrid template.
 * One cell per visible time column, used behind group rows and task bars.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element} The date grid container
 */
export function renderDateColumns(renderer) {
  return renderToElement(
    "miro_gantt_view.Gantt.DateGrid",
    buildDateGridData(renderer),
  );
}

/**
 * Builds the data object for the GanttDateGrid template.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object} Date grid template data
 */
function buildDateGridData(renderer) {
  return {
    totalColumns: renderer.totalColumns,
    columns: buildColumnData(renderer),
  };
}
