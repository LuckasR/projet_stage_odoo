/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { formatDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";

// Luxon is exposed globally by the web bundle (same usage as @web/core/l10n/dates).
const { DateTime } = luxon;

/**
 * Totals row popover: on click on a column of the line chart, lists the tasks
 * covering that column in a READ-ONLY way, grouped like the sidebar (group by):
 * one collapsible header per group (icon + name + counter), then the group's
 * tasks (name + start/end dates). No detail navigation: simple consultation,
 * with an internal scroll when the list exceeds the max height.
 *
 * Wrapped in `o_cw_popover` (calendar-style header + scrollable body), like
 * the other popovers of the view.
 *
 * @extends Component
 * @property {{key: string, name: string, tasks: Object[]}[]} props.groups
 *   Groups (as in the sidebar) holding the records covering the clicked column
 */
export class ChartPopover extends Component {
  static template = "total_rows.ChartPopover";
  static props = {
    close: Function, // Function to close the popover, injected by usePopover
    groups: { type: Array, optional: true },
    defaultTitle: { type: String, optional: true },
    columnDate: { type: Date, optional: true },
    zoom: { type: String, optional: true },
  };

  setup() {
    // Collapsed state is local to this popover (it does not affect the main
    // sidebar). Groups start collapsed, the user expands them on demand.
    this.state = useState({ collapsed: {} });
  }

  get _groups() {
    return this.props.groups || [];
  }

  // Counts tasks recursively: parent groups (isParent) sum their sub-groups,
  // leaf groups carry their own tasks.
  _countGroupTasks(group) {
    if (group.isParent) {
      return (group.children || []).reduce(
        (acc, c) => acc + this._countGroupTasks(c),
        0,
      );
    }
    return group.tasks?.length || 0;
  }

  get _totalCount() {
    return this._groups.reduce((acc, g) => acc + this._countGroupTasks(g), 0);
  }

  // Flat list in DFS order (like the sidebar), recursively hiding the
  // descendants of a collapsed parent group: only the parent header stays
  // visible while its sub-groups/tasks are hidden.
  get _visibleGroups() {
    const visible = [];
    const walk = (groups, ancestorCollapsed) => {
      for (const group of groups) {
        if (ancestorCollapsed) continue;
        visible.push(group);
        if (group.isParent && group.children) {
          walk(group.children, this._isCollapsed(group.key));
        }
      }
    };
    walk(this._groups, false);
    return visible;
  }

  get _defaultTitle() {
    const n = this._totalCount;
    const title = this.props.defaultTitle || _t("Task");
    return n === 1 ? _t("1 %s", title) : _t("%s %ss", String(n), title);
  }

  get _emptyLabel() {
    const title = this.props.defaultTitle || _t("tasks");
    return _t("No %s", title);
  }

  // Date of the clicked column (totals row), displayed after the title —
  // e.g. "05/09/2026". Empty when the popover is opened without a date.
  // Date of the clicked column (totals row), displayed after the title,
  // formatted according to the column's unit for the current zoom level:
  // - day / week / month / year (col = day) -> "01/09/2026"
  // Empty when the popover is opened without a date.
  get _columnDateLabel() {
    const d = this.props.columnDate;
    if (!d) return "";
    const dt = DateTime.fromJSDate(d);
    if (this.props.zoom === "day") {
      return formatDate(dt, { format: "dd/MM/yyyy HH:mm" });
    }
    return formatDate(dt, { format: "dd/MM/yyyy" });
  }

  _isCollapsed(groupKey) {
    return !this.state.collapsed[groupKey];
  }

  _toggleGroup(groupKey) {
    this.state.collapsed[groupKey] = !this.state.collapsed[groupKey];
  }
}
