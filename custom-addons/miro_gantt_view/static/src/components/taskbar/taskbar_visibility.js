/** @odoo-module **/
import { NAME_PANEL_WIDTH} from "@miro_gantt_view/utils/config";


/**
 * Hides a band row (and its matching sidebar row) entirely when none of its
 * taskbars are "on the layout": either the record lies outside the visible
 * date range (out-of-range pills, e.g. after navigating with the < / > buttons)
 * or the pill is outside the horizontally visible area of the scroll body.
 * Runs on scroll (throttled via rAF) and once after each renderGantt(). Rows
 * are hidden with `visibility: hidden` (not display:none) so the grid tracks
 * and sidebar alignment are preserved while scrolled. Group rows and empty
 * (drag-to-create) rows are never hidden.
 *
 * The year zoom (desktop) is excluded: it scrolls horizontally by design but
 * is expected to keep every group's band visible, exactly like the other
 * desktop zooms. Hiding the bands there would show group headers whose
 * taskbars have simply scrolled out of the viewport, i.e. apparent empty
 * groups while vertical-scrolling through the year.
 * @param {Object} renderer - The GanttRenderer instance
 */
function applyRowVisibility(renderer) {
  const scrollBody = renderer.scrollArea.el;
  if (!scrollBody) return;
  const isMobile = typeof window !== "undefined" && window.innerWidth < 768;
  // Only the year zoom's "day columns" mode (scrollable) keeps every band
  // visible: the exception does not apply to the "month columns" mode, which
  // behaves like the other desktop zooms.
  const isYearDayColumns =
    renderer.state.zoom === "year" && renderer.zoomCfg.colUnit === "day";
  if (isYearDayColumns && !isMobile) return;
  const viewport = scrollBody.getBoundingClientRect();
  // The sticky sidebar covers the left part of the scroll viewport, so a pill
  // is only "on the layout" when it starts past the sidebar's right edge.
  const sidebarWidth = renderer.state.sidebarVisible
    ? renderer.state.sidebarWidth || NAME_PANEL_WIDTH
    : 0;
  const visibleLeft = viewport.left + sidebarWidth;
  const rows = scrollBody.querySelectorAll(
    ".o_gantt_view_task_row:not(.o_gantt_view_empty_row)",
  );
  for (const row of rows) {
    // Out-of-range pills (taskbars whose dates lie outside the visible range,
    // e.g. after navigating with the < / > buttons) do not count as visible.
    const pills = row.querySelectorAll(
      ".o_gantt_view_pill_wrapper:not(.o_gantt_view_pill_offscreen)",
    );
    let visible = false;
    for (const pill of pills) {
      const rect = pill.getBoundingClientRect();
      if (
        rect.width > 0 &&
        rect.right > visibleLeft &&
        rect.left < viewport.right
      ) {
        visible = true;
        break;
      }
    }
    row.classList.toggle("o_gantt_view_row_hidden", !visible);
    const ids = row.dataset.recordIds;
    if (ids) {
      const sidebarRow = scrollBody.querySelector(
        '.o_gantt_view_row_sidebar[data-record-ids="' + ids + '"]',
      );
      if (sidebarRow) {
        sidebarRow.classList.toggle("o_gantt_view_row_hidden", !visible);
      }
    }
  }
}

/**
 * Binds the scroll handler that keeps task rows hidden while their taskbars
 * are outside the visible layout. Bound once (the scroll area persists across
 * renders); the visibility state is re-applied on every call.
 * @param {Object} renderer - The GanttRenderer instance
 */
function attachHorizontalRowVisibility(renderer) {
  const scrollBody = renderer.scrollArea.el;
  if (!scrollBody) return;
  if (!renderer._rowVisibilityBound) {
    renderer._rowVisibilityBound = true;
    let rafId = null;
    const onScroll = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        applyRowVisibility(renderer);
      });
    };
    scrollBody.addEventListener("scroll", onScroll, { passive: true });
    renderer._unbindRowVisibility = () => {
      scrollBody.removeEventListener("scroll", onScroll);
      renderer._rowVisibilityBound = false;
    };
  }
  applyRowVisibility(renderer);
}

export { applyRowVisibility, attachHorizontalRowVisibility }
