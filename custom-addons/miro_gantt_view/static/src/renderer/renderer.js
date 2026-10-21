/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { debounce } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { usePopover } from "@web/core/popover/popover_hook";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { DateRangeInput } from "@miro_gantt_view/components/date_range/date_range_input";
import { onDrag, stopDrag } from "@miro_gantt_view/utils/drag_and_drop";
import { GanttViewPopover } from "@miro_gantt_view/components/popover/popover";
import { ChartPopover } from "@miro_gantt_view/components/popover/chart_popover";
import {
  Component,
  useRef,
  useEffect,
  useState,
  onWillUnmount,
} from "@odoo/owl";
import { ViewScaleSelector } from "@web/views/view_components/view_scale_selector";
import {
  ZOOM_CONFIG,
  NAME_PANEL_WIDTH,
  MIN_COL_WIDTH,
  MAX_RANGE_YEARS,
} from "@miro_gantt_view/utils/config";
import { renderGantt as _renderGantt } from "@miro_gantt_view/components/taskbar/taskbar";
import {
  computeDateRange,
  computeTotalColumns,
  getDateColIndex,
  getColumnPosition as utilGetColumnPosition,
  getBarWidth as utilGetBarWidth,
  getDragInterval as utilGetDragInterval,
  getDateGridBounds as utilGetDateGridBounds,
} from "@miro_gantt_view/utils/position_compute";
import {
  evalReadonlyExpr as _evalReadonlyExprFn,
  isFieldReadonlyForRecord as _isFieldReadonlyForRecordFn,
  computeClientColWidth as _computeClientColWidthFn,
  initFocusDate as _initFocusDateFn,
  cleanupRenderer as _cleanupRendererFn,
} from "@miro_gantt_view/renderer/renderer_utils";
import {
  isDragTarget as _isDragTargetFn,
  startDrag as _startDragFn,
  onBarClick as _onBarClickFn,
  dateFromColIndex,
} from "@miro_gantt_view/renderer/renderer_drag";
import {
  updateFeedbackLabel as _updateFeedbackLabelFn,
  removeFeedbackLabel as _removeFeedbackLabelFn,
  highlightRecord as _highlightRecordFn,
  isRecordHighlighted as _isRecordHighlightedFn,
  findBandItemForPath as _findBandItemForPathFn,
  visibleToRealIndex as _visibleToRealIndexFn,
  getRecordGroupKey as _getRecordGroupKeyFn,
  getGroupByPath as _getGroupByPathFn,
} from "@miro_gantt_view/renderer/renderer_dom";
import {
  positionDropIndicator as _positionDropIndicatorFn,
  updateDropIndicator as _updateDropIndicatorFn,
  refreshDropIndicator as _refreshDropIndicatorFn,
  syncDragDropPosition as _syncDragDropPositionFn,
  hideDropIndicator as _hideDropIndicatorFn,
  clearDropIndicator as _clearDropIndicatorFn,
  findGroupWrapperByPath as _findGroupWrapperByPathFn,
  findRootRowsWrapper as _findRootRowsWrapperFn,
  ensureDropCellHighlight,
} from "@miro_gantt_view/renderer/renderer_drop_indicator";
import {
  computeFullLayout as _computeFullLayoutFn,
  inputsSignature as _inputsSignatureFn,
} from "@miro_gantt_view/renderer/renderer_layout";
import {
  computePeriodOptions,
  formatFocusDate,
  scrollByPage as _scrollByPageFn,
  setZoomLevel as _setZoomLevelFn,
  scrollToToday as _scrollToTodayFn,
  getAvailableFilters,
} from "@miro_gantt_view/renderer/renderer_navigation";
import {
  renderTotalsRow,
  groupTasksForPopover,
} from "@miro_gantt_view/utils/chart_row";

export class GanttRenderer extends Component {
  _t(str) {
    try {
      return _t(str);
    } catch {
      return str;
    }
  }
  get _titlePrev() {
    return this.__titlePrev || (this.__titlePrev = _t("Previous"));
  }
  get _titleNext() {
    return this.__titleNext || (this.__titleNext = _t("Next"));
  }
  get _titleToggleSidebar() {
    return (
      this.__titleToggleSidebar ||
      (this.__titleToggleSidebar = _t("Toggle sidebar"))
    );
  }
  get _titleToday() {
    return this.__titleToday_ || (this.__titleToday_ = _t("Today"));
  }
  get _titleSidebarFields() {
    return (
      this.__titleSidebarFields_ ||
      (this.__titleSidebarFields_ = _t("Toggle sidebar fields"))
    );
  }
  get _labelFieldProgress() {
    return (
      this.__labelFieldProgress_ ||
      (this.__labelFieldProgress_ = _t("Progress (%)"))
    );
  }
  get _labelFieldStatus() {
    return (
      this.__labelFieldStatus_ || (this.__labelFieldStatus_ = _t("Status"))
    );
  }
  get _labelFieldStart() {
    return (
      this.__labelFieldStart_ || (this.__labelFieldStart_ = _t("Start date"))
    );
  }
  get _labelFieldEnd() {
    return this.__labelFieldEnd_ || (this.__labelFieldEnd_ = _t("End date"));
  }
  get _labelFieldDuration() {
    return (
      this.__labelFieldDuration_ ||
      (this.__labelFieldDuration_ = _t("Duration"))
    );
  }
  // Fields offered by the sidebar-column Dropdown: the dynamic definitions
  // declared via `sidebar_column_fields` when set, or the historical fixed
  // columns (with translated labels) otherwise.
  get _sidebarToggleFields() {
    const declaredFields = this.model?.metaData?.sidebarColumnFields || [];
    const fieldDefs = this.model?.metaData?.sidebarColumnFieldDefs || [];
    if (declaredFields.length) return fieldDefs;
    return [
      { name: "progress", label: this._labelFieldProgress },
      { name: "status", label: this._labelFieldStatus },
      { name: "start", label: this._labelFieldStart },
      { name: "end", label: this._labelFieldEnd },
      { name: "duration", label: this._labelFieldDuration },
    ];
  }
  get _titleToggleTotals() {
    return (
      this.__titleToggleTotals_ ||
      (this.__titleToggleTotals_ = _t("Toggle totals row"))
    );
  }
  get _titleResetRange() {
    return (
      this.__titleResetRange_ || (this.__titleResetRange_ = _t("Reset range"))
    );
  }
  // get _titleTotalsRowLabel() {
  //   const totalWord = this._t("Total");
  //   const title = this.model.metaData.defaultTitle || "";
  //   const range = this.formattedFocusDate;
  //   let label = totalWord;
  //   if (title) label += ` ${title}`;
  //   return `${label} : ${this._totalsTotalCount}`;
  // }
  get _totalsBands() {
    return (this._rowLayout || []).filter(
      (item) => item && item.type === "band" && !item.empty,
    );
  }
  get _totalsTotalCount() {
    return this._totalsBands.reduce(
      (sum, b) => sum + (b.records || []).length,
      0,
    );
  }

  setup() {
    this.model = this.props.model;
    this.actionService = useService("action");
    this.dialogService = useService("dialog");
    this.notificationService = useService("notification");
    this.orm = useService("orm");
    this._popoverOptions = {
      // 100% native core/popover rendering (bootstrap `.o_popover.popover`
      // wrapper, native arrow + animation) + calendar styling via the
      // global `o_cw_popover` class (448px width, card-header/card-footer,
      // z-index). Position `right` like `useCalendarPopover`, with native
      // auto-flip.
      popoverClass: "o_cw_popover",
      position: "right",
    };
    this.popover = usePopover(GanttViewPopover, this._popoverOptions);
    // Totals row popover: click on the mini bar chart lists the tasks
    // covering that column (READ-ONLY). Same calendar styling
    // (`o_cw_popover`), position `top` (the totals row is anchored at the
    // bottom of the view) + native arrow.
    this.ChartPopover = usePopover(ChartPopover, {
      popoverClass: "o_cw_popover o_gantt_view_chart_popover",
      position: "top",
    });
    // Sidebar columns enabled by default: the fields declared via
    // `sidebar_column_fields` are unchecked by default (only the name column
    // shows; the user enables columns through the toolbar Dropdown), while
    // the historical fixed columns keep their old defaults (only progress
    // shown) when the arch declares none. The FIRST dynamic column
    // (sidebarColumnFieldDefs, i.e. the first `sidebar_column_fields` value
    // after excluding the pinned sidebar_label_field / id) is visible by
    // default, right after the name column.
    const colFields = this.model.metaData?.sidebarColumnFields || [];
    const colFieldDefs = this.model.metaData?.sidebarColumnFieldDefs || [];
    const initialSidebarFields = {};
    if (colFields.length) {
      for (const fname of colFields) initialSidebarFields[fname] = false;
      if (colFieldDefs.length) {
        initialSidebarFields[colFieldDefs[0].name] = true;
      }
    } else {
      initialSidebarFields.start = false;
      initialSidebarFields.end = false;
      initialSidebarFields.duration = false;
      initialSidebarFields.status = false;
      initialSidebarFields.progress = true;
    }
    this.state = useState({
      zoom: this.model.metaData?.defaultFilter || "month",
      refresh: 0,
      sidebarVisible: true,
      sidebarWidth: NAME_PANEL_WIDTH,
      showTotalsRow: false,
      sortOrder: null,
      customStart: null,
      customEnd: null,
      customRange: null,
      customPrevZoom: null,
      sidebarFields: initialSidebarFields,
      ScrollByPageStep: 1,
      yearColumns: "month",
      yearInputWarning: false,
      rangeClipped: false,
    });
    this._focusDate = _initFocusDateFn(this.state.zoom);
    this.state.ScrollByPageStep = this.totalColumns;
    this.rootRef = useRef("root");
    this.scrollArea = useRef("scrollArea");
    this.totalsRow = useRef("totalsRow");
    this.totalsRowScroll = useRef("totalsRowScroll");
    this._dragState = null;
    this._ghostEl = null;
    this._ghostDateLabel = null;
    this._resizeBadgeEl = null;
    this._highlightRecordId = null;
    this._highlightLabel = null;
    this._highlightTimer = null;
    this._feedbackEl = null;
    this._unbindFeedbackScroll = null;
    this._dropCellEl = null;
    this._resizeObserver = null;
    this._renderThrottleRAF = null;
    this._isRendering = false;
    this._fullRowLayout = [];
    this._lastInputsSignature = null;
    this._onDrag = (ev) => onDrag(this, ev);
    this._stopDrag = () => stopDrag(this);
    onWillUnmount(() => _cleanupRendererFn(this));
    useEffect(() => {
      this.renderGantt();
    });
    useEffect(
      () => {
        const container = this.rootRef.el;
        if (!container) return;
        this._resizeObserver = new ResizeObserver(
          debounce(() => this.renderGantt(), 100),
        );
        this._resizeObserver.observe(container);
        const scrollEl = this.scrollArea.el;
        const onScroll = () => {
          if (this.popover.isOpen) this.popover.close();
          if (this.ChartPopover.isOpen) this.ChartPopover.close();
          // The totals row has no scrollbar of its own: its cells simply
          // follow the main body's horizontal scroll position (translate
          // applied at render time in utils/chart_row.js).
          const totalsScroll = this.totalsRowScroll?.el;
          const cellsEl = totalsScroll?.querySelector(
            ".o_gantt_view_chart_row_cells",
          );
          if (cellsEl) {
            cellsEl.style.transform = `translateX(-${scrollEl.scrollLeft}px)`;
          }
        };
        if (scrollEl)
          scrollEl.addEventListener("scroll", onScroll, { passive: true });
        return () => {
          if (scrollEl) scrollEl.removeEventListener("scroll", onScroll);
          if (this._resizeObserver) this._resizeObserver.disconnect();
        };
      },
      () => [],
    );
  }

  get zoomCfg() {
    const base = ZOOM_CONFIG[this.state.zoom];
    if (this.state.zoom !== "year") return base;
    return { ...base, colUnit: this._autoYearUnit };
  }
  // The year zoom's column unit follows the displayed range span:
  //  - more than 1 month and up to 3 months: user choice (day or month,
  //    default "month") via the toolbar dropdown
  //  - more than 3 months and up to 4 years: one month per column
  //  - more than 4 years: one column per year (keeps the column count bounded)
  get _autoYearBand() {
    const r = this.dateRange;
    if (!r || !r.start || !r.end) return "choice";
    const months =
      r.end.getFullYear() * 12 +
      r.end.getMonth() -
      (r.start.getFullYear() * 12 + r.start.getMonth());
    if (months > 48) return "year";
    if (months > 3) return "month";
    return "choice";
  }
  get _autoYearUnit() {
    const band = this._autoYearBand;
    if (band === "year") return "year";
    if (band === "month") return "month";
    return this.state.yearColumns === "month" ? "month" : "day";
  }
  // True when the year zoom is in the <= 3-month band: the user can still
  // toggle the column unit between day and month in the toolbar.
  get _isYearUnitChoice() {
    return this.state.zoom === "year" && this._autoYearBand === "choice";
  }
  get isYearMonthlyColumns() {
    return this.state.zoom === "year" && this.zoomCfg.colUnit === "month";
  }
  get _yearColumnsLabel() {
    return this.isYearMonthlyColumns
      ? _t("Column unit: Month")
      : _t("Column unit: Day");
  }
  get _yearColumnsDayLabel() {
    return _t("Column unit: Day");
  }
  get _yearColumnsMonthLabel() {
    return _t("Column unit: Month");
  }
  get records() {
    return this.model.records || [];
  }
  get groups() {
    return this.model.groups || null;
  }
  get hasGroups() {
    return this.groups && this.groups.length > 0;
  }
  get _rowLayout() {
    return this._fullRowLayout;
  }
  get dateRange() {
    // A custom range (start/end picked in the toolbar) overrides the
    // zoom-based range: the visible window is exactly the selected span.
    if (this.state.customRange) {
      return {
        start: this.state.customRange.start,
        end: this.state.customRange.end,
      };
    }
    return computeDateRange(this._focusDate, this.state.zoom);
  }
  get totalColumns() {
    return computeTotalColumns(this.dateRange, this.zoomCfg.colUnit);
  }
  get _columnWidthPct() {
    return this.totalColumns > 0 ? 100 / this.totalColumns : 0;
  }
  get _minColumnWidth() {
    return MIN_COL_WIDTH;
  }
  get _clientColWidth() {
    if (this._columnWidthPx != null && this._columnWidthPx > 0)
      return this._columnWidthPx;
    return _computeClientColWidthFn(
      this.scrollArea?.el,
      this.totalColumns,
      this.state.sidebarVisible,
      this.state.sidebarWidth,
      this.state.zoom,
      this.zoomCfg.colUnit,
    );
  }
  // get formattedFocusDate() {
  //   this.state.refresh;
  //   return formatFocusDate(this);
  // }
  get periodOptions() {
    this.state.refresh;
    return computePeriodOptions(this);
  }
  get selectedPeriodLabel() {
    const opts = this.periodOptions;
    const selected = opts.find((o) => o.selected);
    return (selected || opts[0] || {}).label || "";
  }
  get availableFilters() {
    return getAvailableFilters(this);
  }
  // Value of the date field in the toolbar (day zoom only): a luxon DateTime.
  get _focusDateDT() {
    const { DateTime } = luxon;
    return DateTime.fromJSDate(new Date(this._focusDate));
  }
  // Year shown in the toolbar number input at year zoom: always the year of
  // the END date of the currently displayed date range (the last day shown in
  // the date-range field), so the input and the range never disagree — even
  // after a custom range or a column-unit change.
  get _focusYear() {
    const endDT = this._customEndDT;
    return endDT && endDT.isValid ? endDT.year : new Date().getFullYear();
  }
  // Hover tooltip of the year input: a warning when the last typed value was
  // rejected (below 1000 or above 9999), the normal help text otherwise.
  get _yearInputTitle() {
    return this.state.yearInputWarning
      ? _t("Invalid year — min 1000, max 9999")
      : _t("Current year — type a year to jump to it");
  }
  _clearYearWarning() {
    if (this.state.yearInputWarning) {
      this.state.yearInputWarning = false;
      this.render();
    }
  }
  // Tooltip shown on the custom-range warning icon: the picked range was
  // clamped to the maximum supported span (MAX_RANGE_YEARS years).
  get _rangeClippedTitle() {
    return _t(`Range limited to ${MAX_RANGE_YEARS} years`);
  }
  // Values of the two custom-range date fields (start/end): luxon DateTime or
  // null. Without an active custom range they mirror the currently displayed
  // period (start → last displayed day), giving the inputs sensible defaults.
  get _customStartDT() {
    const { DateTime } = luxon;
    const js = this.state.customRange
      ? this.state.customStart
      : computeDateRange(this._focusDate, this.state.zoom).start;
    if (!js) return null;
    return DateTime.fromJSDate(new Date(js));
  }
  get _customEndDT() {
    const { DateTime } = luxon;
    let js;
    if (this.state.customRange) {
      js = this.state.customEnd;
    } else {
      const span = computeDateRange(this._focusDate, this.state.zoom);
      js = new Date(span.end);
      js.setDate(js.getDate() - 1); // exclusive end → last displayed day
    }
    if (!js) return null;
    return DateTime.fromJSDate(new Date(js));
  }

  _toJsDate(value) {
    if (!value) return null;
    const js =
      typeof value.toJSDate === "function" ? value.toJSDate() : new Date(value);
    js.setHours(0, 0, 0, 0);
    return js;
  }
  updateScrollByPageStep(value) {
    const v = parseInt(value, 10);
    if (Number.isInteger(v) && v > 0) {
      this.state.ScrollByPageStep = v;
    } else {
      this.state.ScrollByPageStep = 1;
    }
  }
  // Makes the scroll step follow the width of the currently displayed range
  // (one click = one full page): the number of columns of the visible range.
  _syncScrollStep() {
    this.state.ScrollByPageStep = this.totalColumns;
  }
  selectYearColumns(mode) {
    // The day/month choice only applies to the <= 3-month band of the year
    // zoom (where the dropdown is shown); wider ranges fix their own unit.
    if (mode !== "day" && mode !== "month") return;
    if (this.state.yearColumns === mode) return;
    this.state.yearColumns = mode;
    // Keep the user-selected year: reset the focus to the 1st of January of
    // the SAME focus year (never back to today), so the year shown in the
    // toolbar number input (_focusYear) does not change.
    const focusYear =
      this._focusDate && !isNaN(this._focusDate.getTime())
        ? this._focusDate.getFullYear()
        : null;
    this._focusDate = new Date(
      focusYear ?? _initFocusDateFn(this.state.zoom).getFullYear(),
      0,
      1,
    );
    this._syncScrollStep();
    this.state.refresh++;
    this.renderGantt();
  }
  _toggleSidebarField(field) {
    if (
      !this.state.sidebarFields ||
      this.state.sidebarFields[field] === undefined
    )
      return;
    this.state.sidebarFields[field] = !this.state.sidebarFields[field];
    // Re-render immediately so the sidebar width follows the checked
    // columns (base width + 50px per enabled field, see renderGantt).
    this.renderGantt();
  }
  // Receives the committed [start, end] of the range picker (luxon DateTime
  // or null) when the user validated it: picking both dates, pressing Enter
  // or leaving the inputs.
  _onRangeApply(range) {
    const [startDT, endDT] = Array.isArray(range) ? range : [null, null];
    if (!startDT && !endDT) {
      this._clearCustomRange();
      return;
    }
    if (!startDT || !endDT) {
      // Only one side selected: keep the current state until both are known.
      return;
    }
    this.state.customStart = this._toJsDate(startDT);
    this.state.customEnd = this._toJsDate(endDT);
    this._applyCustomRange();
  }
  // Applies the selected start/end range: a span of at most one calendar
  // month keeps the month filter, anything longer switches to the year zoom
  // (month columns: > 1 month and <= 12 months shows a single year, ranges
  // crossing several years are grouped per year in the major header).
  _applyCustomRange() {
    const start = this.state.customStart;
    let end = this.state.customEnd;
    if (!start || !end || end < start) return;
    // Applying exactly the currently displayed span is a no-op: the default
    // values are a starting point, not a real filter, so the zoom level is
    // left untouched.
    const natural = computeDateRange(this._focusDate, this.state.zoom);
    const naturalEnd = new Date(natural.end);
    naturalEnd.setDate(naturalEnd.getDate() - 1);
    if (
      start.getTime() === natural.start.getTime() &&
      end.getTime() === naturalEnd.getTime()
    ) {
      this.state.rangeClipped = false;
      return;
    }
    // Range → zoom: a single day (start == end) shows the day zoom (hour
    // columns), a span of up to 7 days the week zoom, up to one calendar
    // month the month filter, more than one month the year zoom (month
    // columns: the first column = start, the last = end).
    const spanMs = end.getTime() - start.getTime();
    const spanDays = Math.round(spanMs / 86400000);
    const oneMonth = new Date(start);
    oneMonth.setMonth(start.getMonth() + 1);
    let filter;
    if (spanDays <= 0) {
      filter = "day";
    } else if (spanDays <= 7) {
      filter = "week";
    } else if (end < oneMonth) {
      filter = "month";
    } else {
      filter = "year";
    }
    // Ranges wider than MAX_RANGE_YEARS would render unbounded column counts
    // (100+ year-columns are already at the safe limit): clamp the end to
    // start + MAX_RANGE_YEARS years - 1 day and flag the truncation.
    if (filter === "year") {
      const limit = new Date(start);
      limit.setFullYear(start.getFullYear() + MAX_RANGE_YEARS);
      limit.setDate(limit.getDate() - 1);
      if (end.getTime() > limit.getTime()) {
        end = limit;
        this.state.customEnd = end;
        this.state.rangeClipped = true;
      } else {
        this.state.rangeClipped = false;
      }
    }
    if (this.state.customPrevZoom == null) {
      this.state.customPrevZoom = this.state.zoom;
    }
    this.state.zoom = filter;
    // The stored range is [start, end) (exclusive end), like computeDateRange.
    // Setting the end at end-of-day makes the column of the chosen end date
    // visible: a start→end picked range covers end-start+1 day-columns.
    const endOfDay = new Date(end);
    endOfDay.setHours(23, 59, 59, 999);
    this.state.customRange = { start, end: endOfDay };
    this._syncScrollStep();
    this.state.refresh++;
    this.renderGantt();
  }
  _clearCustomRange() {
    this.state.customRange = null;
    this.state.customStart = null;
    this.state.customEnd = null;
    this.state.rangeClipped = false;
    if (this.state.customPrevZoom != null) {
      this.state.zoom = this.state.customPrevZoom;
      this.state.customPrevZoom = null;
    }
    this._syncScrollStep();
    this.state.refresh++;
    this.renderGantt();
  }

  _evalReadonlyExpr(expr, record) {
    return _evalReadonlyExprFn(expr, record);
  }
  _isFieldReadonlyForRecord(fieldName, record) {
    return _isFieldReadonlyForRecordFn(this.model, fieldName, record);
  }
  _getDateColIndex(date) {
    return getDateColIndex(date, this.dateRange.start, this.zoomCfg.colUnit);
  }
  getColumnPosition(date) {
    return utilGetColumnPosition(
      date,
      this.dateRange.start,
      this.zoomCfg.colUnit,
      this._clientColWidth,
    );
  }
  _getClampedBarLayout(record) {
    return utilGetDateGridBounds(
      record,
      this.totalColumns,
      this.dateRange.start,
      this.zoomCfg.colUnit,
    );
  }
  getBarWidth(startDate, endDate) {
    return utilGetBarWidth(startDate, endDate, this.zoomCfg.colUnit, 100);
  }
  getDragInterval() {
    return utilGetDragInterval(this.zoomCfg.colUnit);
  }

  _flushPendingWrite() {
    if (this._pendingNotification) {
      this._pendingNotification();
      this._pendingNotification = null;
    }
  }
  _onPeriodSelect(value) {
    // Selecting a period leaves the custom-range mode.
    this.state.customRange = null;
    this.state.customStart = null;
    this.state.customEnd = null;
    this.state.customPrevZoom = null;
    this._flushPendingWrite();
    this._focusDate = new Date(value);
    this.state.refresh++;
    this.renderGantt();
  }
  _onYearInput(value) {
    const year = parseInt(value, 10);
    // `new Date(year, 0, 1)` maps years 0-99 to 1900+year, so reject them
    // (typing "10" would otherwise silently jump to 1910). Years below 1000
    // are discarded too: pre-1000 dates make no sense in this view.
    if (!Number.isInteger(year) || year < 1000 || year > 9999) {
      // Warn the user the typed value was rejected (hover tooltip + red tint).
      this.state.yearInputWarning = true;
      this.render();
      return;
    }
    this.state.yearInputWarning = false;
    // Jumping to a year leaves the custom-range mode (like the period dropdown).
    this.state.customRange = null;
    this.state.customStart = null;
    this.state.customEnd = null;
    this.state.customPrevZoom = null;
    this._flushPendingWrite();
    this._focusDate = new Date(year, 0, 1);
    this._focusDate.setHours(0, 0, 0, 0);
    this.state.refresh++;
    this.renderGantt();
  }
  _onDateInput(dateTime) {
    if (!dateTime) return;
    const js =
      typeof dateTime.toJSDate === "function"
        ? dateTime.toJSDate()
        : new Date(dateTime);
    this._flushPendingWrite();
    this._focusDate = new Date(js);
    this._focusDate.setHours(0, 0, 0, 0);
    // In an active single-day custom range (day zoom), picking a date
    // moves the range to that day instead of silently ignoring the input.
    if (this.state.customRange) {
      const dayStart = this._toJsDate(dateTime);
      const endOfDay = new Date(dayStart);
      endOfDay.setHours(23, 59, 59, 999);
      this.state.customStart = dayStart;
      this.state.customEnd = endOfDay;
      this.state.customRange = { start: dayStart, end: endOfDay };
    }
    this.state.refresh++;
    this.renderGantt();
  }
  _toggleSidebar() {
    this.state.sidebarVisible = !this.state.sidebarVisible;
    this.renderGantt();
  }
  // Shows/hides the global totals row (number of bars per visible
  // column, across every loaded task).
  _toggleTotalsRow() {
    this.state.showTotalsRow = !this.state.showTotalsRow;
    this.renderGantt();
  }
  // Recomputes and renders the totals row cells. Called at the end of
  // every render, including when the signature did not change (a simple
  // visibility toggle does not rebuild the whole layout).
  _renderTotalsRow() {
    if (!this.state.showTotalsRow) return;
    if (!this.totalsRow?.el) return;
    renderTotalsRow(this);
  }
  // Click on a bar of the totals row mini bar chart: opens the READ-ONLY
  // popover listing the tasks covering the clicked column (name + dates).
  // The `_totalsColumnTasks` array is prepared by `renderTotalsRow` at render
  // time (utils/chart_row.js -> computeGlobalColumnTotals).
  async _onTotalsCellClick(ev, colIndex) {
    const tasks = this._totalsColumnTasks?.[colIndex];
    if (!Array.isArray(tasks) || !tasks.length) return;
    // Reuses the existing popover; `position: 'top'` because the totals
    // row is anchored at the bottom of the view (same `o_cw_popover`
    // styling as the detail popover, cf. `_popoverOptions`). Groups the
    // tasks like the sidebar, for a collapsible display matching the view's
    // group-by.
    const groups = groupTasksForPopover(this, tasks);
    const columnDate = this._dateFromColIndex(colIndex);
    this.ChartPopover.open(ev.currentTarget, {
      groups,
      defaultTitle: this.model.metaData.defaultTitle || null,
      columnDate,
      zoom: this.state.zoom,
    });
  }
  _onGroupSortClick() {
    const next = !this.state.sortOrder
      ? "asc"
      : this.state.sortOrder === "asc"
        ? "desc"
        : null;
    this.state.sortOrder = next;
    this.model.setSortOrder(next);
    this.renderGantt();
  }
  setZoom(zoom) {
    // Selecting a zoom level leaves the custom-range mode.
    this.state.customRange = null;
    this.state.customStart = null;
    this.state.customEnd = null;
    this.state.customPrevZoom = null;
    _setZoomLevelFn(this, zoom);
    this._syncScrollStep();
  }
  scrollToToday() {
    // "Today" leaves the custom-range mode too.
    this.state.customRange = null;
    this.state.customStart = null;
    this.state.customEnd = null;
    this.state.customPrevZoom = null;
    _scrollToTodayFn(this);
  }
  scrollByPage(direction) {
    // In custom-range mode, previous/next shift the whole window by its
    // own duration (a "page" = the selected span).
    if (this.state.customRange) {
      const { start, end } = this.state.customRange;
      const span = end.getTime() - start.getTime();
      this.state.customStart = new Date(start.getTime() + span * direction);
      this.state.customEnd = new Date(end.getTime() + span * direction);
      this.state.customRange = {
        start: this.state.customStart,
        end: this.state.customEnd,
      };
      this.state.refresh++;
      this.renderGantt();
      return;
    }
    _scrollByPageFn(this, direction);
  }
  _computeFullLayout() {
    _computeFullLayoutFn(this);
  }
  _inputsSignature() {
    return _inputsSignatureFn(this);
  }

  renderGantt() {
    if (this._isRendering) return;
    this._isRendering = true;
    try {
      const signature = this._inputsSignature();
      if (signature === this._lastInputsSignature && this.scrollArea?.el) {
        // Unchanged signature: no re-layout, but the totals row is still
        // refreshed (it follows the visibility).
        this._renderTotalsRow();
        return;
      }
      this._lastInputsSignature = signature;
      this._computeFullLayout();
      _renderGantt(this);
      this._updateFeedbackLabel();
      if (this._dragState && this._dragLastY != null)
        this._positionDropIndicator(this._dragLastY);
      this._renderTotalsRow();
    } finally {
      this._isRendering = false;
    }
  }

  _isDragTarget(groupKey) {
    return _isDragTargetFn(this, groupKey);
  }
  _isRecordHighlighted(recordId) {
    return _isRecordHighlightedFn(this, recordId);
  }
  _updateFeedbackLabel() {
    _updateFeedbackLabelFn(this);
  }
  _removeFeedbackLabel() {
    _removeFeedbackLabelFn(this);
  }
  highlightRecord(recordId, label = "", duration = 3000) {
    _highlightRecordFn(this, recordId, label, duration);
  }
  _getRecordGroupKey(record) {
    return _getRecordGroupKeyFn(this, record);
  }
  _getGroupByPath(path) {
    return _getGroupByPathFn(this, path);
  }
  _findGroupWrapperByPath(groupPath) {
    return _findGroupWrapperByPathFn(this, groupPath);
  }
  _findRootRowsWrapper() {
    return _findRootRowsWrapperFn(this);
  }
  _findBandItemForPath(groupPath) {
    return _findBandItemForPathFn(this, groupPath);
  }
  _visibleToRealIndex(groupPath, bandIndex, lane) {
    return _visibleToRealIndexFn(this, groupPath, bandIndex, lane);
  }
  _updateDropIndicator(ev) {
    _updateDropIndicatorFn(this, ev);
  }
  _refreshDropIndicator() {
    _refreshDropIndicatorFn(this);
  }
  _syncDragDropPosition() {
    _syncDragDropPositionFn(this);
  }
  _ensureDropCellHighlight(rowEl) {
    return ensureDropCellHighlight(this, rowEl);
  }
  _positionDropIndicator(clientY) {
    _positionDropIndicatorFn(this, clientY);
  }
  _hideDropIndicator() {
    _hideDropIndicatorFn(this);
  }
  _clearDropIndicator() {
    _clearDropIndicatorFn(this);
  }
  _startDrag(ev, record, mode) {
    _startDragFn(this, ev, record, mode);
  }
  _onBarClick(ev, record) {
    _onBarClickFn(this, ev, record);
  }
  _dateFromColIndex(colIndex) {
    return dateFromColIndex(this, colIndex);
  }
}

GanttRenderer.template = "miro_gantt_view.Gantt.Renderer";
GanttRenderer.components = {
  ViewScaleSelector,
  DateTimeInput,
  Dropdown,
  DropdownItem,
  DateRangeInput,
};
GanttRenderer.props = {
  model: Object,
};
