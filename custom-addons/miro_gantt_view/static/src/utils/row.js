/** @odoo-module **/
import {
  getDateGridBounds,
  getRawDateColIndex,
} from "@miro_gantt_view/utils/position_compute";
import {
  BAR_HEIGHT,
  LANE_PADDING,
  LANE_PITCH,
  GROUP_HEADER_HEIGHT,
  COLOR_PALETTE,
  getColorIndex,
} from "@miro_gantt_view/utils/config";

/**
 * Estimates the pixel width of a piece of text rendered at a given font size.
 * Uses the canvas measureText API when available (browser); falls back to a
 * rough per-character estimate otherwise (tests / headless).
 * @param {string} text - The text to measure
 * @param {number} [fontSize=12] - The font size in pixels
 * @returns {number} The estimated width in pixels
 */
let _measureCtx = null;
function estimateTextWidth(text, fontSize = 12) {
  if (!text) return 0;
  if (typeof document !== "undefined" && document.createElement) {
    if (!_measureCtx) _measureCtx = document.createElement("canvas").getContext("2d");
    _measureCtx.font = `${fontSize}px sans-serif`;
    return _measureCtx.measureText(String(text)).width;
  }
  return String(text).length * fontSize * 0.55;
}

/**
 * Builds the data object for the GanttTaskBandPill template.
 * Calculates pill position, size, lane offset, and visibility flags from the
 * record's date range. The pill is stacked inside its band row at the record's
 * lane (`record._laneIndex`), assigned by the band layout (group_by.js).
 * When the pill is too narrow to fit its label, the label is moved to the right
 * of the taskbar (`labelOutside`). `outOfRange` is true when the record lies
 * entirely outside the visible date range (before start or after end).
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The task record
 * @param {Object} [opts] - Options (e.g. lane override)
 * @returns {Object} Task pill template data including outOfRange, labelOutside
 */
export function buildTaskRowData(renderer, record, opts = {}) {
  const { colStart, colSpan, outOfRange } = getDateGridBounds(
    record,
    renderer.totalColumns,
    renderer.dateRange.start,
    renderer.zoomCfg.colUnit,
  );
  const colPct = renderer._columnWidthPct;
  let pillLeftPct = (colStart - 1) * colPct;
  if (pillLeftPct < 0.1) pillLeftPct = 0.1;
  let pillWidthPct = colSpan * colPct;
  if (pillLeftPct + pillWidthPct > 100) pillWidthPct = 100 - pillLeftPct;
  // A resize handle is only rendered when the edge it resizes is actually
  // visible inside the current grid. A bar clamped on the right (end date beyond
  // the last column) or clipped on the left (start date before the range) hides
  // the corresponding handle.
  const rawStart = getRawDateColIndex(
    record.start,
    renderer.dateRange.start,
    renderer.zoomCfg.colUnit,
  );
  const rawEnd = getRawDateColIndex(
    record.end,
    renderer.dateRange.start,
    renderer.zoomCfg.colUnit,
  );
  const startEdgeVisible = rawStart >= 0 && rawStart < renderer.totalColumns;
  const endEdgeVisible = rawEnd >= 0 && rawEnd < renderer.totalColumns;
  // Stack the pill on its lane inside the band row. The lane pitch includes a
  // fixed gap so bars on adjacent lanes never touch (LANE_GAP = 6px).
  // `opts.lane` (from the band's laneMap) takes precedence so records shared
  // by several bands (M2M groups) keep their per-band lane.
  const lane = opts.lane != null ? opts.lane : record._laneIndex || 0;
  const topOffset = LANE_PADDING + lane * LANE_PITCH;
  const isDragging = Boolean(
    renderer._dragState?.record?.id != null &&
    renderer._dragState.record.id === record.id
  );
  const highlighted =
    typeof renderer._isRecordHighlighted === "function" &&
    renderer._isRecordHighlighted(record.id);
  const colorIndex = getColorIndex(record.color);
  const isDirectHex = record.color && !COLOR_PALETTE.includes(record.color);
  const showStatus = Boolean(record.status);
  let labelOutside = false;
  const labelText = record.pillLabel || record.name || "";
  if (labelText && !outOfRange) {
    const pillPx = Math.max(0, colSpan * renderer._clientColWidth);
    const occupiedPx =
      estimateTextWidth(labelText) + (showStatus ? 44 : 0) + 18;
    labelOutside = occupiedPx > pillPx;
  }
  // The warning icon follows the label: when the label is rendered outside the
  // pill, the icon is rendered outside too; when the label is inside, the
  // inline icon (::after) is used. The o_gantt_view_pill_overdue_outside class
  // hides the inline icon so the two are never displayed together.
  const overdueFlag = Boolean(record.isOverdue);
  const outsideWarning = overdueFlag && labelOutside;
  return {
    recordId: record.id,
    colorClass: isDirectHex ? '' : 'o_gantt_view_color_' + colorIndex,
    colorStyle: isDirectHex ? 'background-color: ' + record.color + ';' : '',
    name: record.pillLabel || record.name || "",
    overdue: overdueFlag,
    outsideWarning: outsideWarning,
    labelOutside: labelOutside,
    outOfRange: Boolean(outOfRange),
    pillLeftPct: pillLeftPct,
    pillWidthPct: pillWidthPct,
    topOffset: topOffset,
    barHeight: BAR_HEIGHT,
    hasResizeRight:
      !renderer._isFieldReadonlyForRecord(
        renderer.model.metaData.dateEnd,
        record,
      ) && endEdgeVisible,
    hasResizeLeft:
      !renderer._isFieldReadonlyForRecord(
        renderer.model.metaData.dateStart,
        record,
      ) && startEdgeVisible,
    highlighted: highlighted,
    isDragging: isDragging,
  };
}

/**
 * Attaches drag, click, and resize events to a rendered task pill wrapper.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Element} wrapperEl - The pill wrapper element (GanttTaskBandPill root)
 * @param {Object} record - The task record
 */
export function attachTaskRowEvents(renderer, wrapperEl, record) {
  const pill = wrapperEl.querySelector(".o_gantt_view_pill_interactive");
  if (!pill) return;

  pill.addEventListener("mousedown", (ev) => {
    renderer._startDrag(ev, record, "move");
  });
  pill.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (renderer._justDragged) return;
    renderer._onBarClick(ev, record);
  });
  const resizeRight = pill.querySelector(".o_gantt_view_resize_handle");
  if (resizeRight)
    resizeRight.addEventListener("mousedown", (ev) => {
      renderer._startDrag(ev, record, "resize");
    });
  const resizeLeft = pill.querySelector(".o_gantt_view_resize_handle_left");
  if (resizeLeft)
    resizeLeft.addEventListener("mousedown", (ev) => {
      renderer._startDrag(ev, record, "resize-start");
    });
}

/**
 * Builds the data object for the GanttGroupRow template.
 * Also computes the position of the thin "overview" task bar that spans from
 * the group's earliest start date to its latest end date (min start → max end).
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} item - Layout item of type "group" (carries groupStart/groupEnd)
 * @param {number} depth - Nesting depth
 * @returns {Object} Group row template data
 */
export function buildGroupRowData(renderer, item, depth = 0) {
  const group = item.group;
  const groupBar = { leftPct: 0, widthPct: 0, show: false };
  if (depth === 0 && item.groupStart && item.groupEnd) {
    const { colStart, colSpan } = getDateGridBounds(
      { start: item.groupStart, end: item.groupEnd },
      renderer.totalColumns,
      renderer.dateRange.start,
      renderer.zoomCfg.colUnit,
    );
    const colPct = renderer._columnWidthPct;
    let leftPct = (colStart - 1) * colPct;
    let widthPct = colSpan * colPct;
    if (leftPct < 0.1) leftPct = 0.1;
    if (leftPct + widthPct > 100) widthPct = 100 - leftPct;
    groupBar.leftPct = leftPct;
    groupBar.widthPct = widthPct;
    groupBar.show = widthPct > 0;
  }
  return {
    groupPath: String(group.path),
    groupKey: String(group.key),
    depth,
    height: GROUP_HEADER_HEIGHT,
    barLeftPct: groupBar.leftPct,
    barWidthPct: groupBar.widthPct,
    barShow: groupBar.show,
  };
}
