/** @odoo-module **/

/**
 * renderer_navigation.js
 *
 * Navigation helpers: period dropdown options, formatted focus date label,
 * and scroll/zoom logic. Extracted from GanttRenderer to keep the main
 * renderer file focused on DOM rendering.
 */

import { _t } from "@web/core/l10n/translation";
import {
  MONTHS_SHORT,
  MONTHS_LONG,
  DAY_NAMES,
  ZOOM_CONFIG,
} from "@miro_gantt_view/utils/config";

/**
 * Returns the ISO week number (1 → 52/53) of the given date: the week is
 * counted from the beginning of the year — week 1 is the one containing the
 * first Thursday of the year (ISO 8601 standard, used in the week zoom
 * dropdown, instead of numbering from the current month).
 * @param {Date} date
 * @returns {number}
 */
function isoWeekNumber(date) {
  const d = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()),
  );
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

/**
 * Computes the list of period options for the period dropdown.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object[]} Array of { value, label, selected }
 */
export function computePeriodOptions(renderer) {
  const zoom = renderer.state.zoom;
  const focus = renderer._focusDate;
  const opts = [];

  if (zoom === "day") {
    const start = new Date(focus);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    for (let i = 0; i < 7; i++) {
      const day = new Date(start);
      day.setDate(day.getDate() + i);
      opts.push({
        value: day.getTime(),
        label: `${DAY_NAMES[i]} ${day.getDate()} ${MONTHS_SHORT[day.getMonth()]}`,
        selected: day.toDateString() === focus.toDateString(),
      });
    }
  } else if (zoom === "week") {
    const month = focus.getMonth();
    const monthStart = new Date(focus.getFullYear(), month, 1);
    const monthEnd = new Date(focus.getFullYear(), month + 1, 1);
    let cursor = new Date(monthStart);
    cursor.setDate(cursor.getDate() - ((cursor.getDay() + 6) % 7));
    const focusWeekStart = new Date(focus);
    focusWeekStart.setDate(
      focusWeekStart.getDate() - ((focusWeekStart.getDay() + 6) % 7),
    );
    const fmtDate = (d) =>
      `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
    let _maxIter = 10;
    while (cursor < monthEnd && --_maxIter > 0) {
      const weekEnd = new Date(cursor);
      weekEnd.setDate(weekEnd.getDate() + 6);
      opts.push({
        value: cursor.getTime(),
        // Week number from the start of the year (ISO 8601), not
        // from the current month: e.g. "Week 38 Sep".
        label: `${_t("Week")} ${isoWeekNumber(cursor)} ${MONTHS_SHORT[month]} (${fmtDate(cursor)} - ${fmtDate(weekEnd)})`,
        selected: cursor.toDateString() === focusWeekStart.toDateString(),
      });
      cursor.setDate(cursor.getDate() + 7);
    }
  } else if (zoom === "month") {
    const year = focus.getFullYear();
    for (let m = 0; m < 12; m++) {
      const d = new Date(year, m, 1);
      opts.push({
        value: d.getTime(),
        label: _t(MONTHS_LONG[m]),
        selected: m === focus.getMonth(),
      });
    }
  } else if (zoom === "year") {
    const y = focus.getFullYear();
    for (let i = -2; i <= 3; i++) {
      const yearStart = y + i;
      const d = new Date(yearStart, 0, 1);
      opts.push({
        value: d.getTime(),
        label: String(yearStart),
        selected: yearStart === y,
      });
    }
  }

  return opts;
}

/**
 * Formats the current date range as a human-readable label.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {string} Formatted date range string
 */
export function formatFocusDate(renderer) {
  const { start, end } = renderer.dateRange;
  const zoom = renderer.state.zoom;
  const endInclusive = new Date(end);
  endInclusive.setDate(endInclusive.getDate() - 1);

  if (zoom === "day") {
    // "Tuesday, 01 September 2026" - weekday + padded day + month + year.
    return `${start.toLocaleDateString(undefined, { weekday: "long" })}, ${String(start.getDate()).padStart(2, "0")} ${start.toLocaleDateString(undefined, { month: "long" })} ${start.getFullYear()}`;
  }
  if (zoom === "week") {
    const o = { month: "short", day: "numeric" };
    if (start.getFullYear() !== endInclusive.getFullYear()) {
      o.year = "numeric";
    }
    return `${start.toLocaleDateString(undefined, o)} - ${endInclusive.toLocaleDateString(undefined, { ...o, year: "numeric" })}`;
  }
  if (zoom === "month") {
    const o = { month: "short", day: "numeric" };
    if (start.getFullYear() !== endInclusive.getFullYear()) {
      o.year = "numeric";
    }
    if (
      start.getMonth() !== endInclusive.getMonth() ||
      start.getFullYear() !== endInclusive.getFullYear()
    ) {
      return `${start.toLocaleDateString(undefined, o)} - ${endInclusive.toLocaleDateString(undefined, { ...o, year: "numeric" })}`;
    }
    return `${_t(MONTHS_LONG[start.getMonth()])} ${start.getFullYear()}`;
  }
  if (zoom === "year") {
    const y1 = start.getFullYear();
    const y2 = endInclusive.getFullYear();
    return y1 === y2 ? String(y1) : `${y1}-${y2}`;
  }
  return `${start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} - ${endInclusive.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}

/**
 * Scrolls the view by one page in the given direction.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} direction - 1 for forward, -1 for backward
 */
export function scrollByPage(renderer, direction) {
  renderer._flushPendingWrite();
  const zoom = renderer.state.zoom;
  const d = new Date(renderer._focusDate);
  if (zoom === "day") {
    d.setDate(d.getDate() + direction);
  } else if (zoom === "week") {
    // One week is a full page: keeps the view anchored on a Monday.
    d.setDate(d.getDate() + direction * 7);
  } else if (zoom === "month") {
    const step = renderer.state?.ScrollByPageStep ?? 1;
    d.setDate(d.getDate() + direction * step);
  } else if (zoom === "year") {
    const step = renderer.state?.ScrollByPageStep ?? 1;
    const unit = renderer.zoomCfg.colUnit;
    if (unit === "year") {
      // Year columns: the step counts YEARS (one column = one year).
      d.setFullYear(d.getFullYear() + direction * step);
    } else if (unit === "month") {
      d.setMonth(d.getMonth() + direction * step);
    } else {
      // Day columns: the step counts DAYS (one column = one day).
      d.setDate(d.getDate() + direction * step);
    }
  } else {
    d.setDate(d.getDate() + direction);
  }
  renderer._focusDate = d;
  renderer.state.refresh++;
  renderer.renderGantt();
}

/**
 * Sets the zoom level and re-renders.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string} zoom - The zoom level ID
 */
export function setZoomLevel(renderer, zoom) {
  renderer._flushPendingWrite();
  renderer.state.zoom = zoom;
  if (zoom === "month") {
    renderer._focusDate = new Date();
    renderer._focusDate.setHours(0, 0, 0, 0);
    renderer._focusDate.setDate(1);
  } else if (zoom === "year") {
    renderer._focusDate = new Date();
    renderer._focusDate.setHours(0, 0, 0, 0);
    renderer._focusDate.setMonth(0, 1);
  }
  renderer.renderGantt();
}

/**
 * Scrolls the view to today's date.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function scrollToToday(renderer) {
  renderer._flushPendingWrite();
  renderer._focusDate = new Date();
  renderer._focusDate.setHours(0, 0, 0, 0);
  renderer.state.refresh++;
  renderer.renderGantt();
}

/**
 * Returns the available filter/zoom options for the ViewScaleSelector.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object} Map of scale IDs to { description, hotkey }
 */
export function getAvailableFilters(renderer) {
  const modelScales = renderer.model.metaData.scales || [];
  const zoomScales = modelScales.length
    ? modelScales
    : Object.values(ZOOM_CONFIG);
  const scales = Object.fromEntries(
    zoomScales.map((s) => [s.id, { description: s.label, hotkey: s.id[0] }]),
  );
  // The current zoom must always be representable: a custom date-range
  // filter can switch to a scale that is not declared on the arch. Without
  // this the scale selector crashes.
  const current = renderer.state.zoom;
  if (!scales[current] && ZOOM_CONFIG[current]) {
    scales[current] = {
      description: ZOOM_CONFIG[current].label,
      hotkey: current[0],
    };
  }
  return scales;
}
