/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useDateTimePicker } from "@web/core/datetime/datetime_hook";

/**
 * Two linked date inputs (start → end) backed by the same range-capable
 * DateTimePicker used by the form "daterange" widget: picking a date for one
 * side automatically switches the open picker to the other side, and the
 * committed value is delivered as a [start, end] array.
 */
export class DateRangeInput extends Component {
  static template = "gantt_view.DateRangeInput";
  static props = {
    value: { type: Array, optional: true },
    showWeekNumbers: { type: Boolean, optional: true },
    format: { type: String, optional: true },
    onChange: { type: Function, optional: true },
    onApply: { type: Function, optional: true },
  };

  setup() {
    const getPickerProps = () => ({
      value: this.props.value ?? [null, null],
      type: "date",
      range: true,
      showWeekNumbers: this.props.showWeekNumbers ?? true,
    });
    useDateTimePicker({
      get pickerProps() {
        return getPickerProps();
      },
      format: this.props.format,
      onChange: (range) => this.props.onChange?.(range),
      onApply: (range) => this.props.onApply?.(range),
    });
  }
}
