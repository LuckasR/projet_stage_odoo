/** @odoo-module **/

/**
 * renderer_drag.js
 *
 * Drag-and-drop logic for the Gantt chart.
 * Exports standalone functions that receive the renderer instance as first param,
 * keeping the main renderer class thin.
 */

import {
    isDragTarget as _isDragTargetUtil,
    startDrag as _startDragUtil,
} from '@miro_gantt_view/utils/drag_and_drop';
import { onBarClick as _onBarClickUtil } from '@miro_gantt_view/components/taskbar/taskbar';

/**
 * Checks if a group is a valid drag target.
 * Cross-group drag-and-drop is removed: the target stays pinned to the
 * record's original group, so this function always returns `false`.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string} groupKey - The group path to check
 * @returns {boolean}
 */
export function isDragTarget(renderer, groupKey) {
    return _isDragTargetUtil(renderer._dragState, groupKey);
}

/**
 * Initiates a drag operation on a task pill.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mousedown event
 * @param {Object} record - The task record
 * @param {string} mode - Drag mode ("move", "resize", "resize-start")
 */
export function startDrag(renderer, ev, record, mode) {
    _startDragUtil(renderer, ev, record, mode);
}

/**
 * Handles a click on a task bar to show the popover.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The click event
 * @param {Object} record - The task record
 */
export function onBarClick(renderer, ev, record) {
    _onBarClickUtil(renderer, ev, record);
}

// ---------------------------------------------------------------------------
// Column index helpers
// ---------------------------------------------------------------------------

/**
 * Returns the Date for a given 0-based time column index.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} colIndex - 0-based column index
 * @returns {Date}
 */
export function dateFromColIndex(renderer, colIndex) {
    const { start } = renderer.dateRange;
    const colUnit = renderer.zoomCfg.colUnit;
    if (colUnit === 'hour') {
        return new Date(start.getTime() + colIndex * 3600000);
    }
    if (colUnit === 'day') {
        return new Date(start.getTime() + colIndex * 86400000);
    }
    const d = new Date(start);
    if (colUnit === 'month') {
        d.setMonth(d.getMonth() + colIndex);
        return d;
    }
    if (colUnit === 'year') {
        d.setFullYear(d.getFullYear() + colIndex);
        return d;
    }
    return d;
}
