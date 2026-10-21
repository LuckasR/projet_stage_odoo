/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { getDateGridBounds } from "@miro_gantt_view/utils/position_compute";
import { buildColumnData } from "@miro_gantt_view/utils/grid";
import {
  TOTALS_BAR_COLOR_LOW,
  TOTALS_BAR_COLOR_MID,
  TOTALS_BAR_COLOR_ZOOMS,
} from "@miro_gantt_view/utils/config";

/**
 * Computes, for each visible time column, the number of task bars overlapping
 * it. Unlike the per-group consolidation row, this count is GLOBAL: it covers
 * every task currently loaded in the model (renderer.records), regardless of
 * rows/groups.
 *
 * Each task covers the columns between its start and end columns inclusive
 * (same logic as getDateGridBounds). Tasks entirely outside the visible range
 * are ignored; those spilling over the left/right edges are clamped to the
 * grid bounds.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @returns {{ counts: number[], tasks: Object[][] }} `counts[i]` = number of
 *   tasks covering column i; `tasks[i]` = the records (model order) covering
 *   this column, for the click popover.
 */
export function computeGlobalColumnTotals(renderer) {
  const total = renderer.totalColumns;
  const counts = new Array(total).fill(0);
  const tasks = Array.from({ length: total }, () => []);
  const { start } = renderer.dateRange;
  const colUnit = renderer.zoomCfg.colUnit;
  for (const record of renderer.records || []) {
    if (!record.start || !record.end) continue;
    const { colStart, colSpan, outOfRange } = getDateGridBounds(
      record,
      total,
      start,
      colUnit,
    );
    if (outOfRange || colSpan <= 0) continue;
    const first = Math.max(0, colStart - 1);
    const last = Math.min(total - 1, first + colSpan - 1);
    for (let i = first; i <= last; i++) {
      counts[i]++;
      tasks[i].push(record);
    }
  }
  return { counts, tasks };
}

/**
 * Recursively walks the model's nested group tree and builds a hierarchical
 * list of groups for the totals popover. Only groups that contain at least
 * one of the given tasks are included (pruned). Parent groups carry only a
 * count (sum of descendants); leaf groups carry the matching task records.
 *
 * The result mirrors the sidebar's group-by hierarchy: if the sidebar uses
 * `project > assigned_by`, the popover will show project groups containing
 * assigned_by sub-groups, preserving the same order and nesting.
 *
 * @param {Object[]} groups - `renderer.model.groups` (nested tree)
 * @param {Set<number>} taskIdSet - Set of record IDs to match against
 * @param {number} [depth=0] - Current nesting depth (internal)
 * @returns {{key: string, name: string, depth: number, isParent: boolean,
 *            children?: Array, tasks?: Object[], count: number}[]}
 */
function buildPopoverGroupTree(groups, taskIdSet, depth = 0) {
  const result = [];
  for (const group of groups || []) {
    if (group.isParent && group.children) {
      const children = buildPopoverGroupTree(
        group.children,
        taskIdSet,
        depth + 1,
      );
      if (children.length > 0) {
        const totalTasks = children.reduce((sum, c) => sum + c.count, 0);
        result.push({
          key: group.path,
          name: group.name,
          depth,
          isParent: true,
          children,
          count: totalTasks,
        });
      }
    } else {
      const matchingTasks = (group.records || []).filter((r) =>
        taskIdSet.has(r.id),
      );
      if (matchingTasks.length > 0) {
        result.push({
          key: group.path,
          name: group.name,
          depth,
          isParent: false,
          tasks: matchingTasks,
          count: matchingTasks.length,
        });
      }
    }
  }
  return result;
}

/**
 * Buckets a flat list of tasks (as gathered per column by
 * `computeGlobalColumnTotals`) into the same hierarchical groups shown in the
 * sidebar. Preserves each group's first-seen order and nesting depth.
 *
 * When no group-by is configured (ungrouped mode), all tasks are placed under
 * a single "Without group" entry.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object[]} tasks - Records to bucket (one column's worth)
 * @returns {{key: string, name: string, depth: number, isParent: boolean,
 *            children?: Array, tasks?: Object[], count: number}[]}
 */
export function groupTasksForPopover(renderer, tasks) {
  const taskIdSet = new Set(tasks.map((t) => t.id));
  const groups = renderer.model?.groups;
  if (!groups || groups.length === 0) {
    return [
      {
        key: "__none__",
        name: _t("Without group"),
        depth: 0,
        isParent: false,
        tasks,
        count: tasks.length,
      },
    ];
  }
  return buildPopoverGroupTree(groups, taskIdSet);
}

/**
 * Returns stroke and fill colors for the bar chart based on the zoom level
 * and the peak column count.  Week/month zooms use intensity-dependent shades;
 * all other zooms use the standard brand blue.
 * @param {string} zoom - Current zoom level ID
 * @param {number} maxCount - Highest task count across all visible columns
 * @returns {{ stroke: string, fill: string }} CSS color strings
 */
function _getBarColor(zoom, maxCount) {
  if (TOTALS_BAR_COLOR_ZOOMS.has(zoom)) {
    if (maxCount <= TOTALS_BAR_COLOR_LOW) {
      return {
        stroke: "hsl(214, 40%, 76%)",
        fill: "hsla(214, 40%, 76%, 0.18)",
      };
    }
    if (maxCount <= TOTALS_BAR_COLOR_MID) {
      return {
        stroke: "hsl(215, 74%, 70%)",
        fill: "hsla(215, 74%, 70%, 0.18)",
      };
    }
    return { stroke: "hsl(215, 73%, 44%)", fill: "hsla(215, 73%, 44%, 0.18)" };
  }
  return { stroke: "#1a73e8", fill: "rgba(26,115,232,0.15)" };
}

/**
 * Renders the totals row as a Chart.js bar chart. One bar per visible column;
 * clicking a column (or a bar) opens the task-list popover (same behaviour as
 * the former line chart). A dashed vertical line marks today's column.
 *
 * Chart.js v4 is bundled by this module: `web/static/lib/Chart/Chart.js` is
 * declared first in our `web.assets_backend` assets (`__manifest__.py`), so
 * the constructor is available globally as `window.Chart`. This avoids the
 * isolated `web.chartjs_lib` bundle, which fails to serve on some servers
 * (GET /web/assets/debug/web.chartjs_lib.js -> 500). No runtime loading.
 *
 * @param {Object} renderer - The GanttRenderer instance
 */
export function renderTotalsRow(renderer) {
  const scrollEl = renderer.totalsRowScroll?.el;
  if (!scrollEl) return;
  if (renderer.ChartPopover?.isOpen) renderer.ChartPopover.close();

  const { counts, tasks } = computeGlobalColumnTotals(renderer);
  renderer._totalsColumnTasks = tasks;

  const total = renderer.totalColumns;
  const max = counts.reduce((acc, c) => Math.max(acc, c), 0);
  const maxCount = Math.max(max, 1);

  let colWidth = renderer._columnWidthPx;
  if (!colWidth) {
    const body = renderer.scrollArea?.el;
    const sidebar = renderer.state.sidebarVisible
      ? renderer.state.sidebarWidth || 0
      : 0;
    colWidth = body ? Math.max(1, (body.clientWidth - sidebar) / total) : 60;
  }

  const cellsWidth = Math.max(1, colWidth * total);
  const columns = buildColumnData(renderer);
  const taskLabel = renderer.model?.metaData?.defaultTitle || _t("tasks");
  const { stroke, fill } = _getBarColor(renderer.state.zoom, maxCount);
  const todayIdx = columns.findIndex((c) => c.isToday);

  // Chart.js is part of `web.assets_backend` (see docstring); bail out
  // silently if the enclosing page does not provide it.
  if (typeof Chart !== "function") return;

  // Destroy the previous instance (Chart.js observes its container and must
  // be torn down before its canvas is removed from the DOM).
  if (renderer._totalsChart) {
    renderer._totalsChart.destroy();
    renderer._totalsChart = null;
  }

  scrollEl.innerHTML = "";
  const cells = document.createElement("div");
  cells.className = "o_gantt_view_chart_row_cells";
  cells.style.width = `${cellsWidth}px`;
  const canvas = document.createElement("canvas");
  canvas.className = "o_gantt_view_totals_canvas";
  cells.appendChild(canvas);
  scrollEl.appendChild(cells);

  // Category x-axis: bar i is centered on column i (labels are the column
  // indices; the tooltip title is hidden anyway), exactly like the native
  // graph view feeds its datasets.
  const config = {
    type: "bar",
    data: {
      labels: counts.map((_, i) => String(i)),
      datasets: [
        {
          data: counts.slice(),
          backgroundColor: fill,
          borderColor: stroke,
          borderWidth: 1,
          borderRadius: 2,
          maxBarThickness: 26,
          hoverBackgroundColor: stroke,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      onClick: (evt, elements) => {
        const idx = elements.length ? elements[0].index : -1;
        if (idx < 0) return;
        // Anchors the popover on the center of the clicked column.
        const anchor = document.createElement("div");
        anchor.style.position = "absolute";
        anchor.style.top = "0";
        anchor.style.left = `${(idx + 0.5) * colWidth}px`;
        anchor.style.width = "1px";
        anchor.style.height = "1px";
        cells.appendChild(anchor);
        renderer._onTotalsCellClick({ currentTarget: anchor }, idx);
      },
      onHover: (evt, elements) => {
        const idx = elements.length ? elements[0].index : -1;
        canvas.style.cursor =
          idx >= 0 && counts[idx] > 0 ? "pointer" : "default";
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          callbacks: {
            title: () => "",
            label: (ctx) => {
              const value = counts[ctx.dataIndex];
              return value === 1
                ? _t("1 %s", taskLabel)
                : `${value} ${taskLabel}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "category",
          display: false,
          grid: { display: false },
          border: { display: false },
        },
        y: {
          type: "linear",
          display: false,
          grid: { display: false },
          border: { display: false },
          min: 0,
          max: Math.max(1, maxCount * 1.15),
        },
      },
    },
  };

  // Visible column separators, aligned with the layout grid columns: a thin
  // vertical line at each column boundary (the Chart.js x gridlines would be
  // centered on the bars instead, so draw them ourselves).
  config.options.plugins.colLines = {
    id: "colLines",
    beforeDraw: (chart) => {
      const ctx = chart.ctx;
      const { top, bottom } = chart.chartArea;
      ctx.save();
      ctx.strokeStyle = "rgba(0, 0, 0, 0.12)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 1; i < total; i++) {
        const x = i * colWidth;
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
      }
      ctx.stroke();
      ctx.restore();
    },
  };

  // Dashed vertical marker on today's column (drawn under the tooltip),
  // positioned at the actual pixel of today's bar.
  if (todayIdx >= 0) {
    config.options.plugins.todayLine = {
      id: "todayLine",
      beforeDraw: (chart) => {
        const bar = chart.getDatasetMeta(0).data[todayIdx];
        if (!bar) return;
        const ctx = chart.ctx;
        const { top, bottom } = chart.chartArea;
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = "#bb8262";
        ctx.lineWidth = 1;
        ctx.moveTo(bar.x, top);
        ctx.lineTo(bar.x, bottom);
        ctx.stroke();
        ctx.restore();
      },
    };
  }

  renderer._totalsChart = new Chart(canvas, config);

  // The cells follow the main body's horizontal scroll position via a
  // translate — the row itself has no scrollbar (see renderer.js 'scroll'
  // handler).
  const body = renderer.scrollArea?.el;
  if (body) cells.style.transform = `translateX(-${body.scrollLeft}px)`;
}
