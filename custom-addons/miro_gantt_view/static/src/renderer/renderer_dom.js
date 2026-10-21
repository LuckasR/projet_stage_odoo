/** @odoo-module **/

import { getRecordGroupKey as _getRecordGroupKey } from '@miro_gantt_view/utils/group_by';

/**
 * renderer_dom.js
 *
 * DOM helper functions for the Gantt renderer: floating feedback label,
 * highlight management, and layout query helpers (band lookup, visible→real
 * index mapping, record group key, group path lookup).
 */

/**
 * Creates/repositions the floating feedback dialog ("Task moved" /
 * "Task created") above the highlighted taskbar. The dialog lives on
 * <body> with position: fixed so it is never clipped by row containers.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function updateFeedbackLabel(renderer) {
    if (renderer._highlightRecordId == null || !renderer._highlightLabel) {
        removeFeedbackLabel(renderer);
        return;
    }
    if (!renderer._feedbackEl) {
        const el = document.createElement('div');
        el.className = 'o_gantt_view_pill_feedback';
        document.body.appendChild(el);
        renderer._feedbackEl = el;
    }
    renderer._feedbackEl.textContent = renderer._highlightLabel;
    const pillWrapper = renderer.rootRef.el?.querySelector(
        `.o_gantt_view_pill_wrapper[data-record-id="${renderer._highlightRecordId}"]`
    );
    if (pillWrapper) {
        const rect = pillWrapper.getBoundingClientRect();
        renderer._feedbackEl.style.top = `${Math.max(4, rect.top - 30)}px`;
        renderer._feedbackEl.style.left = `${rect.left + rect.width / 2}px`;
    }
}

/**
 * Removes the floating feedback dialog, if any.
 * @param {Object} renderer - The GanttRenderer instance
 */
export function removeFeedbackLabel(renderer) {
    if (renderer._feedbackEl) {
        renderer._feedbackEl.remove();
        renderer._feedbackEl = null;
    }
}

/**
 * Re-positions the feedback dialog while the highlighted taskbar scrolls.
 * @param {Object} renderer - The GanttRenderer instance
 */
function bindFeedbackScroll(renderer) {
    if (renderer._unbindFeedbackScroll) return;
    const scrollEl = renderer.scrollArea?.el;
    if (!scrollEl) return;
    const onScroll = () => updateFeedbackLabel(renderer);
    scrollEl.addEventListener('scroll', onScroll, { passive: true });
    renderer._unbindFeedbackScroll = () => scrollEl.removeEventListener('scroll', onScroll);
}

/**
 * Highlights the given taskbar with a visible border and a small floating
 * dialog above it for a short duration, then removes both and re-renders.
 * Used after a drag-and-drop / create to show which taskbar just changed.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} recordId - The record ID to highlight
 * @param {string} [label] - Optional short message ("Task moved", ...)
 * @param {number} duration - Highlight duration in ms (default 3000)
 */
export function highlightRecord(renderer, recordId, label = '', duration = 3000) {
    renderer._highlightRecordId = recordId;
    renderer._highlightLabel = label || null;
    if (renderer._highlightTimer) clearTimeout(renderer._highlightTimer);
    renderer._highlightTimer = setTimeout(() => {
        renderer._highlightTimer = null;
        renderer._highlightRecordId = null;
        renderer._highlightLabel = null;
        if (renderer._unbindFeedbackScroll) {
            renderer._unbindFeedbackScroll();
            renderer._unbindFeedbackScroll = null;
        }
        removeFeedbackLabel(renderer);
        renderer.renderGantt();
    }, duration);
    bindFeedbackScroll(renderer);
    renderer.renderGantt();
}

/**
 * Returns true if the given record is currently highlighted.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {number} recordId - The record ID to test
 * @returns {boolean}
 */
export function isRecordHighlighted(renderer, recordId) {
    return renderer._highlightRecordId === recordId;
}

// ---------------------------------------------------------------------------
// Layout query helpers
// ---------------------------------------------------------------------------

/**
 * Finds the band layout item for a group (or the single global band in
 * ungrouped mode) among the computed row layout.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string|number|null} groupPath - The leaf group path, or null
 * @returns {Object|null}
 */
export function findBandItemForPath(renderer, groupPath) {
    const pathStr = groupPath == null ? null : String(groupPath);
    return (
        (renderer._fullRowLayout || []).find((item) => {
            if (item.type !== 'band' || item.empty) return false;
            if (pathStr == null) return item.group == null;
            return item.group && String(item.group.path) === pathStr;
        }) || null
    );
}

/**
 * Converts a visible drop position (band index + lane inside the hovered
 * band) into the REAL insertion index within the target group's full record
 * order.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string|number|null} groupPath - The leaf group path (null ungrouped)
 * @param {number} bandIndex - Visible band index among the group's bands
 * @param {number} lane - The target lane inside the hovered band
 * @returns {number} The 0-based insertion index in the full record order
 */
export function visibleToRealIndex(renderer, groupPath, bandIndex, lane) {
    const band = findBandItemForPath(renderer, groupPath);
    if (!band) return 0;
    const group =
        groupPath == null
            ? null
            : renderer.model._findGroupByPath(String(groupPath));
    const fullIds = groupPath == null
        ? (renderer.model.records || []).map((r) => r.id)
        : (group?.records || []).map((r) => r.id);
    const draggedId = renderer._dragState?.record?.id;
    const lanes = Math.max(1, band.lanes || 1);
    const l = Math.max(0, Math.min(lane || 0, lanes - 1));
    const visible = band.records.filter((r) => r.id !== draggedId);
    if (bandIndex > 0) {
        const lastVisible = visible[visible.length - 1];
        return lastVisible ? fullIds.indexOf(lastVisible.id) + 1 : 0;
    }
    const laneOf = (r) =>
        band.laneMap && band.laneMap.has(r.id)
            ? band.laneMap.get(r.id)
            : r._laneIndex || 0;
    const above = visible.filter((r) => laneOf(r) < l);
    if (!above.length) return 0;
    const lastAbove = above[above.length - 1];
    return fullIds.indexOf(lastAbove.id) + 1;
}

/**
 * Gets the leaf-group path for a record.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The task record
 * @returns {string|null}
 */
export function getRecordGroupKey(renderer, record) {
    return _getRecordGroupKey(record, renderer.groups);
}

/**
 * Finds a group by its path in the group tree.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {string} path - The slash-separated group path
 * @returns {Object|null}
 */
export function getGroupByPath(renderer, path) {
    return renderer.model._findGroupByPath(path);
}
