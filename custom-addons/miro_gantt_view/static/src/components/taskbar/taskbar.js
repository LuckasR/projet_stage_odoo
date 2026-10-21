/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { extractErrorMessage } from "@miro_gantt_view/utils/error_message";
import { renderColumnHeader } from "@miro_gantt_view/components/header/header";
import { deleteTaskBar, openFormView } from "@miro_gantt_view/model/records"
import {
  renderHeaderSidebar,
  _startSidebarResize,
} from "@miro_gantt_view/components/sidebar/sidebar";
import { buildSidebarCols, NAME_PANEL_WIDTH, SIDEBAR_MAX_WIDTH } from "@miro_gantt_view/utils/config";
import { renderRowHeaders, renderGanttColumns } from "@miro_gantt_view/components/taskbar/taskbar_rendering"
import { attachHorizontalRowVisibility } from "@miro_gantt_view/components/taskbar/taskbar_visibility"
/**
 * Main Gantt rendering function (CSS Grid layout).
 * Rebuilds the entire Gantt DOM tree: column headers, row headers (sidebar),
 * date grid, task bars (pills), group rows, and today line.
 * Preserves scroll position during re-render for smooth updates.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
export function renderGantt(renderer){
  const scrollBody = renderer.scrollArea.el;
  if (!scrollBody) return;
  try {
    const container = renderer.rootRef.el;
    // Save and restore scroll position to avoid jumping during re-render
    const savedScrollTop = scrollBody.scrollTop;
    const savedScrollLeft = scrollBody.scrollLeft;
    scrollBody.innerHTML = "";

    // Responsive sidebar
    // Sidebar width = base width (NAME_PANEL_WIDTH) + the real width of each
    // enabled info column (dynamic `sidebar_column_fields` or the historical
    // fixed ones), clamped to the drag maximum. The user's manual drag width
    // always wins over the auto-calculated one.
    const autoTarget = Math.min(
      SIDEBAR_MAX_WIDTH,
      NAME_PANEL_WIDTH +
        buildSidebarCols(renderer)
          .filter((c) => c.key !== "name")
          .reduce((sum, c) => sum + c.width, 0),
    );
    renderer.state.sidebarWidth = Math.max(
      autoTarget,
      renderer._manualSidebarWidth || 0,
    );
    const sidebarWidth = renderer.state.sidebarVisible
      ? renderer.state.sidebarWidth || NAME_PANEL_WIDTH
      : 0;

    // The layout always fills 100% of the container and stays responsive: the
    // CSS Grid columns are `1fr` tracks that squeeze to the available width,
    // so no horizontal overflow is ever forced (scrollBody.overflowX stays
    // hidden — the dedicated bottom scrollbar strip remains the only
    // horizontal scrubber, shown only when the columns overflow).
    const fitToContainer = true;
    const minBodyWidth = scrollBody.clientWidth;
    scrollBody.style.overflowX = "hidden";

    // Store the real rendered column width. The CSS Grid columns are `1fr`
    // tracks squeezed to fit the container, so they can be narrower than
    // MIN_COL_WIDTH. This stored value is used by `_clientColWidth` so the
    // drag pixel→date conversion matches the visible grid (fixes drops that
    // landed off the drop indicator at Day/Month zooms).
    const ganttTrackWidth = Math.max(0, minBodyWidth - sidebarWidth);
    renderer._columnWidthPx =
      renderer.totalColumns > 0 ? ganttTrackWidth / renderer.totalColumns : 100;

    // Set CSS custom properties on the container for grid layout
    if (container) {
      container.style.setProperty(
        "--Gantt__RowHeader-width",
        sidebarWidth + "px",
      );
      container.style.setProperty(
        "--Gantt__Template-columns",
        renderer.totalColumns,
      );
    }

    // Render loading / error / empty states (when no rows are displayed yet)
    const hasRows =
      renderer._fullRowLayout && renderer._fullRowLayout.length > 0;
    if (!hasRows) {
      if (renderer.model && renderer.model.loadError) {
        const errorBox = document.createElement("div");
        errorBox.className = "o_gantt_view_error";
        const icon = document.createElement("i");
        icon.className = "fa fa-exclamation-triangle o_gantt_view_error_icon";
        const text = document.createElement("span");
        text.textContent = extractErrorMessage(
          renderer.model.loadError,
          _t("Failed to load gantt data."),
        );
        errorBox.append(icon, text);
        scrollBody.appendChild(errorBox);
        return;
      }
      if (renderer.model && renderer.model.loading) {
        const loading = document.createElement("div");
        loading.className =
          "o_gantt_view_loading p-3 text-muted d-flex align-items-center gap-2";
        loading.innerHTML =
          '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i>';
        loading.appendChild(
          document.createTextNode(" " + _t("Loading...")),
        );
        scrollBody.appendChild(loading);
        return;
      }

      const inner = document.createElement("div");
      inner.className = "o_gantt_view_body";
      inner.style.display = "grid";
      inner.style.gridTemplateColumns = `${sidebarWidth}px 1fr`;
      inner.style.width = "100%";
      inner.style.minWidth = minBodyWidth + "px";

      const columnHeader = renderColumnHeader(renderer);
      columnHeader.style.gridColumn = "2";
      columnHeader.style.gridRow = "1";
      inner.appendChild(columnHeader);

      if (renderer.state.sidebarVisible) {
        const sidebarHeader = renderHeaderSidebar(renderer);
        if (sidebarHeader) {
          sidebarHeader.style.gridColumn = "1";
          sidebarHeader.style.gridRow = "1";
          inner.appendChild(sidebarHeader);
        }
      }

      scrollBody.appendChild(inner);
    } else {
      const inner = document.createElement("div");
      inner.className = "o_gantt_view_body";
      // CSS Grid: sidebar (first track) + grid area (second track), implicit rows (auto height)
      inner.style.display = "grid";
      inner.style.gridTemplateColumns = `${sidebarWidth}px 1fr`;
      inner.style.width = "100%";
      inner.style.minWidth = minBodyWidth + "px";

      // Render column header in the second grid track (so its column widths match the date grid/pills)
      const columnHeader = renderColumnHeader(renderer);
      columnHeader.style.gridColumn = "2";
      columnHeader.style.gridRow = "1";
      inner.appendChild(columnHeader);

      // Render sidebar header (sticky left, aligned with column header) — first grid track, same row as column header
      let sidebarHeader = null;
      if (renderer.state.sidebarVisible) {
        sidebarHeader = renderHeaderSidebar(renderer);
        if (sidebarHeader) {
          sidebarHeader.style.gridColumn = "1";
          sidebarHeader.style.gridRow = "1";
          inner.appendChild(sidebarHeader);
        }
      }

      // Render sidebar (row headers) — first grid track, second grid row
      if (renderer.state.sidebarVisible) {
        const rowHeaders = renderRowHeaders(renderer);
        if (rowHeaders) {
          rowHeaders.style.gridColumn = "1";
          rowHeaders.style.gridRow = "2";
          inner.appendChild(rowHeaders);
          // Keep the sidebar header labels aligned with the rows when the
          // panel is too narrow (manual drag) and its columns scroll.
          if (sidebarHeader) {
            rowHeaders.addEventListener("scroll", () => {
              sidebarHeader.scrollLeft = rowHeaders.scrollLeft;
            });
          }
          // Resize handle on the border between sidebar and grid
          const resizeHandle = document.createElement("div");
          resizeHandle.className = "o_gantt_view_sidebar_resize";
          resizeHandle.style.gridColumn = "1";
          resizeHandle.style.gridRow = "2";
          resizeHandle.style.justifySelf = "end";
          resizeHandle.style.position = "sticky";
          resizeHandle.style.left = "0";
          // Above the sidebar (row headers, z-index 21) so the 1px handle
          // stays clickable on top of it.
          resizeHandle.style.zIndex = "22";
          resizeHandle.addEventListener("mousedown", (ev) =>
            _startSidebarResize(renderer, ev),
          );
          inner.appendChild(resizeHandle);
        }
      }

      // Render the Gantt columns (date grid + task rows) — second grid track, second grid row
      const ganttColumns = renderGanttColumns(renderer);
      ganttColumns.style.gridColumn = renderer.state.sidebarVisible
        ? "2"
        : "1 / -1";
      ganttColumns.style.gridRow = "2";
      inner.appendChild(ganttColumns);
      scrollBody.appendChild(inner);
    }

    // Restore scroll position
    scrollBody.scrollTop = savedScrollTop;
    scrollBody.scrollLeft = savedScrollLeft;
    renderer._scrollArea = scrollBody;
    // Hide task rows whose taskbars are all outside the visible layout
    attachHorizontalRowVisibility(renderer);
  } catch (error) {
    console.error("Failed to render gantt:", error);
    const errDiv = document.createElement("div");
    errDiv.className = "o_gantt_view_error";
    const errIcon = document.createElement("i");
    errIcon.className = "fa fa-exclamation-triangle o_gantt_view_error_icon";
    const errText = document.createElement("span");
    errText.textContent = _t(
      "Failed to render gantt chart. Please try refreshing.",
    );
    errDiv.append(errIcon, errText);
    scrollBody.textContent = "";
    scrollBody.appendChild(errDiv);
  }
}

/**
 * Handles a click on a task bar (pill) by opening the popover with task details.
 * The position (right) and the popoverClass (o_cw_popover) are set via
 * renderer._popoverOptions (calendar style).
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {MouseEvent} ev - The click event
 * @param {Object} record - The clicked task record
 */
export function onBarClick(renderer, ev, record) {
  renderer.popover.open(ev.currentTarget, {
    record,
    model: renderer.model,
    close: () => renderer.popover.close(),
    editRecord: renderer.model.metaData.canEdit ? (rec) => openFormView(renderer, rec) : undefined,
    openFullFormRecord: renderer.model.metaData.canEdit ? (rec) => openFormView(renderer, rec, 'current') : undefined,
    deleteRecord: renderer.model.metaData.canDelete ? (rec) => deleteTaskBar(renderer, rec) : undefined,
  });
}


