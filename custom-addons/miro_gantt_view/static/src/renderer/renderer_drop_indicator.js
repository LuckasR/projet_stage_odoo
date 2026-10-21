/** @odoo-module **/

/**
 * renderer_drop_indicator.js
 *
 * Drop indicator management for drag-and-drop operations.
 * Renders a blue cell highlight on the hovered band during a drag,
 * showing where the taskbar would be placed if dropped.
 */

import { getDateGridBounds } from '@miro_gantt_view/utils/position_compute';

/**
 * Creates/reuses the blue cell highlight attached to a band row.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Element} rowEl - The band row the highlight is attached to
 * @returns {Element} The highlight element
 */
export function ensureDropCellHighlight(renderer, rowEl) {
    if (!renderer._dropCellEl) {
        const cell = document.createElement('div');
        cell.className = 'o_gantt_view_drop_cell';
        renderer._dropCellEl = cell;
    }
    rowEl.appendChild(renderer._dropCellEl);
    return renderer._dropCellEl;
}

/**
 * Removes the blue drop highlight.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function hideDropIndicator(renderer) {
    renderer._dropCellEl?.remove();
    renderer._dropCellEl = null;
}

/**
 * Removes the blue drop highlight and resets drag cursor state.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function clearDropIndicator(renderer) {
    renderer._dropCellEl?.remove();
    renderer._dropCellEl = null;
    renderer._dragLastY = null;
}

/**
 * Finds the DOM wrapper of a group by its path.
 * Prefers the Gantt columns area (contains task pills), skipping sidebar panels.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string} groupPath - The group path to find
 * @returns {Element|null} The group wrapper element
 */
export function findGroupWrapperByPath(renderer, groupPath) {
    const rootEl = renderer.rootRef?.el;
    if (!rootEl) return null;
    const candidates = rootEl.querySelectorAll('[data-group-path]');
    for (const el of candidates) {
        if (
            String(el.dataset.groupPath) === String(groupPath) &&
            el.querySelector('.o_gantt_view_pill_interactive')
        ) {
            return el;
        }
    }
    return null;
}

/**
 * Returns the root grid columns wrapper (holds band rows in ungrouped mode).
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element|null} The grid columns wrapper
 */
export function findRootRowsWrapper(renderer) {
    const rootEl = renderer.rootRef?.el;
    if (!rootEl) return null;
    return rootEl.querySelector('.o_gantt_view_columns');
}

/**
 * Positions the blue drop indicator on the hovered band.
 * Validates the target group is a leaf, finds the band under the cursor,
 * and highlights the cells matching the dragged record's column range.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} clientY - The current cursor Y (viewport coordinate)
 */
export function positionDropIndicator(renderer, clientY) {
    const dragState = renderer._dragState;
    const rootEl = renderer.rootRef?.el;
    if (!dragState || !rootEl) return;

    const targetKey = dragState.targetGroupKey;
    const targetGroup =
        targetKey != null ? renderer.model._findGroupByPath(String(targetKey)) : null;
    const isLeaf =
        targetKey == null ||
        (targetGroup && !targetGroup.isParent && Array.isArray(targetGroup.records));
    if (!isLeaf) {
        hideDropIndicator(renderer);
        return;
    }

    const wrapper =
        targetKey == null
            ? findRootRowsWrapper(renderer)
            : findGroupWrapperByPath(renderer, targetKey);
    if (!wrapper) {
        hideDropIndicator(renderer);
        return;
    }

    const allBands = Array.from(
        wrapper.querySelectorAll('.o_gantt_view_task_row:not(.o_gantt_view_empty_row)')
    );
    const underCursor =
        allBands.find((row) => {
            const rect = row.getBoundingClientRect();
            return clientY >= rect.top && clientY <= rect.bottom;
        }) || null;
    if (!underCursor) {
        hideDropIndicator(renderer);
        return;
    }

    const record = dragState.record;
    const { colStart, colSpan } = getDateGridBounds(
        record,
        renderer.totalColumns,
        renderer.dateRange.start,
        renderer.zoomCfg.colUnit
    );
    const colPct = renderer._columnWidthPct;
    let leftPct = (colStart - 1) * colPct;
    if (leftPct < 0.1) leftPct = 0.1;
    let widthPct = colSpan * colPct;
    if (leftPct + widthPct > 100) widthPct = 100 - leftPct;
    const cell = ensureDropCellHighlight(renderer, underCursor);
    if (cell) {
        cell.style.left = leftPct + '%';
        cell.style.width = widthPct + '%';
    }
}

/**
 * Updates the drop indicator on mousemove.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mouse event
 */
export function updateDropIndicator(renderer, ev) {
    renderer._dragLastY = ev.clientY;
    positionDropIndicator(renderer, ev.clientY);
}

/**
 * Recomputes the drop indicator from the last known cursor Y.
 * Cross-group drag-and-drop is removed: the target stays the record's original
 * group, we just reposition the indicator before finalizing the drag.
 * Called once right before the drag is finalized.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function refreshDropIndicator(renderer) {
    if (renderer._dragState && renderer._dragLastY != null) {
        positionDropIndicator(renderer, renderer._dragLastY);
    }
}

/**
 * Keeps the drop target and indicator in sync during auto-scroll.
 * Called on every auto-scroll frame when the mouse may be stationary.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function syncDragDropPosition(renderer) {
    const dragState = renderer._dragState;
    if (!dragState || renderer._dragLastY == null) return;
    positionDropIndicator(renderer, renderer._dragLastY);
}
