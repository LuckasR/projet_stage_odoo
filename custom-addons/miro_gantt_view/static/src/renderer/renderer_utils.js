/** @odoo-module **/

import { NAME_PANEL_WIDTH } from '@miro_gantt_view/utils/config';

/**
 * Evaluates a readonly expression from the arch (e.g. "state == 'draft'",
 * "not(closed)", "user_id in (1,2)") against a record's field values.
 * Supports a small subset of operators useful for per-row readonly fields.
 * @param {string} expr - The readonly expression string
 * @param {Object} record - The task record (uses _raw values first, then mapped values)
 * @returns {boolean} True when the record should be treated as readonly
 */
export function evalReadonlyExpr(expr, record) {
    if (!expr || !record) return false;
    const _raw = record._raw || {};
    const getVal = (f) => (_raw[f] !== undefined ? _raw[f] : record[f]);
    const s = expr.trim();
    const matchNotParen = s.match(/^not\s*\((.+)\)$/);
    if (matchNotParen) return !evalReadonlyExpr(matchNotParen[1], record);
    const matchNotField = s.match(/^not\s+(\w+)$/);
    if (matchNotField) return !getVal(matchNotField[1]);
    const matchIn = s.match(/^(\w+)\s+in\s*\((.+)\)$/);
    if (matchIn) {
        const fv = getVal(matchIn[1]);
        const vals = matchIn[2].split(',').map((v) => v.trim().replace(/^['"]|['"]$/g, ''));
        if (typeof fv === 'number') return vals.map(Number).includes(fv);
        if (typeof fv === 'string') return vals.includes(fv);
        return false;
    }
    const matchOp = s.match(/^(\w+)\s*(!=|==)\s*(.+)$/);
    if (matchOp) {
        const fv = getVal(matchOp[1]);
        const expected = matchOp[3].trim().replace(/^['"]|['"]$/g, '');
        if (matchOp[2] === '!=') return String(fv) !== expected;
        if (matchOp[2] === '==') return String(fv) === expected;
    }
    const matchField = s.match(/^(\w+)$/);
    if (matchField) return !!getVal(matchField[1]);
    return false;
}

/**
 * Determines whether a field is readonly for a specific record, either because
 * the field definition marks it readonly or because a readonly expression in
 * the arch evaluates to true.
 * @param {Object} model - The Gantt model instance
 * @param {string} fieldName - The field name to check
 * @param {Object} record - The task record
 * @returns {boolean} True when the field is readonly for this record
 */
export function isFieldReadonlyForRecord(model, fieldName, record) {
    const fields = model.metaData.fields;
    if (fields && fields[fieldName]?.readonly) return true;
    const exprMap = model.metaData.fieldReadonlyExpr;
    if (exprMap && exprMap[fieldName]) return evalReadonlyExpr(exprMap[fieldName], record);
    return false;
}

/**
 * Computes the current pixel width of a single date column, matching the actual
 * grid layout. The layout always fills the container: columns are sized as
 * availWidth / totalColumns, whatever the zoom, column unit or screen size.
 * @param {Object} scrollArea - The scroll body ref ({ el })
 * @param {number} totalColumns - Number of visible date columns
 * @param {boolean} sidebarVisible - Whether the sidebar is shown
 * @param {number} sidebarWidth - Sidebar width in pixels
 * @param {string} zoom - Current zoom level ID
 * @param {string} colUnit - Column unit of the current zoom
 * @returns {number} Client column width in pixels
 */
export function computeClientColWidth(scrollArea, totalColumns, sidebarVisible, sidebarWidth, zoom, colUnit) {
    if (!totalColumns || !scrollArea) return 100;
    const sbWidth = sidebarVisible ? (sidebarWidth || NAME_PANEL_WIDTH) : 0;
    const availWidth = scrollArea.clientWidth - sbWidth;
    return Math.max(1, availWidth / totalColumns);
}

/**
 * Computes the initial focus date for a zoom level, snapping to the expected
 * anchor: start of week for week zoom, first of month for month, Jan 1
 * for year.
 * @param {string} zoom - The zoom level ID
 * @returns {Date} The initial focus date (normalized to midnight)
 */
export function initFocusDate(zoom) {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    if (zoom === 'week') {
        const diff = (d.getDay() + 6) % 7;
        d.setDate(d.getDate() - diff);
    } else if (zoom === 'month') {
        d.setDate(1);
    } else if (zoom === 'year') {
        d.setMonth(0, 1);
    }
    return d;
}

/**
 * Releases all transient renderer state and DOM listeners when the view is
 * unmounted or an error occurs: highlights, feedback labels, drop indicators,
 * drag listeners and auto-scroll.
 * @param {Object} r - The GanttRenderer instance
 */
export function cleanupRenderer(r) {
    if (r._highlightTimer) {
        clearTimeout(r._highlightTimer);
        r._highlightTimer = null;
    }
    if (r._unbindFeedbackScroll) {
        r._unbindFeedbackScroll();
        r._unbindFeedbackScroll = null;
    }
    if (r._feedbackEl) {
        r._feedbackEl.remove();
        r._feedbackEl = null;
    }
    if (r._dropCellEl) {
        r._dropCellEl.remove();
        r._dropCellEl = null;
    }
    if (r._dragState) {
        document.removeEventListener('mousemove', r._onDrag);
        document.removeEventListener('mouseup', r._stopDrag);
        if (typeof r._clearDropIndicator === 'function') {
            r._clearDropIndicator();
        }
    }
    if (r._renderThrottleRAF) {
        cancelAnimationFrame(r._renderThrottleRAF);
        r._renderThrottleRAF = null;
    }
    if (r._autoScrollRAF) {
        cancelAnimationFrame(r._autoScrollRAF);
        r._autoScrollRAF = null;
    }
    if (r._ghostEl) {
        r._ghostEl.remove();
        r._ghostEl = null;
    }
    if (r._resizeBadgeEl) {
        r._resizeBadgeEl.remove();
        r._resizeBadgeEl = null;
    }
    if (r._totalsChart) {
        r._totalsChart.destroy();
        r._totalsChart = null;
    }
}
