/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, useRef } from "@odoo/owl";
import { deserializeDate, deserializeDateTime } from "@web/core/l10n/dates";
import { hasTime } from "@miro_gantt_view/utils/dates";
import {
  renderDefaultBody,
  renderCustomTemplate,
} from "@miro_gantt_view/components/popover/popover_template";

/**
 * GanttViewPopover
 *
 * Popover component displayed when clicking on a task bar (pill) in the Gantt chart.
 * Shows task details (name, dates, etc.) with optional Edit and Delete buttons.
 * Supports custom popup templates defined in the XML arch for rendering task details.
 */
export class GanttViewPopover extends Component {
  // Lazy-loaded translated strings for UI labels
  get _titleEdit() {
    return this.__titleEdit || (this.__titleEdit = _t("Edit"));
  }
  get _titleClose() {
    return this.__titleClose || (this.__titleClose = _t("Close"));
  }
  get _titleDelete() {
    return this.__titleDelete || (this.__titleDelete = _t("Delete"));
  }
  get _titleOpenFullForm() {
    return (
      this.__titleOpenFullForm_ ||
      (this.__titleOpenFullForm_ = _t("Open full form"))
    );
  }

  /**
   * Component setup: renders the popup body by either using a custom template
   * or generating a default summary view.
   */
  setup() {
    // Reference to the body container element
    this.bodyRef = useRef("bodyRef");

    // Extract record data and model metadata from props
    const { record, model } = this.props;

    // Popover title (card-header): display_name or record name fallback.
    this.title = record.display_name || record.name || "";
    const raw = record._raw || {};
    const { dateStart, dateEnd } = model.metaData;

    // Build a context object from the raw record data
    const context = { ...raw };

    /**
     * Creates a date value usable directly in custom templates: a luxon
     * `DateTime` (via the native `deserializeDate`/`deserializeDateTime`
     * parsers from `@web/core/l10n/dates`, same server semantics as our model:
     * datetime = UTC, date alone = local midnight) exposed with a native
     * `.toFormat(fmt)`. An invalid/unreadable value is kept as-is.
     *
     * @param {string} val - The date value to wrap
     * @returns {Object|string} luxon DateTime (toFormat), or empty string if empty
     */
    const makeDateWrapper = (val) => {
      if (!val) return "";
      if (typeof val !== "string") return val;
      try {
        const d = hasTime(val)
          ? deserializeDateTime(val)
          : deserializeDate(val);
        return d.isValid && d.toMillis() !== 0 ? d : val;
      } catch (error) {
        return val;
      }
    };

    // Wrap date fields with the formatter so templates can use .toFormat()
    if (dateStart && raw[dateStart] !== undefined) {
      context[dateStart] = makeDateWrapper(raw[dateStart]);
    }
    if (dateEnd && raw[dateEnd] !== undefined) {
      context[dateEnd] = makeDateWrapper(raw[dateEnd]);
    }

    // Render the popup body: use custom template if defined, otherwise use default
    const popupDef = model.metaData.ganttPopup;
    if (popupDef) {
      this.rawBody = renderCustomTemplate(popupDef.xml, context);
    } else {
      this.rawBody = renderDefaultBody(context, model.metaData);
    }

    // After mount, inject the rendered HTML into the DOM body element
    onMounted(() => {
      if (this.bodyRef.el) {
        this.bodyRef.el.innerHTML = "";
        const temp = document.createElement("div");
        temp.innerHTML = this.rawBody;
        let _maxIter = 1000;
        while (temp.firstChild && --_maxIter > 0) {
          this.bodyRef.el.appendChild(temp.firstChild);
        }
      }
    });

    // Determine if Edit/Delete/Open full form buttons should be shown based on props
    this.hasEdit = Boolean(this.props.editRecord);
    this.hasDelete = Boolean(this.props.deleteRecord);
    this.hasOpenFullForm = Boolean(this.props.openFullFormRecord);

    // Ribbon status: shown top-left of the popover only when the view
    // declares status_field and the record carries a status value.
    const { statusField } = model.metaData;
    this.status = statusField && record.status ? String(record.status) : "";
  }

  /**
   * Handles the Edit button click.
   * Calls the editRecord callback with the current record, then closes the popover.
   */
  onEdit() {
    this.props.editRecord(this.props.record);
    this.props.close();
  }

  /**
   * Handles the Delete button click.
   * Calls the deleteRecord callback with the current record, then closes the popover.
   */
  onDelete() {
    this.props.deleteRecord(this.props.record);
    this.props.close();
  }

  /**
   * Handles the Open full form button click.
   * Opens the record's full form view in the current tab, then closes the popover.
   */
  onOpenFullForm() {
    this.props.openFullFormRecord(this.props.record);
    this.props.close();
  }
}

// Template reference for the OWL component
GanttViewPopover.template = "gantt_view.Popover";

// Component prop types definition
GanttViewPopover.props = {
  close: Function, // Function to close the popover
  record: Object, // The task record being displayed
  model: Object, // The Gantt model instance
  editRecord: { type: Function, optional: true },
  deleteRecord: { type: Function, optional: true },
  openFullFormRecord: { type: Function, optional: true },
};
