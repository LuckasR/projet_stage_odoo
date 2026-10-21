/** @odoo-module **/
import { renderToElement } from "@web/core/utils/render";
import { buildColumnData } from "@miro_gantt_view/utils/grid";
import {
  NAME_PANEL_WIDTH,
  buildSidebarCols,
  sidebarColsCss,
} from "@miro_gantt_view/utils/config";

// ==============================================================================
// Event attachment helpers: attach interactive behavior after template rendering.
// ==============================================================================

/**
 * Attaches click events to interactive elements in the header (title click for sort,
 * sort icon buttons).
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Element} headerEl - The rendered header element
 */
export function attachHeaderEvents(renderer, headerEl) {
  const titleEl = headerEl.querySelector(
    ".o_gantt_view_header_title_clickable",
  );
  if (titleEl)
    titleEl.addEventListener("click", () => renderer._onGroupSortClick());

  // Sidebar fields toggle menu: fully manual (open/close AND item clicks),
  // because (1) this header is rendered imperatively via renderToElement, so
  // there is no Owl Dropdown component / onSelected available here, and
  // (2) Bootstrap's own data-bs-toggle="dropdown" positions its menu with
  // `position: absolute` in normal flow, which gets clipped by
  // `.o_gantt_view_header_sidebar`'s `overflow: hidden`. We reuse Bootstrap's
  // `.dropdown-menu` / `.show` CSS classes for styling only, but compute a
  // `position: fixed` placement ourselves so the menu escapes that clipping.
  const toggleBtn = headerEl.querySelector(
    ".o_gantt_view_sidebar_fields_toggle_btn",
  );
  const menuEl = headerEl.querySelector(".o_gantt_view_sidebar_fields_menu");
  if (toggleBtn && menuEl) {
    const closeMenu = () => {
      menuEl.classList.remove("show");
      if (menuEl._outsideClickHandler) {
        document.removeEventListener(
          "click",
          menuEl._outsideClickHandler,
          true,
        );
        menuEl._outsideClickHandler = null;
      }
    };
    const openMenu = () => {
      const rect = toggleBtn.getBoundingClientRect();
      menuEl.style.position = "fixed";
      menuEl.style.top = `${rect.bottom + 2}px`;
      menuEl.style.left = "auto";
      menuEl.style.right = `${Math.max(0, window.innerWidth - rect.right)}px`;
      menuEl.classList.add("show");
      menuEl._outsideClickHandler = (ev) => {
        if (!menuEl.contains(ev.target) && ev.target !== toggleBtn) {
          closeMenu();
        }
      };
      document.addEventListener("click", menuEl._outsideClickHandler, true);
    };
    toggleBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (menuEl.classList.contains("show")) closeMenu();
      else openMenu();
    });
    for (const itemEl of menuEl.querySelectorAll(
      ".o_gantt_view_sidebar_field_item",
    )) {
      itemEl.addEventListener("click", (ev) => {
        ev.preventDefault();
        closeMenu();
        // Triggers renderer.renderGantt(), which replaces this whole header
        // element with a fresh one (menu naturally starts closed again).
        renderer._toggleSidebarField(itemEl.dataset.field);
      });
    }
  }
}

/**
 * Computes header group data for the major header row (month/year labels spanning columns).
 * Each group represents a contiguous set of columns with the same major label.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object[]} Array of { key, label, start, count, gridStart }
 */
function buildHeaderGroups(renderer) {
  const zoom = renderer.state.zoom;
  const total = renderer.totalColumns;
  const { start } = renderer.dateRange;
  const base = new Date(start);
  // Year zoom in "year columns" mode (one column per year, used for ranges
  // wider than 4 years): the major header groups
  // consecutive year-columns by decade ("2021 - 2030", "2031 - 2040", ...,
  // windows aligned on years ending in 1).
  if (zoom === "year" && renderer.zoomCfg.colUnit === "year") {
    const groups = [];
    let currentKey = null;
    let currentStart = 0;
    for (let i = 0; i < total; i++) {
      const y = base.getFullYear() + i;
      const key = y - ((y + 9) % 10);
      if (key !== currentKey) {
        if (currentKey !== null) {
          groups.push({
            key: `${currentKey}`,
            label: `${currentKey} - ${currentKey + 9}`,
            start: currentStart,
            count: i - currentStart,
            gridStart: currentStart + 1,
          });
        }
        currentKey = key;
        currentStart = i;
      }
    }
    if (currentKey !== null) {
      groups.push({
        key: `${currentKey}`,
        label: `${currentKey} - ${currentKey + 9}`,
        start: currentStart,
        count: total - currentStart,
        gridStart: currentStart + 1,
      });
    }
    return groups;
  }
  // Year zoom in "month columns" mode: group the major header by calendar
  // year. A 12-month range (Jan → Dec) yields a single "2026" group; a range
  // crossing several years (e.g. a custom range longer than 12 months)
  // yields one group per year ("2026", "2027", ...).
  if (zoom === "year" && renderer.zoomCfg.colUnit === "month") {
    const groups = [];
    let currentKey = null;
    let currentStart = 0;
    let count = 0;
    for (let i = 0; i < total; i++) {
      const d = new Date(base);
      d.setMonth(base.getMonth() + i);
      const key = d.getFullYear();
      if (key !== currentKey) {
        if (currentKey !== null) {
          groups.push({
            key: `${currentKey}`,
            label: `${currentKey}`,
            start: currentStart,
            count,
            gridStart: currentStart + 1,
          });
        }
        currentKey = key;
        currentStart = i;
        count = 1;
      } else {
        count++;
      }
    }
    if (currentKey !== null) {
      groups.push({
        key: `${currentKey}`,
        label: `${currentKey}`,
        start: currentStart,
        count,
        gridStart: currentStart + 1,
      });
    }
    return groups;
  }
  const dates = [];
  for (let i = 0; i < total; i++) {
    let d;
    if (zoom === "day") d = new Date(+base + i * 3600000);
    else if (zoom === "week" || zoom === "month" || zoom === "year") {
      d = new Date(base);
      d.setDate(base.getDate() + i);
    } else {
      d = new Date(base);
      d.setDate(base.getDate() + i);
    }
    dates.push(d);
  }
  let getKey, getLabel;
  if (zoom === "day") {
    getKey = (d) => d.toDateString();
    getLabel = (d) =>
      // "Tuesday, 01 September 2026" - padded day, no comma before the month.
      `${d.toLocaleDateString(undefined, { weekday: "long" })}, ${String(d.getDate()).padStart(2, "0")} ${d.toLocaleDateString(undefined, { month: "long" })} ${d.getFullYear()}`;
  } else if (zoom === "week" || zoom === "month" || zoom === "year") {
    getKey = (d) => `${d.getFullYear()}-${d.getMonth()}`;
    getLabel = (d) =>
      d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  } else {
    getKey = (d) => d.toDateString();
    getLabel = (d) =>
      d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
  }
  const groups = [];
  let currentKey = null,
    currentLabel = null,
    currentStart = 0,
    count = 0;
  for (let i = 0; i < dates.length; i++) {
    const key = getKey(dates[i]);
    const label = getLabel(dates[i]);
    if (key !== currentKey) {
      if (currentKey !== null)
        groups.push({
          key: currentKey,
          label: currentLabel,
          start: currentStart,
          count,
          gridStart: currentStart + 1,
        });
      currentKey = key;
      currentLabel = label;
      currentStart = i;
      count = 1;
    } else count++;
  }
  if (currentKey !== null)
    groups.push({
      key: currentKey,
      label: currentLabel,
      start: currentStart,
      count,
      gridStart: currentStart + 1,
    });
  return groups;
}

/**
 * Builds the data object for the GanttHeader template.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Object} Header template data
 */
export function buildHeaderData(renderer) {
  return {
    sidebarVisible: renderer.state.sidebarVisible,
    sidebarWidth: renderer.state.sidebarVisible
      ? renderer.state.sidebarWidth || NAME_PANEL_WIDTH
      : 0,
    totalColumns: renderer.totalColumns,
    defaultTitle: renderer.model.metaData.defaultTitle || "",
    sortOrder: renderer.state.sortOrder || "",
    sidebarCols: buildSidebarCols(renderer),
    colsCss: sidebarColsCss(buildSidebarCols(renderer)),
    headerGroups: buildHeaderGroups(renderer),
    columns: buildColumnData(renderer),
    // Sidebar fields toggle dropdown (now rendered under the sidebar column
    // headers instead of the top toolbar, see attachHeaderEvents below).
    sidebarToggleFields: renderer._sidebarToggleFields,
    sidebarFieldsState: renderer.state.sidebarFields || {},
    sidebarToggleFieldsTitle: renderer._titleSidebarFields,
  };
}

/**
 * Renders the column header area via the GanttHeader template (CSS Grid layout).
 * Events are attached after rendering via attachHeaderEvents.
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {Element} The column header DOM element
 */
export function renderColumnHeader(renderer) {
  return renderToElement("gantt_view.Header", buildHeaderData(renderer));
}
