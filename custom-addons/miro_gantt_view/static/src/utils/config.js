/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

const MAX_RENDERED_ROWS = 1000;
/** Height of the empty placeholder rows in pixels (a real band is sized by
 * computeBandHeight; ROW_HEIGHT only sizes empty/fallback rows and must stay
 * in sync with the SCSS `contain-intrinsic-size` hint in miro_gantt.scss). */
const ROW_HEIGHT = 56;

/** Height of a task bar (pill) in pixels */
const BAR_HEIGHT = 30;

/**
 * Vertical padding (in px) above the task bars inside a band row, and below
 * the last task bar. Matches (ROW_HEIGHT - BAR_HEIGHT) / 2 so a single-lane
 * band keeps the exact height of the historical empty placeholder row.
 */
const LANE_PADDING = (ROW_HEIGHT - BAR_HEIGHT) / 2;

/** Minimum vertical gap (in px) between task bars of two adjacent lanes */
const LANE_GAP = 6;

/**
 * Vertical distance between the top edges of two consecutive lanes inside a
 * band row (task bar height + the guaranteed gap, so bars never overlap).
 */
const LANE_PITCH = BAR_HEIGHT + LANE_GAP;

/**
 * Computes the height of a band row holding `lanes` stacked task bars.
 * The band ends exactly at the bottom of its LAST task bar (no trailing
 * padding), so the band's bottom border aligns with the bottom of the last
 * lane — both in the grid and the sidebar (which share the same item.height).
 * Each extra lane adds its bar height plus the inter-lane gap, so the bars of
 * adjacent lanes are always separated by at least LANE_GAP pixels.
 * @param {number} lanes - Number of vertical lanes in the band
 * @returns {number} Height in pixels
 */
function computeBandHeight(lanes) {
  const n = Math.max(1, lanes || 1);
  return LANE_PADDING + n * BAR_HEIGHT + Math.max(0, n - 1) * LANE_GAP;
}

/** Base width of the left sidebar (record name column) in pixels */
const NAME_PANEL_WIDTH = 300;

/** Pixel width of each toggleable sidebar info column. The auto sidebar
 * width is NAME_PANEL_WIDTH + the sum of the widths of the enabled columns.
 * Must stay in sync with the CSS .o_gantt_view_sidebar_* rules. */
const SIDEBAR_COL_WIDTHS = {
  start: 120,
  end: 120,
  status: 96,
  duration: 60,
  progress: 64,
};

/**
 * Target number of day-columns visible at once in the year zoom (desktop).
 * The year zoom displays every day of the year (365/366 columns) and must
 * scroll horizontally; its columns are sized so roughly three months fit on
 * screen.
 */
const YEAR_VISIBLE_DAYS = 90;

/**
 * Maximum span of a user-picked custom date range, in years. Ranges wider
 * than this are clamped to start + MAX_RANGE_YEARS - 1 day, keeping the
 * renderable column count bounded (100 year-columns).
 */
const MAX_RANGE_YEARS = 100;

/** Header labels of the toggleable sidebar info columns */
const SIDEBAR_COL_LABELS = {
  start: _t("Start date"),
  end: _t("End date"),
  status: _t("Status"),
  duration: _t("Duration"),
  progress: _t("Progress"),
};

/**
 * Default column width (in px) for a sidebar info column, by field type
 * (used for the toggleable dynamic fields of `_sidebarToggleFields`).
 * Date fields need more room (dd/MM/yyyy + HH:mm), numeric fields are narrow.
 * @param {string} type - The field type (date, datetime, integer, boolean...)
 * @returns {number} Width in pixels
 */
function colWidthForType(type) {
  if (["date", "datetime"].includes(type)) return 150;
  if (["integer", "float", "monetary"].includes(type)) return 110;
  if (type === "boolean") return 90;
  return 130; // char, selection, many2one...
}

/**
 * Ordered list of the sidebar columns to render: the name column (always
 * first, width NAME_PANEL_WIDTH) followed by the enabled info columns. When
 * the arch declares `sidebar_column_fields`, the columns come from those
 * dynamic field definitions (width by type, label from the field string);
 * otherwise the historical fixed columns (start/end/status/duration/progress)
 * are used. Used to build the <colgroup> and the <th>/<td> cells of the
 * sidebar tables, so the header and the body share exactly the same column
 * geometry.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object[]} [{ key, width, label? }]
 */
function buildSidebarCols(renderer) {
  const fields = renderer?.state?.sidebarFields || {};
  const cols = [{ key: "name", width: NAME_PANEL_WIDTH }];
  const declaredFields =
    renderer?.model?.metaData?.sidebarColumnFields || [];
  const fieldDefs = renderer?.model?.metaData?.sidebarColumnFieldDefs || [];
  if (declaredFields.length) {
    for (const def of fieldDefs) {
      if (fields[def.name]) {
        cols.push({
          key: def.name,
          width: colWidthForType(def.type),
          label: def.label,
        });
      }
    }
  } else {
    for (const key of Object.keys(SIDEBAR_COL_WIDTHS)) {
      if (fields[key]) {
        cols.push({
          key,
          width: SIDEBAR_COL_WIDTHS[key],
          label: SIDEBAR_COL_LABELS[key],
        });
      }
    }
  }
  return cols;
}

/**
 * CSS `grid-template-columns` string matching the sidebar columns (name column
 * + enabled info columns). The last info column is left as `1fr` so the row
 * grid stretches exactly to the sidebar width (mimicking the old
 * table-layout:fixed) while every column stays pixel-aligned with the header
 * band, which uses the same string.
 * @param {Object[]} cols - Output of buildSidebarCols()
 * @returns {string} e.g. "250px 98px minmax(64px, 1fr)"
 */
function sidebarColsCss(cols) {
  const tracks = cols.map((c) => c.width + "px");
  if (tracks.length > 1) {
    tracks[tracks.length - 1] =
      "minmax(" + tracks[tracks.length - 1] + ", 1fr)";
  }
  return tracks.join(" ");
}

/** Maximum width reachable by dragging the sidebar resize handle */
const SIDEBAR_MAX_WIDTH = 900;

/** Minimum column width in pixels (prevents columns from being too narrow) */
const MIN_COL_WIDTH = 60;

/** Height of a group header row in pixels */
const GROUP_HEADER_HEIGHT = 32;

/**
 * Number of empty task rows rendered when no tasks are loaded.
 * These rows keep the grid visible so the user sees columns even with no data.
 */
const EMPTY_ROW_COUNT = 2;

/** Abbreviated month names for column headers (e.g., "Jan", "Feb", ...) */
const MONTHS_SHORT = [
  _t("Jan"),
  _t("Feb"),
  _t("Mar"),
  _t("Apr"),
  _t("May"),
  _t("Jun"),
  _t("Jul"),
  _t("Aug"),
  _t("Sep"),
  _t("Oct"),
  _t("Nov"),
  _t("Dec"),
];

/** Full month names for display (e.g., "January", "February", ...) */
const MONTHS_LONG = [
  _t("January"),
  _t("February"),
  _t("March"),
  _t("April"),
  _t("May"),
  _t("June"),
  _t("July"),
  _t("August"),
  _t("September"),
  _t("October"),
  _t("November"),
  _t("December"),
];

/** Weekday names starting from Monday (e.g., "Mon", "Tue", ...) */
const DAY_NAMES = [
  _t("Mon"),
  _t("Tue"),
  _t("Wed"),
  _t("Thu"),
  _t("Fri"),
  _t("Sat"),
  _t("Sun"),
];

/**
 * Color palette assigned to task bars.
 * Colors cycle based on the colored_by field value.
 * 12 distinct colors suitable for dark backgrounds (white text).
 */
const COLOR_PALETTE = [
  "#1A56DB",
  "#096B5E",
  "#0A4F22",
  "#7048D4",
  "#067A99",
  "#5254D0",
  "#0D6458",
  "#3E38B5",
  "#475A2D",
  "#3A4555",
  "#0170A8",
  "#6B30D0",
];

/** Reverse lookup map: hex color string -> index in COLOR_PALETTE */
const COLOR_INDEXES = Object.fromEntries(
  COLOR_PALETTE.map((color, index) => [color, index]),
);

/**
 * Returns the palette index for a hex color, defaulting to 0 if not found.
 * @param {string} hex - A hex color string from the palette
 * @returns {number} The index in COLOR_PALETTE
 */
export function getColorIndex(hex) {
  return COLOR_INDEXES[hex] !== undefined ? COLOR_INDEXES[hex] : 0;
}

/**
 * Zoom level configurations.
 * Each level defines a column unit (hour/day/month/year) and a default column width in pixels.
 * The colUnit determines how time is divided:
 *   - "hour": each column represents one hour (used in "day" zoom)
 *   - "day": each column represents one day (used in "week", "month" and
 *     "year" zoom — the year zoom shows every day of the year, the header
 *     regrouping the days per month)
 *   - "month" and "year": unused by any zoom level (kept for compatibility)
 */
const ZOOM_CONFIG = {
  day: { id: "day", label: _t("Day"), colUnit: "hour" },
  week: { id: "week", label: _t("Week"), colUnit: "day" },
  month: { id: "month", label: _t("Month"), colUnit: "day" },
  year: { id: "year", label: _t("Year"), colUnit: "day" },
};

/**
 * Returns initials from a name (first letter of first and last name parts).
 * If the name has only one part, returns the first two characters.
 * Falls back to "?" for empty/null names.
 *
 * @param {string} name - The full name
 * @returns {string} Uppercase initials
 */
export function getInitials(name) {
  if (!name) return "?";
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return String(name).slice(0, 2).toUpperCase();
}

/**
 * Deterministic color assignment from a string using the existing palette.
 * Hashes the string and uses modulo to pick a color.
 * Used for avatar fallback backgrounds.
 *
 * @param {string} name - The name to derive a color from
 * @returns {string} A hex color string from COLOR_PALETTE
 */
export function getAvatarColor(name) {
  let hash = 0;
  const text = String(name || "");
  for (let i = 0; i < text.length; i++) {
    hash = text.charCodeAt(i) + ((hash << 5) - hash);
  }
  return COLOR_PALETTE[Math.abs(hash) % COLOR_PALETTE.length];
}

/**
 * Creates a 24x24 span element showing initials as a fallback avatar.
 * Used when an avatar image is not available for a group header.
 *
 * @param {string} name - The name to derive initials from
 * @returns {Element} A styled span element with initials
 */
export function createAvatarFallback(name) {
  const span = document.createElement("span");
  span.style.width = "26px";
  span.style.height = "26px";
  span.style.borderRadius = "10%";
  span.style.display = "inline-flex";
  span.style.alignItems = "center";
  span.style.justifyContent = "center";
  span.style.fontSize = "11px";
  span.style.fontWeight = "bold";
  span.style.color = "#fff";
  span.style.marginRight = "4px";
  span.style.flexShrink = "0";
  span.textContent = getInitials(name);
  span.style.backgroundColor = getAvatarColor(name);
  return span;
}

// Color intensity thresholds for week / month zooms.
// The hue stays blue (215°), only the saturation varies (see SCSS).
const TOTALS_BAR_COLOR_LOW = 2;
const TOTALS_BAR_COLOR_MID = 5;
const TOTALS_BAR_COLOR_ZOOMS = new Set(["week", "month"]);

// Export all constants and utility functions
export {
  TOTALS_BAR_COLOR_LOW,
  TOTALS_BAR_COLOR_MID,
  TOTALS_BAR_COLOR_ZOOMS,
  ZOOM_CONFIG,
  ROW_HEIGHT,
  BAR_HEIGHT,
  LANE_PADDING,
  LANE_GAP,
  LANE_PITCH,
  computeBandHeight,
  NAME_PANEL_WIDTH,
  SIDEBAR_COL_WIDTHS,
  SIDEBAR_MAX_WIDTH,
  buildSidebarCols,
  sidebarColsCss,
  MIN_COL_WIDTH,
  YEAR_VISIBLE_DAYS,
  MAX_RANGE_YEARS,
  GROUP_HEADER_HEIGHT,
  EMPTY_ROW_COUNT,
  MONTHS_SHORT,
  MONTHS_LONG,
  DAY_NAMES,
  MAX_RENDERED_ROWS,
  COLOR_PALETTE,
  COLOR_INDEXES,
  getColorIndex,
  getInitials,
  getAvatarColor,
  createAvatarFallback,
};
