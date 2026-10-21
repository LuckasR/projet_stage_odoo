/** @odoo-module **/
//  Reference: https://github.com/odoo/odoo/tree/17.0/addons/web/static/src/views/list/list_controller.js

import { onWillUnmount } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { Component, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { usePager } from "@web/search/pager_hook";
import { useService } from "@web/core/utils/hooks";
import { useSetupView } from "@web/views/view_hook";
import { useModelWithSampleData } from "@web/model/model";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { standardViewProps } from "@web/views/standard_view_props";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { extractErrorMessage } from "@miro_gantt_view/utils/error_message";
/**
 * GanttController
 *
 * Controller component for the Miro Gantt view.
 * Wires the model, layout, search bar, pager, and cog menu together.
 * Manages pagination state via the usePager hook.
 *
 * Template: "miro_gantt_view.GanttController"
 */
export class GanttController extends Component {
  /**
   * Component setup: initializes the model, view setup, search bar toggler, and pager.
   * The model is created using useModelWithSampleData to support sample data preview.
   */
  setup() {
    try {
      // Initialize the Gantt model with the provided Model class and parameters

      this.model = useModelWithSampleData(
        this.props.Model,
        this.props.modelParams,
      );
    } catch (error) {
      console.error("Failed to initialize Gantt model:", error);
      throw error;
    }

    this.notificationService = useService("notification");

    // Set up the view with root ref and local state
    useSetupView({
      rootRef: useRef("root"),
      getLocalState: () => {
        try {
          return { metaData: this.model.metaData };
        } catch (error) {
          console.error("Failed to get local state:", error);
          return {};
        }
      },
      getContext: () => this.getContext(),
    });

    // Initialize the search bar toggler
    this.searchBarToggler = useSearchBarToggler();

    this.actionService = useService("action");
    this.dialogService = useService("dialog");
    onWillUnmount(() => this.closeDialog?.());

    // Set up pagination with the pager hook
    usePager(() => ({
      offset: this.model.offset,
      limit: this.model.limit,
      total: this.model.count,
      onUpdate: async ({ offset, limit }) => {
        await this.model.load({ ...this.model.searchParams, offset, limit });
      },
    }));
  }

  /**
   * Returns the context for the view.
   * Can be overridden to provide additional context values.
   * @returns {Object} Empty context object
   */
  getContext() {
    return {};
  }
  /**
   * Translated "New" label for the create button.
   * @returns {string} The localized label
   */
  get _titleNew() {
    return this.__titleNew_ || (this.__titleNew_ = _t("New"));
  }
  /**
   * Creates a new record, either by opening the configured create action or
   * the form dialog. Returns a promise that resolves once the dialog closes
   * (create-action mode resolves immediately). Extra options are forwarded to
   * the dialog so callers can hook into the creation lifecycle:
   *   - options.onCreated(rawRecord|null, resId): called right after the
   *     record is saved and inserted into the gantt model.
   *
   * @param {Object} context - Create context (default_* keys)
   * @param {Object} [options] - Optional callbacks
   * @returns {Promise<void>} Resolves when the dialog is closed
   */
  create(context, options = {}) {
    const { createAction } = this.model.metaData;
    if (createAction) {
      this.actionService.doAction(createAction, {
        additionalContext: context,
        onClose: () => {
          this.model.load(this.model.searchParams);
          options.onClosed?.();
        },
      });
      return Promise.resolve();
    }
    return this.openDialog({ context }, options);
  }

  openDialog(props, options = {}) {
    const { canEdit, resModel, formViewId: viewId } = this.model.metaData;
    const title = props.title || (props.resId ? _t("Open") : _t("Create"));
    // Tracks whether a brand-new record was created in this dialog and
    // inserted into the model locally. When it was, the full reload that
    // normally happens on close is skipped: the taskbar is already visible.
    this._createdInDialog = false;
    this.closeDialog = this.dialogService.add(
      FormViewDialog,
      {
        title,
        resModel,
        viewId,
        resId: props.resId,
        mode: canEdit ? "edit" : "readonly",
        context: props.context,
        onRecordSaved: (record) => {
          if (!props.resId) {
            this._handleRecordCreated(record, options);
          }
        },
      },
      {
        ...options,
        onClose: () => {
          this.closeDialog = null;
          if (!this._createdInDialog) {
            this.model.load(this.model.searchParams);
          }
          options.onClosed?.();
          if (this._dialogCloseResolve) {
            const resolve = this._dialogCloseResolve;
            this._dialogCloseResolve = null;
            resolve();
          }
        },
      },
    );
    return new Promise((resolve) => {
      this._dialogCloseResolve = resolve;
    });
  }

  /**
   * Called right after a brand-new record is saved in the create dialog.
   * Fetches the freshly created record and inserts it into the gantt model so
   * the taskbar is displayed immediately (no full view reload needed).
   * Notifies the caller via options.onCreated when provided.
   *
   * @param {Object} record - The saved form record
   * @param {Object} options - Options forwarded from create()
   */
  async _handleRecordCreated(record, options) {
    const resId = record && record.resId;
    if (resId == null) return;
    const raw = await this.model.fetchNewRecord(resId);
    if (raw) {
      try {
        await this.model.addNewRecord(raw);
        this._createdInDialog = true;
      } catch (error) {
        console.error(
          "Failed to insert the created record into the gantt:",
          error,
        );
        this.model.load(this.model.searchParams);
      }
    }
    if (typeof options.onCreated === "function") {
      options.onCreated(raw || null, resId);
    }
  }

  async onAddClicked() {
    const context = this.model.getDialogContext
      ? this.model.getDialogContext({ withDefault: true })
      : {};

    try {
      await this.create(context);
      this.notificationService.add("", {
        title: _t("Record created successfully"),
        type: "success",
      });
    } catch (error) {
      this.notificationService.add(extractErrorMessage(error), {
        title: _t("Failed to create record"),
        type: "danger",
      });
    }
  }
}

// Template reference for the OWL component
GanttController.template = "miro_gantt_view.Gantt.Controller";

// Sub-components used in the template
GanttController.components = { Layout, SearchBar };

// Component prop types definition
GanttController.props = {
  ...standardViewProps,
  Model: Function,
  modelParams: Object,
  Renderer: Function,
};
