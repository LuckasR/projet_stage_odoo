/** @odoo-module **/
import { renderToElement } from "@web/core/utils/render";
import { formatDate, formatDateTime } from "@web/core/l10n/dates";
import { isDragTarget } from "@miro_gantt_view/utils/drag_and_drop";
import {
  buildHeaderData,
  attachHeaderEvents,
} from "@miro_gantt_view/components/header/header";
import {
  ROW_HEIGHT,
  NAME_PANEL_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_COL_WIDTHS,
  buildSidebarCols,
  sidebarColsCss,
  GROUP_HEADER_HEIGHT,
  BAR_HEIGHT,
  LANE_PADDING,
  LANE_PITCH,
  createAvatarFallback,
  getInitials,
  getAvatarColor,
} from "@miro_gantt_view/utils/config";

// Luxon is exposed globally by the web bundle (same usage as @web/core/l10n/dates).
const { DateTime } = luxon;

/**
 * Renders the sidebar area of the header (sticky left, aligned with column headers).
 * Contains the title and sort icon.
 * Placed in grid-column: 1 of the body grid, alongside the column header (grid-column: 2).
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element} The sidebar header element
 */
export function renderHeaderSidebar(renderer) {
  const el = renderToElement(
    "gantt_view.HeaderSidebar",
    buildHeaderData(renderer),
  );
  attachHeaderEvents(renderer, el);
  return el;
}

/**
 * Handles the start of sidebar resize via mouse drag.
 * Attaches mousemove and mouseup event listeners to the document.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mousedown event
 */
export function _startSidebarResize(renderer, ev) {
  ev.preventDefault();
  const startX = ev.clientX;
  const startWidth = renderer.state.sidebarWidth || NAME_PANEL_WIDTH;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  const minWidth = 100;
  const maxWidth = SIDEBAR_MAX_WIDTH;

  /**
   * Drag handler: updates sidebar width and re-renders (throttled via RAF).
   * @param {MouseEvent} e - The mousemove event
   */
  let _sidebarResizeRAF = null;
  function _onMouseMove(e) {
    const newWidth = Math.max(
      minWidth,
      Math.min(maxWidth, startWidth + (e.clientX - startX)),
    );
    renderer.state.sidebarWidth = newWidth;
    renderer._manualSidebarWidth = newWidth;
    if (!_sidebarResizeRAF) {
      _sidebarResizeRAF = requestAnimationFrame(() => {
        _sidebarResizeRAF = null;
        renderer.renderGantt();
      });
    }
  }

  /** Cleans up after drag ends. */
  function _onMouseUp() {
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    document.removeEventListener("mousemove", _onMouseMove);
    document.removeEventListener("mouseup", _onMouseUp);
  }

  document.addEventListener("mousemove", _onMouseMove);
  document.addEventListener("mouseup", _onMouseUp);
}

/**
 * Formats a start date for the sidebar "Start date" column.
 * Displays dd/MM/yyyy, appending HH:mm when the source value carries a time
 * component. Returns an empty string for null/unset dates (epoch).
 *
 * @param {Date|null|undefined} date - The start date to format
 * @param {boolean} [hasTime=false] - Whether to include the time component
 * @returns {string} The formatted date string
 */
function formatStartDate(date, hasTime = false) {
  if (!date || date.getTime() === 0) return "";
  const d = DateTime.fromJSDate(date);
  return hasTime ? formatDateTime(d) : formatDate(d);
}

/**
 * Formats a numeric duration for the sidebar "Duration" column.
 * Renders the value with two decimal places (e.g. "12.50"). Returns an empty
 * string for null/undefined/non-numeric values.
 *
 * @param {number|null|undefined} val - The duration value
 * @returns {string} The formatted duration string
 */
function formatDuration(val) {
  if (val == null || typeof val !== "number" || !isFinite(val)) return "";
  return val.toFixed(2);
}

/**
 * Formats a numeric progress value (progress_field, in percent).
 * Trims trailing zeros: 12.50 -> "12.5%", 70.00 -> "70%". Returns an empty
 * string for null/undefined/non-numeric values.
 *
 * @param {number|null|undefined} val - The progress value (0-100)
 * @returns {string} The formatted progress string
 */
function formatProgress(val) {
  if (val == null || !isFinite(Number(val))) return "";
  return `${Number(val)
    .toFixed(2)
    .replace(/\.?0+$/, "")}%`;
}

/**
 * Formats a raw field value for a dynamic sidebar column, depending on its
 * field type (date, datetime, boolean, selection, many2one...).
 * @param {*} val - The raw value (as returned by the ORM)
 * @param {Object} fieldDef - The field definition { name, label, type, selection }
 * @returns {string} The display text
 */
function formatFieldValue(val, fieldDef) {
  if (val === null || val === undefined || val === false || val === "")
    return "";
  const type = (fieldDef && fieldDef.type) || "char";
  if (type === "date") {
    const d = DateTime.fromISO(val);
    return d.isValid ? formatDate(d) : "";
  }
  if (type === "datetime") {
    // Odoo returns datetimes as "YYYY-MM-DD HH:mm:ss"; luxon's fromISO
    // requires the ISO "T" separator.
    const d = DateTime.fromISO(String(val).trim().replace(" ", "T"));
    return d.isValid ? formatDateTime(d) : "";
  }
  if (type === "boolean") return val ? "✓" : "";
  if (type === "selection") {
    const selection = fieldDef.selection;
    if (Array.isArray(selection)) {
      const match = selection.find(([v]) => String(v) === String(val));
      if (match) return match[1];
    }
    return String(val);
  }
  if (type === "many2one") return Array.isArray(val) ? val[1] : String(val);
  if (type === "float" || type === "monetary") {
    // 2 décimales par défaut, ou le scale déclaré sur le champ
    // (fields[fname].digits = [precision, scale]).
    const rawScale = fieldDef?.digits?.[1];
    const digits = Number.isFinite(Number(rawScale)) ? Number(rawScale) : 2;
    const num = Number(val);
    return isFinite(num) ? num.toFixed(digits) : "";
  }
  if (type === "integer") return String(val);
  if (type === "many2many") {
    // Names are resolved by resolveM2MNames into { id, name } objects;
    // a plain array of IDs (unresolved) falls back to a raw list.
    return Array.isArray(val)
      ? val
          .map((item) =>
            item && typeof item === "object" ? item.name : String(item),
          )
          .join(", ")
      : String(val);
  }
  return String(val);
}

/**
 * Attaches collapse/expand and avatar fallback to a rendered group row.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Element} rowEl - The rendered sidebar group row element
 * @param {string} groupPath - The group path for toggle
 */
export function attachSidebarGroupRowEvents(renderer, rowEl, groupPath) {
  const toggle = rowEl.querySelector(".o_gantt_view_group_toggle");
  if (toggle) {
    toggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      renderer.model.toggleGroup(groupPath);
      renderer.renderGantt();
    });
  }
  const avatarImg = rowEl.querySelector(".o_gantt_view_group_avatar");
  if (avatarImg) {
    avatarImg.onerror = function () {
      const fallback = createAvatarFallback(rowEl.title || "");
      this.replaceWith(fallback);
    };
  }
}

/**
 * Builds the data object for the GanttSidebarRecordRow template.
 * The layout item is a band (one cell per leaf group, its taskbars stacked on
 * their own rows). The sidebar cell keeps the band's height and renders ONE
 * sub-row per taskbar, aligned with the taskbar's lane in the gantt grid. Each
 * sub-row shows the task name, start date and duration; the progress is
 * rendered as the sub-row background.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} item - Band layout item with record data
 * @returns {Object} Sidebar record row template data
 */
export function buildSidebarRecordRowData(renderer, item, colsCss) {
  const records = item.records && item.records.length ? item.records : [];
  const bandHeight = item.height || ROW_HEIGHT;
  const primary = records[0] || null;
  const dragging = renderer._dragState?.record;
  const isDragging = dragging
    ? records.some((r) => r.id === dragging.id)
    : false;
  let rowStyle =
    "height: " +
    bandHeight +
    "px; grid-template-columns: " +
    (colsCss || "") +
    ";";
  if (isDragging) rowStyle += " opacity: 0.5;";

  // One entry per lane (taskbar), aligned with the pill's lane in the gantt:
  // the name cell + one value per info column, all at the same top offset.
  // Every lane keeps the pill height (BAR_HEIGHT) so the labels stay
  // perfectly centered on their taskbar; the group-closing border is drawn
  // by the band row itself, not by the last lane.
  // Info-column lane keys: the dynamic `sidebar_column_fields` when declared
  // in the arch, else the historical fixed columns (SIDEBAR_COL_WIDTHS).
  const declaredFields =
    renderer?.model?.metaData?.sidebarColumnFields || [];
  const fieldDefs =
    renderer?.model?.metaData?.sidebarColumnFieldDefs || [];
  const lanes = { name: [] };
  const useDynamic = Boolean(declaredFields.length);
  const colKeys = useDynamic
    ? fieldDefs.map((def) => def.name)
    : Object.keys(SIDEBAR_COL_WIDTHS);
  for (const key of colKeys) lanes[key] = [];

  for (const record of records) {
    const lane =
      item.laneMap && item.laneMap.has(record.id)
        ? item.laneMap.get(record.id)
        : record._laneIndex || 0;
    const top = LANE_PADDING + lane * LANE_PITCH;
    const progress =
      record.progress !== null && record.progress !== undefined
        ? Number(record.progress)
        : null;
    let subStyle =
      "position: absolute; top: " +
      top +
      "px; height: " +
      BAR_HEIGHT +
      "px; left: 0; right: 0; display: flex; align-items: center;";
    if (progress != null) {
      subStyle +=
        " background: linear-gradient(to right, rgba(26, 115, 232, 0.12) " +
        progress +
        "%, transparent " +
        progress +
        "%);";
    }
    lanes.name.push({
      recordId: record.id,
      text: record.name || "",
      color: record.color || "#4f46e5",
      subStyle: subStyle,
    });
    if (useDynamic) {
      for (const def of fieldDefs) {
        // La colonne dynamique correspondant à progress_field s'affiche comme
        // la progression native : « % » derrière la valeur, rouge (text-danger)
        // hors plage 0-100, grisée (text-muted) à 0.
        const isProgressCol =
          def.name === renderer?.model?.metaData?.progressField;
        const rawVal = record._raw && record._raw[def.name];
        const numVal =
          isProgressCol && rawVal != null ? Number(rawVal) : NaN;
        const isFiniteNum = isProgressCol && isFinite(numVal);
        lanes[def.name].push({
          text: isProgressCol
            ? formatProgress(numVal)
            : formatFieldValue(rawVal, def),
          top: top,
          height: BAR_HEIGHT,
          isOverdue:
            def.name === renderer?.model?.metaData?.dateEnd &&
            Boolean(record.isOverdue),
          isOverProgress: isFiniteNum && numVal > 100,
          isUnderProgress: isFiniteNum && numVal < 0,
          isZero: isFiniteNum && numVal === 0,
        });
      }
    } else {
      const values = {
        start: formatStartDate(record.start, record.startHasTime),
        end: formatStartDate(record.end, record.endHasTime),
        status: record.status || "",
        duration: formatDuration(record.duration),
        progress: formatProgress(record.progress),
      };
      for (const key of Object.keys(SIDEBAR_COL_WIDTHS)) {
        lanes[key].push({
          text: values[key],
          top: top,
          height: BAR_HEIGHT,
          isOverProgress:
            key === "progress" && progress != null && progress > 100,
          isOverdue: key === "end" && Boolean(record.isOverdue),
        });
      }
    }
  }
  return {
    recordId: primary ? primary.id : null,
    recordIds: records.map((r) => r.id).join(","),
    rowStyle: rowStyle,
    bandHeight: bandHeight,
    lanes: lanes,
  };
}

/**
 * Builds the data object for the GanttSidebarGroupRow template.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} item - Layout item with group data
 * @param {boolean} isChild - Whether this is a nested (child) group
 * @returns {Object} Sidebar group row template data
 */
export function buildSidebarGroupRowData(renderer, item, isChild) {
  const group = item.group;
  const depth = group.depth || 0;
  const cells = {};
  const declaredFields =
    renderer?.model?.metaData?.sidebarColumnFields || [];
  const fieldDefs =
    renderer?.model?.metaData?.sidebarColumnFieldDefs || [];
  if (declaredFields.length) {
    for (const def of fieldDefs) cells[def.name] = "";
  } else {
    for (const key of Object.keys(SIDEBAR_COL_WIDTHS)) cells[key] = "";
  }
  cells.duration = formatDuration(item.groupDuration);
  return {
    isChild,
    isParent: !!group.isParent,
    groupPath: String(group.path),
    groupKey: String(group.key),
    name: group.name || "",
    cells: cells,
    indent: Math.min(depth, 3) * 14,
    isCollapsed: renderer.model.isGroupCollapsed(group.path),
    hasAvatar: !!renderer.model.isAvatarField?.(group.field),
    avatarUrl:
      (renderer.model.isAvatarField?.(group.field) &&
        renderer.model.getAvatarUrl?.(group.field, group.key)) ||
      "",
    avatarInitials: getInitials(group.name || ""),
    avatarColor: getAvatarColor(group.name || ""),
    visibleCount: item.visibleCount || 0,
    height: GROUP_HEADER_HEIGHT,
  };
}

/**
 * Builds the template data of the sidebar body: the shared CSS
 * `grid-template-columns` string and the flat list of rows (flattened groups —
 * child groups become their own rows with an indented name cell — record bands
 * and empty drag-to-create rows).
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object} { cols, colsCss, rows }
 */
export function buildSidebarBodyData(renderer) {
  const cols = buildSidebarCols(renderer);
  const colsCss = sidebarColsCss(cols);
  const rows = [];
  for (const item of renderer._rowLayout || []) {
    if (item.type === "group") {
      rows.push({
        type: "group",
        colsCss: colsCss,
        dragHover: isDragTarget(renderer._dragState, item.group.path),
        row: buildSidebarGroupRowData(
          renderer,
          item,
          (item.group.depth || 0) !== 0,
        ),
      });
    } else if (item.type === "band" && item.empty) {
      rows.push({
        type: "empty",
        colsCss: colsCss,
        height: item.height || ROW_HEIGHT,
      });
    } else if (item.type === "band") {
      rows.push({
        type: "band",
        colsCss: colsCss,
        row: buildSidebarRecordRowData(renderer, item, colsCss),
      });
    }
  }
  return { cols: cols, colsCss: colsCss, rows: rows };
}
