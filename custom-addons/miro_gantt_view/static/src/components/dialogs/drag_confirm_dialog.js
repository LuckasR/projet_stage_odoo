/** @odoo-module **/

import { Component, onWillUnmount, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;

/**
 * Drag confirmation dialog: lets the user adjust the proposed new date(s)
 * (Odoo date/time pickers, format dd/MM/yyyy HH:mm) before the drag change is
 * written to the database.
 *
 * Modes:
 *   - "move":         new start AND end are editable, kept synchronized so the
 *                     task duration is preserved.
 *   - "resize":       only the end date is editable.
 *   - "resize-start": only the start date is editable.
 *
 * Props:
 *   - mode, taskName, origStartDate, origEndDate, newStartDate, newEndDate
 *   - confirm(newStartDate, newEndDate): called with the dates retained by the
 *     user; each is a Date, or null when that date is not editable in the mode.
 *   - close: injected by the dialog service.
 */
export class DragConfirmDialog extends Component {
  static template = "gantt_view.DragConfirmDialog";
  static components = { Dialog, DateTimeInput };
  static props = {
    mode: {
      type: String,
      validate: (m) => ["move", "resize", "resize-start"].includes(m),
    },
    taskName: { type: String },
    origStartDate: Date,
    origEndDate: Date,
    newStartDate: Date,
    newEndDate: Date,
    confirm: { type: Function },
    cancel: { type: Function, optional: true },
    close: { type: Function },
  };

  setup() {
    this.confirmed = false;
    this.durationMs = this.props.newEndDate - this.props.newStartDate;
    this.state = useState({
      start: DateTime.fromJSDate(this.props.newStartDate),
      end: DateTime.fromJSDate(this.props.newEndDate),
    });
    // Any close path that does not confirm (Cancel button, close icon,
    // Escape, click outside) must revert the visual drag position.
    onWillUnmount(() => {
      if (!this.confirmed) {
        this.props.cancel?.();
      }
    });
  }

  get showStart() {
    return this.props.mode === "move" || this.props.mode === "resize-start";
  }

  get showEnd() {
    return this.props.mode === "move" || this.props.mode === "resize";
  }

  get dialogTitle() {
    return _t("Confirm");
  }

  get labelStart() {
    return _t("Start date");
  }

  get labelEnd() {
    return _t("End date");
  }

  get confirmLabel() {
    return _t("Confirm");
  }

  get cancelLabel() {
    return _t("Cancel");
  }

  get message() {
    const name = this.props.taskName;
    const oldstartdate = `${this._fmtJSDate(this.props.origStartDate)}`;
    const oldenddate = `${this._fmtJSDate(this.props.origEndDate)}`;
    if (this.props.mode === "move") {
      return _t("Move « %s » from %s - %s to:", name, oldstartdate, oldenddate);
    }
    return this.props.mode === "resize"
      ? _t("Change the end date of « %s » %s to:", name, oldenddate)
      : _t("Change the start date of « %s » %s to:", name, oldstartdate);
  }

  onStartChange(dt) {
    if (!this.state) return;
    dt = this._reparseInput("date-start-dialog", dt);
    this.state.start = dt;
    if (this.props.mode === "move") {
      this.state.end = dt.plus({ milliseconds: this.durationMs });
    }
  }

  onEndChange(dt) {
    if (!this.state) return;
    dt = this._reparseInput("date-end-dialog", dt);
    this.state.end = dt;
    if (this.props.mode === "move") {
      this.state.start = dt.minus({ milliseconds: this.durationMs });
    }
  }

  /**
   * Re-reads the text actually typed in a DateTimeInput (located via its id).
   * The picker's onApply can deliver a stale value when the popover is closed
   * and the user pressed Enter (datetimepicker_service skips parsing the
   * inputs in that path), so the text is parsed here as the source of truth.
   * Falls back to the picker-provided value when the field is empty or the
   * text does not parse with the dialog format.
   * @param {string} inputId - DOM id of the DateTimeInput input element
   * @param {DateTime} fallback - value delivered by the picker callback
   * @returns {DateTime}
   */
  _reparseInput(inputId, fallback) {
    const el = document.getElementById(inputId);
    if (!el || !el.value) {
      return fallback;
    }
    const parsed = DateTime.fromFormat(el.value, "dd/MM/yyyy HH:mm");
    return parsed.isValid ? parsed : fallback;
  }

  onConfirm() {
    if (!this.state) return;
    this.confirmed = true;
    // The confirmed dates are the LAST values displayed in the fields: the
    // editable inputs are the single source of truth, whatever the picker
    // callbacks delivered (onChange/onApply may be skipped or stale).
    // Only constraint: start must stay before or equal to the end. If not,
    // the last synchronized state is used as a safe fallback (the move
    // handlers always keep start <= end).
    let start = this.showStart
      ? this._reparseInput("date-start-dialog", this.state.start)
      : null;
    let end = this.showEnd
      ? this._reparseInput("date-end-dialog", this.state.end)
      : null;
    if (start && end && start.toMillis() > end.toMillis()) {
      start = this.showStart ? this.state.start : start;
      end = this.showEnd ? this.state.end : end;
    }
    this.props.confirm(
      start ? start.toJSDate() : null,
      end ? end.toJSDate() : null,
    );
    this.props.close();
  }

  _fmtJSDate(d) {
    return DateTime.fromJSDate(new Date(d)).toFormat("dd/MM/yyyy HH:mm");
  }
}
