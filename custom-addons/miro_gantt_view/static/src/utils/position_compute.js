/** @odoo-module **/

/**
 * Calculates the month difference between two dates.
 * Handles partial months by counting full months only (day-of-month is ignored).
 * Used as a building block for column indexing and bar positioning in month/year zooms.
 *
 * @param {Date} a - First date
 * @param {Date} b - Second date
 * @returns {number} Number of months between a and b (b - a)
 */
function monthDiff(a, b) {
  return (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth();
}

/**
 * Converts a time difference in milliseconds to an hour-based column index.
 *
 * @param {number} diffMs - Time difference in milliseconds
 * @returns {number} Number of hours (column index)
 */
function getHourColIndex(diffMs) {
  return Math.floor(diffMs / 3600000);
}

/**
 * Returns the column index for a given date relative to the visible range start.
 * The column unit determines the granularity:
 *   "year"  -> year-based columns
 *   "month" -> month-based columns (using monthDiff)
 *   "hour"  -> hour-based columns (for day zoom)
 *   "day"   -> day-based columns (for week/month zoom)
 *
 * @param {Date} date - The date to locate
 * @param {Date} rangeStart - Start of the visible date range
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @returns {number} 0-based column index, clamped to 0
 */
export function getDateColIndex(date, rangeStart, colUnit) {
  if (colUnit === "year") {
    return Math.max(0, date.getFullYear() - rangeStart.getFullYear());
  }
  if (colUnit === "month") {
    return Math.max(0, monthDiff(rangeStart, date));
  }
  const diff = date.getTime() - rangeStart.getTime();
  if (colUnit === "hour") {
    return Math.max(0, getHourColIndex(diff));
  }
  if (colUnit !== "day") {
    console.warn(
      "Unknown colUnit in getDateColIndex:",
      colUnit,
      "falling back to day",
    );
  }
  return Math.max(0, Math.floor(diff / 86400000));
}

/**
 * Returns the pixel position of a date from the left edge of the gantt area.
 * Similar logic to getDateColIndex but returns pixel offset instead of column index.
 *
 * @param {Date} date - The date to position
 * @param {Date} rangeStart - Start of the visible date range
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @param {number} colWidth - Width of one column in pixels
 * @returns {number} Pixel position from the left, clamped to 0
 */
export function getColumnPosition(date, rangeStart, colUnit, colWidth) {
  const d = new Date(date);
  if (colUnit === "year") {
    return Math.max(0, d.getFullYear() - rangeStart.getFullYear()) * colWidth;
  }
  if (colUnit === "month") {
    return Math.max(0, monthDiff(rangeStart, d)) * colWidth;
  }
  const diff = d.getTime() - rangeStart.getTime();
  if (colUnit === "hour") {
    return Math.max(0, getHourColIndex(diff)) * colWidth;
  }
  return Math.max(0, Math.floor(diff / 86400000)) * colWidth;
}

/**
 * Returns the pixel width of a bar spanning from startDate to endDate.
 * Includes the end-date column (inclusive end) so a zero-day task spans one column.
 * Date inputs can be Date objects or numeric timestamps.
 *
 * @param {Date|number} startDate - Task start date
 * @param {Date|number} endDate - Task end date
 * @param {string} colUnit - Column unit: "month" | "hour" | "day"
 * @param {number} colWidth - Width of one column in pixels
 * @returns {number} Bar width in pixels, at least one column wide
 */
export function getBarWidth(startDate, endDate, colUnit, colWidth) {
  const s = new Date(startDate);
  const e = new Date(endDate);
  if (colUnit === "year") {
    const diff = Math.max(1, e.getFullYear() - s.getFullYear() + 1);
    return diff * colWidth;
  }
  if (colUnit === "month") {
    const diff = Math.max(1, monthDiff(s, e) + 1);
    return diff * colWidth;
  }
  if (colUnit === "hour") {
    const diff = e.getTime() - s.getTime() + 3600000;
    const hours = Math.max(1, Math.ceil(diff / 3600000));
    return Math.max(colWidth, hours * colWidth);
  }
  const diff = e.getTime() - s.getTime() + 86400000;
  const days = Math.max(1, Math.ceil(diff / 86400000));
  return Math.max(colWidth, days * colWidth);
}

/**
 * Returns clamped { left, width } for a bar, ensuring it stays within visible columns.
 * Bars that start before the visible range are clipped from the left.
 * Bars that end after the visible range are clipped from the right.
 * When the entire bar falls outside the range, returns zero width.
 *
 * @param {Object} record - Task record with .start and .end dates
 * @param {number} totalColumns - Total number of visible columns
 * @param {number} colWidth - Width of one column in pixels
 * @param {Date} rangeStart - Start of the visible date range
 * @param {string} colUnit - Column unit: "month" | "hour" | "day"
 * @returns {{left: number, width: number}} Clamped pixel position and width
 */

/**
 * Returns the unclamped column index for a date relative to the range start.
 * Unlike getDateColIndex, the result can be negative (before the range) or
 * larger than totalColumns (after the range). Used to detect records that lie
 * entirely outside the visible range.
 *
 * @param {Date} date - The date to locate
 * @param {Date} rangeStart - Start of the visible date range
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @returns {number} Raw (unclamped) column index
 */
export function getRawDateColIndex(date, rangeStart, colUnit) {
  if (colUnit === "year") {
    return date.getFullYear() - rangeStart.getFullYear();
  }
  if (colUnit === "month") {
    return monthDiff(rangeStart, date);
  }
  const diff = date.getTime() - rangeStart.getTime();
  if (colUnit === "hour") {
    return diff / 3600000;
  }
  return diff / 86400000;
}

/**
 * Returns grid column bounds for CSS Grid positioning (1-indexed).
 * Replaces getClampedBarLayout for CSS Grid layouts.
 * Bars that start before the visible range are clipped.
 * Bars that end after the visible range are clipped.
 * `outOfRange` is true when the record lies entirely outside the visible
 * range (before the start or after the end), so callers can hide the row.
 *
 * @param {Object} record - Task record with .start and .end dates
 * @param {number} totalColumns - Total number of visible columns
 * @param {Date} rangeStart - Start of the visible date range
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @returns {{colStart: number, colSpan: number, outOfRange: boolean}} Grid column start (1-based) and span
 */
export function getDateGridBounds(record, totalColumns, rangeStart, colUnit) {
  if (totalColumns <= 0) return { colStart: 1, colSpan: 0, outOfRange: true };

  let startCol = getDateColIndex(record.start, rangeStart, colUnit);
  let endCol = getDateColIndex(record.end, rangeStart, colUnit);

  const startRaw = getRawDateColIndex(record.start, rangeStart, colUnit);
  const endRaw = getRawDateColIndex(record.end, rangeStart, colUnit);
  const outOfRange = endRaw < 0 || startRaw >= totalColumns;

  startCol = Math.max(0, startCol);
  endCol = Math.min(totalColumns - 1, endCol);

  if (endCol < startCol) {
    return { colStart: 1, colSpan: 0, outOfRange: true };
  }

  return {
    colStart: startCol + 1,
    colSpan: endCol - startCol + 1,
    outOfRange,
  };
}

/**
 * Returns the time interval in ms that corresponds to one column unit.
 * Used for drag delta calculations: moving N columns = N * interval ms.
 * Month is approximated as 30 days (30 * 86400000 ms).
 *
 * @param {string} colUnit - Column unit: "month" | "hour" | "day"
 * @returns {number} Interval in milliseconds
 */
export function getDragInterval(colUnit) {
  if (colUnit === "year") return 365 * 86400000;
  if (colUnit === "month") return 30 * 86400000;
  if (colUnit === "hour") return 3600000;
  if (colUnit !== "day") {
    console.warn(
      "Unknown colUnit in getDragInterval:",
      colUnit,
      "falling back to day",
    );
  }
  return 86400000;
}

/**
 * Computes the start and end dates for the visible time range
 * based on the current focus date and zoom level.
 * The range is always [start, end) — end is exclusive.
 *
 * For "day" zoom: shows a single day (24 hours).
 * For "week" zoom: shows the full ISO week (Monday to Sunday).
 * For "month" zoom: shows the full calendar month.
 * For "year" zoom: shows the full calendar year.
 * Falls back to a 7-day range for unknown zoom levels.
 *
 * @param {Date} focusDate - The centered/anchored date
 * @param {string} zoom - Zoom level: "day" | "week" | "month" | "year"
 * @returns {{start: Date, end: Date}} Inclusive start, exclusive end
 */
export function computeDateRange(focusDate, zoom) {
  const focus = focusDate || new Date();

  if (zoom === "day") {
    const start = new Date(focus);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return { start, end };
  }

  if (zoom === "week") {
    // The week always starts on Monday (ISO week); a custom date-range filter
    // is the only case that overrides this via the renderer's dateRange getter.
    const start = new Date(focus);
    start.setHours(0, 0, 0, 0);
    const diff = (start.getDay() + 6) % 7;
    if (diff > 0) start.setDate(start.getDate() - diff);
    const end = new Date(start);
    end.setDate(end.getDate() + 7);
    return { start, end };
  }

  if (zoom === "month") {
    const start = new Date(focus);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setMonth(end.getMonth() + 1);
    return { start, end };
  }

  if (zoom === "year") {
    const start = new Date(focus);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setMonth(end.getMonth() + 12);
    return { start, end };
  }

  // Fallback: 7-day range
  const start = new Date(focus);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return { start, end };
}

/**
 * Returns whether a date lies exactly on a column-unit boundary (00:00:00.000
 * at the very start of the unit). A range whose exclusive `end` falls exactly
 * on a boundary does not cover that unit — e.g. an end of 01/11/2029 00:00
 * only spans up to October, while 01/11/2029 23:59:59.999 includes November.
 * A custom date-range's end is stored as end-of-day, so it always includes its
 * own unit's column.
 * @param {Date} date - The date to test
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @returns {boolean} True when the date is exactly at a unit boundary
 */
export function isUnitBoundary(date, colUnit) {
    if (!date || isNaN(date.getTime())) return false;
    if (colUnit === "month") {
        return (
            date.getDate() === 1 &&
            date.getHours() === 0 &&
            date.getMinutes() === 0 &&
            date.getSeconds() === 0 &&
            date.getMilliseconds() === 0
        );
    }
    if (colUnit === "year") {
        return (
            date.getMonth() === 0 &&
            date.getDate() === 1 &&
            date.getHours() === 0 &&
            date.getMinutes() === 0 &&
            date.getSeconds() === 0 &&
            date.getMilliseconds() === 0
        );
    }
    return false;
}

/**
 * Returns the number of time columns in the given date range for the given column unit.
 *
 * For "year" unit, counts the year difference.
 * For "month" unit, counts the month boundary crossings (not the number of months).
 * For "hour" and "day" units, uses rounding to handle DST transitions.
 *
 * For the month/year units the range is INCLUSIVE of the end unit: the column of
 * the end date is always shown, except when `end` falls exactly on a unit
 * boundary (e.g. 1st of a month at 00:00 for the month unit), where no part of
 * that unit is covered and its column is excluded.
 *
 * @param {{start: Date, end: Date}} dateRange - Visible date range
 * @param {string} colUnit - Column unit: "year" | "month" | "hour" | "day"
 * @returns {number} Total column count
 */
export function computeTotalColumns(dateRange, colUnit) {
  const { start, end } = dateRange;
  if (colUnit === "year") {
    const base = end.getFullYear() - start.getFullYear();
    return base + (isUnitBoundary(end, "year") ? 0 : 1);
  }
  if (colUnit === "month") {
    const base =
      (end.getFullYear() - start.getFullYear()) * 12 +
      end.getMonth() -
      start.getMonth();
    return base + (isUnitBoundary(end, "month") ? 0 : 1);
  }
  if (colUnit === "hour") {
    return Math.round((end.getTime() - start.getTime()) / 3600000);
  }
  return Math.round((end.getTime() - start.getTime()) / 86400000);
}
