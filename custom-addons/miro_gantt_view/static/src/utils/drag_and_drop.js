/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { DragConfirmDialog } from "@miro_gantt_view/components/dialogs/drag_confirm_dialog";
import { extractErrorMessage } from "@miro_gantt_view/utils/error_message";
import { getRecordGroupKey } from "@miro_gantt_view/utils/group_by";
import { getDragInterval } from "@miro_gantt_view/utils/position_compute";
import {
  createGhost,
  positionGhost,
  updateResizeBadge,
  removeResizeBadge,
} from "@miro_gantt_view/utils/ghost";
import {
  checkAutoScroll,
  stopAutoScroll,
} from "@miro_gantt_view/utils/autoscroll";
import {
  _formatDragDateRange,
  _formatDayCount,
} from "@miro_gantt_view/utils/ghost";
import { buildTaskRowData } from "@miro_gantt_view/utils/row";

/**
 * Checks whether a given group key is a valid target for a drag-and-drop operation.
 * A group is a valid target if:
 *   1. A drag operation is active (dragState exists)
 *   2. A target group key has been set (dragState.targetGroupKey is not null)
 *   3. The target group key matches the provided groupKey
 *   4. The target group is different from the original group
 *
 * Since cross-group drag-and-drop was removed, `targetGroupKey` stays pinned
 * to the record's original group, so this function always returns `false`
 * (no other group is highlighted as a target).
 *
 * @param {Object|null} dragState - The current drag state (null if no drag active)
 * @param {string} groupKey - The group path to check
 * @returns {boolean} True if this group is a valid drag target
 */
export function isDragTarget(dragState, groupKey) {
  return (
    dragState &&
    dragState.targetGroupKey != null &&
    String(dragState.targetGroupKey) === String(groupKey) &&
    String(dragState.originalGroupKey) !== String(groupKey)
  );
}

/**
 * Schedules a throttled re-render using requestAnimationFrame.
 */
function scheduleRender(renderer) {
  if (renderer._renderThrottleRAF) return;
  renderer._renderThrottleRAF = requestAnimationFrame(() => {
    renderer._renderThrottleRAF = null;
    renderer.renderGantt();
  });
}

/**
 * Live-syncs the visual position of every pill sharing the same record id
 * across multiple bands. A task grouped by a many2many field (e.g. assignees)
 * appears once per assigned user using the SAME record object, so a drag that
 * mutates record.start/end must reposition all sibling bars in real time.
 * This is done imperatively (just left/width style writes) instead of a full
 * Gantt DOM rebuild on every mousemove, keeping the move-drag UX fluid.
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The record being dragged (shared across bands)
 */
function syncSiblingBars(renderer, record) {
  if (!record || record.id == null) return;
  const data = buildTaskRowData(renderer, record);
  const wrappers = document.querySelectorAll(
    `.o_gantt_view_pill_wrapper[data-record-id="${record.id}"]`,
  );
  for (const wrapper of wrappers) {
    wrapper.style.left = data.pillLeftPct + "%";
    wrapper.style.width = data.pillWidthPct + "%";
    wrapper.classList.toggle("o_gantt_view_pill_offscreen", data.outOfRange);
  }
}

/**
 * Updates the visual position of a task bar and triggers a throttled re-render.
 */
function updateBarPosition(renderer, record, newStartTime, newEndTime) {
  record.start = new Date(newStartTime);
  record.end = new Date(newEndTime);
  // Re-position every bar of the same record (multi-assignee M2M groups slide
  // together live), in every drag mode.
  syncSiblingBars(renderer, record);
  const container = renderer.rootRef.el;
  if (!container) return;
  // During a "move" drag the live feedback is fully imperative (the ghost pill
  // follows the cursor, the drop indicator/placeholder is re-positioned by
  // _updateDropIndicator on every mousemove and _syncDragDropPosition during
  // auto-scroll), so skipping the whole-DOM re-render here avoids rebuilding the
  // Gantt on every mouse frame. The layout pill keeps its original position
  // until the drag is committed or cancelled, matching the ghost-based UX.
  // The "resize" modes still need the re-render: the task bar must resize live.
  if (renderer._dragState && renderer._dragState.mode !== "move") {
    scheduleRender(renderer);
  }
}

/**
 * Initializes a drag operation on a task pill.
 * Sets up drag state, attaches event listeners, and provides visual feedback.
 * Supports three modes:
 *   - "move": drag the task to a new date (within its own group)
 *   - "resize": drag the right edge to change the end date
 *   - "resize-start": drag the left edge to change the start date
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mousedown event
 * @param {Object} record - The task record being dragged
 * @param {string} mode - The drag mode ("move", "resize", "resize-start")
 */
export function startDrag(renderer, ev, record, mode) {
  if (!renderer.model.metaData.canEdit) {
  try {
    renderer.notificationService.add(
      _t("Editing and deletion are not allowed."),
      {
        title: _t("Read-only view"),
        type: "warning",
      },
    );
  } catch (e) {
    console.warn("Notification failed:", e);
  }
    return;
  }
  if (renderer._flushPendingWrite) {
    renderer._flushPendingWrite();
  }
  const { dateEnd, dateStart } = renderer.model.metaData;
  if (
    mode === "resize" &&
    renderer._isFieldReadonlyForRecord(dateEnd, record)
  ) {
    try {
      renderer.notificationService.add(_t("date end is readonly"), {
        title: _t("Cannot resize"),
        type: "warning",
      });
    } catch (e) {
      console.warn("Notification failed:", e);
    }
    return;
  }
  if (
    mode === "resize-start" &&
    renderer._isFieldReadonlyForRecord(dateStart, record)
  ) {
    try {
      renderer.notificationService.add(_t("date start is readonly"), {
        title: _t("Cannot resize"),
        type: "warning",
      });
    } catch (e) {
      console.warn("Notification failed:", e);
    }
    return;
  }
  if (
    mode === "move" &&
    renderer._isFieldReadonlyForRecord(dateStart, record) &&
    renderer._isFieldReadonlyForRecord(dateEnd, record)
  ) {
    try {
      renderer.notificationService.add(
        _t("date Start and date End are readonly"),
        { title: _t("Cannot move"), type: "warning" },
      );
    } catch (e) {
      console.warn("Notification failed:", e);
    }
    return;
  }

  ev.preventDefault();
  ev.stopPropagation();
  renderer._justDragged = false;

  // Capture the original state for undo in case of cancellation or failure
  const originalGroupKey = getRecordGroupKey(record, renderer.groups);
  renderer._dragState = {
    record,
    mode,
    startX: ev.clientX,
    startY: ev.clientY,
    originalStart: new Date(record.start).getTime(),
    originalEnd: new Date(record.end).getTime(),
    targetStart: new Date(record.start).getTime(),
    targetEnd: new Date(record.end).getTime(),
    originalDayCount:
      Math.round(Math.abs(record.end - record.start) / 86400000) + 1,
    originalGroupKey,
    // Cross-group drag-and-drop is removed: the target stays pinned to the
    // record's original group, only date changes are allowed.
    targetGroupKey: originalGroupKey,
    isDragging: false, // Not dragging yet, waiting for threshold
  };

  // Attach document-level event listeners for tracking the drag
  document.addEventListener("mousemove", renderer._onDrag);
  document.addEventListener("mouseup", renderer._stopDrag);
}

/**
 * Handles the mousemove event during a drag operation.
 * Updates the ghost position, applies auto-scroll, calculates date deltas,
 * and updates the task bar position in real-time.
 * Cross-group drag-and-drop is removed: the target stays the record's
 * original group, only the move through time is taken into account.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The mouse event
 */
export function onDrag(renderer, ev) {
  if (!renderer._dragState) return;

  try {
    // Check if movement threshold is met before starting actual drag
    if (!renderer._dragState.isDragging) {
      const deltaX = ev.clientX - renderer._dragState.startX;
      const deltaY = ev.clientY - renderer._dragState.startY;
      if (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5) {
        renderer._dragState.isDragging = true;
        renderer.popover.close();
      } else {
        return; // Not dragging yet
      }
    }

    // Create ghost on first move (for "move" mode only)
    if (!renderer._ghostEl && renderer._dragState.mode === "move") {
      createGhost(renderer, ev, renderer._dragState.record);
    } else if (renderer._ghostEl) {
      positionGhost(renderer, ev);
    }

    // Check for auto-scroll at the edges of the scroll area
    checkAutoScroll(renderer, ev);

    // Calculate the mouse delta
    const deltaX = ev.clientX - renderer._dragState.startX;

    // Convert pixel delta to column/unit delta
    const interval = getDragInterval(renderer.zoomCfg.colUnit);
    const colWidth = renderer._clientColWidth;
    const deltaUnits = Math.round(deltaX / colWidth);
    const { record, mode, originalStart, originalEnd } = renderer._dragState;

    // For tasks without time components, snap to whole-day increments
    const noTime =
      mode === "resize"
        ? !record.endHasTime
        : mode === "resize-start"
          ? !record.startHasTime
          : !record.startHasTime || !record.endHasTime;
    let effInterval = interval;
    let effDelta = deltaUnits;
    if (noTime) {
      const totalMs = deltaUnits * interval;
      effDelta = Math.round(totalMs / 86400000);
      effInterval = 86400000;
    }

    // Apply the delta based on drag mode
    if (mode === "move") {
      const colUnit = renderer.zoomCfg.colUnit;
      if (colUnit === "month" || colUnit === "year") {
        const monthShift = deltaUnits * (colUnit === "year" ? 12 : 1);
        const startDate = new Date(originalStart);
        const endDate = new Date(originalEnd);
        startDate.setMonth(startDate.getMonth() + monthShift);
        endDate.setMonth(endDate.getMonth() + monthShift);
        renderer._dragState.targetStart = startDate.getTime();
        renderer._dragState.targetEnd = endDate.getTime();
        updateBarPosition(
          renderer,
          record,
          startDate.getTime(),
          endDate.getTime(),
        );
      } else {
        const newStart = originalStart + effDelta * effInterval;
        const duration = originalEnd - originalStart;
        const newEnd = newStart + duration;
        renderer._dragState.targetStart = newStart;
        renderer._dragState.targetEnd = newEnd;
        updateBarPosition(renderer, record, newStart, newEnd);
      }
    } else if (mode === "resize") {
      // Resize from the right edge: only change the end date
      const newEnd = originalEnd + effDelta * effInterval;
      if (newEnd > originalStart) {
        updateBarPosition(renderer, record, originalStart, newEnd);
      }
    } else if (mode === "resize-start") {
      // Resize from the left edge: only change the start date
      const newStart = originalStart + effDelta * effInterval;
      if (newStart < originalEnd) {
        updateBarPosition(renderer, record, newStart, originalEnd);
      }
    }

    // Live resize badge while resizing: shows the current
    // start -> end dates and day count, following the cursor like the drag label
    if (mode === "resize" || mode === "resize-start") {
      updateResizeBadge(renderer, record, ev);
    }

    // Update date label with current dates
    if (renderer._ghostDateLabel) {
      const ds = renderer._dragState;
      const labelStart =
        ds.mode === "move" ? new Date(ds.targetStart) : record.start;
      const labelEnd = ds.mode === "move" ? new Date(ds.targetEnd) : record.end;
      const dayCount =
        ds.mode === "move"
          ? ds.originalDayCount
          : Math.round(Math.abs(labelEnd - labelStart) / 86400000) + 1;
      renderer._ghostDateLabel.textContent =
        _formatDragDateRange(labelStart, labelEnd) +
        _formatDayCount(labelStart, labelEnd, dayCount);
    }

    // Update the insertion position + drop indicator live. Runs in both grouped
    // and ungrouped modes (ungrouped targets the single global band). As the
    // target is pinned to the original group, only its band is hovered.
    if (
      mode === "move" &&
      typeof renderer._updateDropIndicator === "function"
    ) {
      renderer._updateDropIndicator(ev);
    }
  } catch (error) {
    console.error("Drag error:", error);
    cleanupDrag(renderer);
  }
}

/**
 * Cleans up drag state: removes ghost element, detaches event listeners,
 * stops auto-scroll, and nullifies the drag state.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
function cleanupDrag(renderer) {
  stopAutoScroll(renderer);
  if (renderer._ghostEl) {
    renderer._ghostEl.remove();
    renderer._ghostEl = null;
  }
  renderer._ghostDateLabel = null;
  removeResizeBadge(renderer);
  if (typeof renderer._clearDropIndicator === "function") {
    renderer._clearDropIndicator();
  }
  document.removeEventListener("mousemove", renderer._onDrag);
  document.removeEventListener("mouseup", renderer._stopDrag);
  renderer._dragState = null;
}

/**
 * Finalizes the drag operation.
 * Compares the new dates with the original: if the dates changed, saves them
 * immediately and shows a "rescheduled" notification with an Undo button that
 * reverts the change on the server.
 *
 * Cross-group drag-and-drop is removed: the record never changes group, only
 * its position through time (within its original group) can evolve.
 *
 * If the save fails, the task reverts to its original position visually.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
export async function stopDrag(renderer) {
  if (!renderer._dragState) return;

  const wasDragging = renderer._dragState.isDragging;
  const taskLabel = renderer.model.metaData.defaultTitle || _t("Task");

  // Recompute the drop index so it matches the indicator that was last shown,
  // even if a throttled re-render happened since the final mousemove.
  if (typeof renderer._refreshDropIndicator === "function") {
    renderer._refreshDropIndicator();
  }

  // Capture drag state values before cleanup
  const {
    record,
    originalStart,
    originalEnd,
    targetStart,
    targetEnd,
    mode: dragMode,
  } = renderer._dragState;

  cleanupDrag(renderer);
  const newStart = dragMode === "move" ? new Date(targetStart) : record.start;
  const newEnd = dragMode === "move" ? new Date(targetEnd) : record.end;
  const { dateStart, dateEnd } = renderer.model.metaData;
  const dsReadonly = renderer._isFieldReadonlyForRecord(dateStart, record);
  const deReadonly = renderer._isFieldReadonlyForRecord(dateEnd, record);

  const datesChanged =
    (newStart.getTime() !== originalStart ||
      newEnd.getTime() !== originalEnd) &&
    ((dragMode === "move" && (!dsReadonly || !deReadonly)) ||
      (dragMode === "resize" && !deReadonly) ||
      (dragMode === "resize-start" && !dsReadonly));

  // If a real drag happened, set a flag so the pill click handler skips opening the popover
  if (wasDragging) {
    renderer._justDragged = true;
    setTimeout(() => {
      renderer._justDragged = false;
    }, 100);
  }

  if (!datesChanged) {
    // Nothing actually changed — just re-render so the UI reflects the final
    // state (e.g. _justDragged flag, drop indicator cleanup).
    if (wasDragging) scheduleRender(renderer);
    return;
  }

  // The proposed dates are editable in a confirmation dialog before writing to
  // the database (dates only: the record stays in its own group).
  const { dateStart: ds, dateEnd: de, resModel } = renderer.model.metaData;

  const fmt = (d, hasTime) => {
    const y = hasTime ? d.getUTCFullYear() : d.getFullYear();
    const m = String(hasTime ? d.getUTCMonth() + 1 : d.getMonth() + 1).padStart(
      2,
      "0",
    );
    const day = String(hasTime ? d.getUTCDate() : d.getDate()).padStart(2, "0");
    if (!hasTime) return `${y}-${m}-${day}`;
    const h = String(hasTime ? d.getUTCHours() : d.getHours()).padStart(2, "0");
    const min = String(hasTime ? d.getUTCMinutes() : d.getMinutes()).padStart(
      2,
      "0",
    );
    const s = String(hasTime ? d.getUTCSeconds() : d.getSeconds()).padStart(
      2,
      "0",
    );
    return `${y}-${m}-${day} ${h}:${min}:${s}`;
  };

  const buildWriteValues = (start, end) => {
    const wv = {};
    if (!dsReadonly) wv[ds] = fmt(start, record.startHasTime);
    if (!deReadonly) wv[de] = fmt(end, record.endHasTime);
    return wv;
  };

  const buildRevertValues = () => {
    const rv = {};
    if (!dsReadonly) rv[ds] = fmt(new Date(originalStart), record.startHasTime);
    if (!deReadonly) rv[de] = fmt(new Date(originalEnd), record.endHasTime);
    return rv;
  };

  // Visual revert used when the user cancels the confirmation dialog.
  const revertPosition = () => {
    updateBarPosition(
      renderer,
      record,
      new Date(originalStart),
      new Date(originalEnd),
    );
    scheduleRender(renderer);
  };

  // Confirmation dialog: the proposed new date(s) are shown in editable date
  // pickers. The write to the database happens only after the user confirms.
  renderer.dialogService.add(DragConfirmDialog, {
    mode: dragMode,
    taskName: record.name || "",
    origStartDate: new Date(originalStart),
    origEndDate: new Date(originalEnd),
    newStartDate: new Date(newStart),
    newEndDate: new Date(newEnd),
    confirm: async (editedStart, editedEnd) => {
      const finalStart = editedStart || newStart;
      const finalEnd = editedEnd || newEnd;
      const writeValues = buildWriteValues(finalStart, finalEnd);

      if (renderer._pendingNotification) {
        renderer._pendingNotification();
        renderer._pendingNotification = null;
      }

      try {
        await renderer.orm.write(resModel, [record.id], writeValues);
        // The dropped taskbar keeps its own row: rows are persisted, so a
        // drag left/right (dates change) or a resize never changes its row.
        await renderer.model.load({
          ...renderer.model.searchParams,
          offset: renderer.model.offset,
          limit: renderer.model.limit,
        });
        renderer.highlightRecord(record.id, `${record.name} ${_t("moved")}`);

        // Only after the change has been applied successfully do we offer the undo
        // button, so "Tasks rescheduled" (and its undo) reflects a real saved change.
        let closeNotif;
        closeNotif = renderer.notificationService.add("", {
          title: `${record.name} ${_t("rescheduled")}`,
          type: "success",
          sticky: true,
          buttons: [
            {
              name: _t("undo"),
              icon: "fa-undo",
              primary: false,
              onClick: async () => {
                closeNotif();
                renderer._pendingNotification = null;
                try {
                  await renderer.orm.write(
                    resModel,
                    [record.id],
                    buildRevertValues(),
                  );
                  await renderer.model.load({
                    ...renderer.model.searchParams,
                    offset: renderer.model.offset,
                    limit: renderer.model.limit,
                  });
                  updateBarPosition(
                    renderer,
                    record,
                    new Date(originalStart),
                    new Date(originalEnd),
                  );
                  scheduleRender(renderer);
                } catch (error) {
                  renderer.notificationService.add(extractErrorMessage(error), {
                    title: _t("Failed to revert changes "),
                    type: "danger",
                  });
                }
              },
            },
          ],
        });
        renderer._pendingNotification = closeNotif;
      } catch (error) {
        updateBarPosition(
          renderer,
          record,
          new Date(originalStart),
          new Date(originalEnd),
        );
        scheduleRender(renderer);
        renderer.notificationService.add(extractErrorMessage(error), {
          title: _t("Failed to save changes: "),
          type: "danger",
        });
      }
    },
    cancel: () => {
      revertPosition();
    },
  });
}
