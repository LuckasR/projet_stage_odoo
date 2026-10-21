/** @odoo-module **/

import { BAR_HEIGHT, MONTHS_SHORT } from '@miro_gantt_view/utils/config';

/**
 * Formats a date for the drag indicator label.
 * @param {Date} date - The date to format
 * @returns {string} Formatted date string (e.g. "23 Jul 2026")
 */
function _formatDragDate(date) {
    if (!date) return '';
    const d = date instanceof Date ? date : new Date(date);
    const day = d.getDate();
    const month = MONTHS_SHORT[d.getMonth()];
    const year = d.getFullYear();
    return `${day} ${month} ${year}`;
}

/**
 * Formats the drag date range label.
 * @param {Date} start - Start date
 * @param {Date} end - End date
 * @returns {string} Formatted range (e.g. "07 Oct 2026 -> 20 Oct 2026")
 */
export function _formatDragDateRange(start, end) {
    return _formatDragDate(start) + ' -> ' + _formatDragDate(end);
}

/**
 * Formats the day count for the drag label.
 * @param {Date} start - Start date
 * @param {Date} end - End date
 * @returns {string} Formatted day count (e.g. " (14 days)")
 */
export function _formatDayCount(start, end, count) {
    const days = count !== undefined ? count : Math.round(Math.abs(end - start) / 86400000) + 1;
    return ` (${days} ${days > 1 ? 'days' : 'day'})`;
}

/**
 * Creates a visual ghost element that follows the mouse cursor during drag.
 * The ghost is a clone of the original task pill, positioned at the cursor location.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mousedown event
 * @param {Object} record - The task record being dragged
 */
export function createGhost(renderer, ev, record) {
    try {
        // Find the original pill element to clone
        const originalPill = ev.target
            .closest('.o_gantt_view_pill_wrapper')
            ?.querySelector('.o_gantt_view_pill');
        const ghost = originalPill ? originalPill.cloneNode(true) : document.createElement('div');

        ghost.className = 'o_gantt_view_pill o_miro_dragged_pill';
        // Only the colored bar (and its handles) follow the cursor: strip the
        // task label (inside pill title or outside label) and status badge
        // from the cloned pill.
        const ghostTitle = ghost.querySelector('.o_gantt_view_pill_title');
        if (ghostTitle) ghostTitle.remove();
        const ghostOutsideLabel = ghost.querySelector('.o_gantt_view_pill_label_outside');
        if (ghostOutsideLabel) ghostOutsideLabel.remove();
        const ghostBadge = ghost.querySelector('.o_gantt_view_status_badge');
        if (ghostBadge) ghostBadge.remove();
        ghost.style.position = 'fixed';
        ghost.style.zIndex = '15';
        ghost.style.opacity = '1';
        ghost.style.pointerEvents = 'none';
        ghost.style.width =
            (originalPill ? originalPill.offsetWidth : renderer._clientColWidth) + 'px';
        ghost.style.height = (originalPill ? originalPill.offsetHeight : BAR_HEIGHT) + 'px';
        ghost.style.minHeight = 'auto';
        ghost.style.flex = 'none';
        // Tilt the dragged ghost (the element lives on <body>, outside the gantt
        // container, so a nested SCSS rule would never match — inline style wins).
        ghost.style.transform = 'rotate(-2deg)';
        ghost.style.boxShadow = '0 15px 40px rgba(0, 0, 0, 0.3), 0 5px 15px rgba(0, 0, 0, 0.2)';

        if (originalPill) {
            // Copy computed styles from the original pill for visual consistency
            const origCS = getComputedStyle(originalPill);
            ghost.style.backgroundColor = origCS.backgroundColor;
            ghost.style.borderRadius = origCS.borderRadius;

            // Calculate the offset between the cursor and the pill's top-left corner
            const pillRect = originalPill.getBoundingClientRect();
            renderer._dragOffsetX = ev.clientX - pillRect.left;
            renderer._dragOffsetY = ev.clientY - pillRect.top;

            // Copy styles from child elements (title, drag handle, resize handles)
            const copyStyle = (sel, props) => {
                const ghostEl = ghost.querySelector(sel);
                const origEl = originalPill.querySelector(sel);
                if (ghostEl && origEl) {
                    const cs = getComputedStyle(origEl);
                    props.forEach((p) => (ghostEl.style[p] = cs[p]));
                }
            };
            copyStyle('.o_gantt_view_pill_title', ['color', 'textShadow']);
            copyStyle('.o_gantt_view_resize_handle', ['color', 'opacity']);
            copyStyle('.o_gantt_view_resize_handle_left', ['color', 'opacity']);
        } else {
            // No original pill found: center the ghost on the cursor
            renderer._dragOffsetX = 0;
            renderer._dragOffsetY = 0;
        }

        // Add the ghost to the body and position it
        document.body.appendChild(ghost);
        renderer._ghostEl = ghost;

        // Create date range label as a child of the ghost
        const dateLabel = document.createElement('div');
        dateLabel.className = 'o_gantt-view_drag_date_label';
        dateLabel.textContent =
            _formatDragDateRange(record.start, record.end) +
            _formatDayCount(record.start, record.end);
        ghost.style.position = 'fixed';
        ghost.style.overflow = 'visible';
        ghost.appendChild(dateLabel);
        renderer._ghostDateLabel = dateLabel;

        positionGhost(renderer, ev);
    } catch (error) {
        console.error('Failed to create ghost:', error);
        renderer._dragOffsetX = 0;
        renderer._dragOffsetY = 0;
    }
}

/**
 * Positions the ghost element at the cursor location during drag.
 * The ghost is `position: fixed` on <body>, so it is positioned in viewport
 * coordinates: `clientX`/`clientY` already include any page scroll, adding
 * `pageXOffset`/`pageYOffset` would double-count it.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mouse event
 */
export function positionGhost(renderer, ev) {
    if (!renderer._ghostEl) return;
    const x = ev.clientX - (renderer._dragOffsetX || renderer._ghostEl.offsetWidth / 2);
    const y = ev.clientY - (renderer._dragOffsetY || renderer._ghostEl.offsetHeight / 2);
    renderer._ghostEl.style.left = x + 'px';
    renderer._ghostEl.style.top = y + 'px';
}

/**
 * Creates/updates the floating resize badge shown while resizing a task bar.
 * Displays the live date range and day count above the bar, mirroring the.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The task record being resized
 * @param {MouseEvent} [ev] - The mouse event, used to follow the cursor
 */
export function updateResizeBadge(renderer, record, ev) {
    try {
        if (!renderer._resizeBadgeEl) {
            const badge = document.createElement('div');
            badge.className = 'o_gantt_view_resize_badge';
            document.body.appendChild(badge);
            renderer._resizeBadgeEl = badge;
        }
        const badge = renderer._resizeBadgeEl;
        badge.textContent =
            _formatDragDateRange(record.start, record.end) +
            _formatDayCount(record.start, record.end);

        // Follow the cursor, mirroring the drag ghost label (on-drag dates are
        // shown attached to the pointer; the resize badge must behave the same).
        const dragState = renderer._dragState || {};
        const clientX = ev && ev.clientX != null ? ev.clientX : dragState.startX;
        const clientY = ev && ev.clientY != null ? ev.clientY : dragState.startY;
        badge.style.top = `${Math.max(4, (clientY || 0) - 26)}px`;
        badge.style.left = `${clientX || 0}px`;
    } catch (error) {
        console.warn('Failed to update resize badge:', error);
    }
}

/**
 * Removes the resize badge element if present.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function removeResizeBadge(renderer) {
    if (renderer._resizeBadgeEl) {
        renderer._resizeBadgeEl.remove();
        renderer._resizeBadgeEl = null;
    }
}
