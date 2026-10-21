/** @odoo-module **/
//  Reference: https://github.com/odoo/odoo/tree/17.0/addons/web/static/src/views/list/list_arch_parser.js

import { visitXML } from '@web/core/utils/xml';
import { getActiveActions } from '@web/views/utils';
/**
 * GanttArchParser
 *
 * Parses the <miro_gantt> XML arch node and extracts view configuration.
 * Validates required attributes and produces warnings for misconfigurations.
 */
export class GanttArchParser {
    /**
     * Parses the arch XML and returns a configuration object.
     *
     * Expected <miro_gantt> attributes:
     *   date_start (required) - Date field marking task start
     *   date_end (required) - Date field marking task end
     *   colored_by - Field used to assign bar colors
     *   default_group_by - Comma-separated field names for grouping
     *   default_filter - Default zoom level: "day", "week", "month", "year"
     *   available_filters - Comma-separated allowed zoom levels
*   default_title - Column header label for the record name panel
 *   sidebar_label_field - Field displayed in the sidebar (e.g. a reference code)
 *   taskbar_label_field - Field displayed on the taskbar pill (e.g. a description)
 *   name / default_name - Deprecated aliases for sidebar_label_field /
 *              taskbar_label_field (kept for backward compatibility; a
 *              warning is logged when used).
 *              If only one of sidebar_label_field/taskbar_label_field is set,
 *              the other falls back to the same value.
 *   progress_field - Field read for the progress percentage display
 *   duration_field - Field read for the duration display
 *   overdue_field - Boolean field marking a record as overdue
 *   status_field - Selection field for the status display
 *   sidebar_column_fields - Comma-separated field names displayed as toggleable
 *              columns of the sidebar (in addition to the name column).
 *              When set, these replace the historical fixed columns
 *              (start/end/status/duration/progress).
 *   default_progress / default_duration / default_overdue / available_status -
 *              Deprecated aliases for the *_field attributes above (kept for
 *              backward compatibility; a warning is logged when used).
 *   plan - Set to "true" to enable planning by dragging on empty cells (requires edit rights)
 *   sequence - Optional field name (e.g. "sequence") used to persist taskbar
 *              ordering in the database when reordering via drag-and-drop.
 *   string - View display name
 *
     * Also extracts <field> elements for additional data loading (with optional
     * readonly expressions like readonly="state != 'draft'") and
     * <templates> with <t t-name> for custom popup rendering.
     *
     * @param {Element} arch - The XML arch node to parse
     * @param {Object} fields - The model's field definitions
     * @returns {Object} archInfo - Parsed configuration object
     */
    parse(arch, fields) {
        // Initialize the archInfo object with default values
        const archInfo = {
            canCreate: true,
            canEdit: true,
            canDelete: true,
            createAction: null,
            formViewId: false,
            dateStart: null,
            dateEnd: null,
            coloredBy: null,
            defaultGroupBy: [],
            defaultFilter: 'month',
            availableFilters: ['day', 'week', 'month', 'year'],
            defaultName: null,
            name: null,
            sidebarLabelField: null,
            taskbarLabelField: null,
            defaultTitle: null,
            progressField: null,
            durationField: null,
            overdueField: null,
            statusField: null,
            sidebarColumnFields: [],
            // Deprecated aliases for the *_field attributes above, kept for
            // backward compatibility with existing views (read-only modules).
            defaultProgress: null,
            defaultDuration: null,
            defaultOverdue: null,
            availableStatus: null,
            sequence: null,
            fieldReadonlyExpr: {},
            warnings: [],
        };
        const extraFields = [];
        let GanttPopup = null;
        let inTemplates = false;
        // Walk through all XML nodes using the visitXML utility
        visitXML(arch, (node) => {
            // --- Parse <miro_gantt> root element attributes ---
            if (node.tagName === 'miro_gantt') {
                const { create: canCreate, delete: canDelete, edit: canEdit } = getActiveActions(node);
                archInfo.canCreate = canCreate;
                archInfo.canEdit = canEdit;
                archInfo.canDelete = canDelete;

                if (node.hasAttribute('date_start')) {
                    archInfo.dateStart = node.getAttribute('date_start');
                }
                if (node.hasAttribute('date_end')) {
                    archInfo.dateEnd = node.getAttribute('date_end');
                }
                if (node.hasAttribute('colored_by')) {
                    archInfo.coloredBy = node.getAttribute('colored_by');
                }
                if (node.hasAttribute('default_title')) {
                    archInfo.defaultTitle = node.getAttribute('default_title');
                }
                if (node.hasAttribute('default_name')) {
                    archInfo.defaultName = node.getAttribute('default_name');
                    archInfo.warnings.push(
                        "Attribute 'default_name' is deprecated, use 'taskbar_label_field' instead."
                    );
                }
                if (node.hasAttribute('name')) {
                    archInfo.name = node.getAttribute('name');
                    archInfo.warnings.push(
                        "Attribute 'name' is deprecated, use 'sidebar_label_field' instead."
                    );
                }
                if (node.hasAttribute('sidebar_label_field')) {
                    archInfo.sidebarLabelField = node.getAttribute('sidebar_label_field');
                }
                if (node.hasAttribute('taskbar_label_field')) {
                    archInfo.taskbarLabelField = node.getAttribute('taskbar_label_field');
                }
                if (node.hasAttribute('status_field')) {
                    archInfo.statusField = node.getAttribute('status_field');
                }
                if (node.hasAttribute('available_status')) {
                    archInfo.availableStatus = node.getAttribute('available_status');
                    archInfo.warnings.push(
                        "Attribute 'available_status' is deprecated, use 'status_field' instead."
                    );
                }
                if (node.hasAttribute('progress_field')) {
                    archInfo.progressField = node.getAttribute('progress_field');
                }
                if (node.hasAttribute('default_progress')) {
                    archInfo.defaultProgress = node.getAttribute('default_progress');
                    archInfo.warnings.push(
                        "Attribute 'default_progress' is deprecated, use 'progress_field' instead."
                    );
                }
                if (node.hasAttribute('duration_field')) {
                    archInfo.durationField = node.getAttribute('duration_field');
                }
                if (node.hasAttribute('default_duration')) {
                    archInfo.defaultDuration = node.getAttribute('default_duration');
                    archInfo.warnings.push(
                        "Attribute 'default_duration' is deprecated, use 'duration_field' instead."
                    );
                }
                if (node.hasAttribute('overdue_field')) {
                    archInfo.overdueField = node.getAttribute('overdue_field');
                }
                if (node.hasAttribute('default_overdue')) {
                    archInfo.defaultOverdue = node.getAttribute('default_overdue');
                    archInfo.warnings.push(
                        "Attribute 'default_overdue' is deprecated, use 'overdue_field' instead."
                    );
                }
                if (node.hasAttribute('sequence')) {
                    archInfo.sequence = node.getAttribute('sequence');
                }
                if (node.hasAttribute('sidebar_column_fields')) {
                    archInfo.sidebarColumnFields = node
                        .getAttribute('sidebar_column_fields')
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean);
                }
                if (node.hasAttribute('default_group_by')) {
                    // Split comma-separated group-by fields, trim whitespace, remove empty strings
                    archInfo.defaultGroupBy = node
                        .getAttribute('default_group_by')
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean);
                }
                if (node.hasAttribute('default_filter')) {
                    // Validate that the default filter is one of the allowed values
                    const filter = node.getAttribute('default_filter');
                    if (['day', 'week', 'month', 'year'].includes(filter)) {
                        archInfo.defaultFilter = filter;
                    }
                }
                if (node.hasAttribute('available_filters')) {
                    // Parse and validate available filters, discarding any invalid values
                    const allowed = node
                        .getAttribute('available_filters')
                        .split(',')
                        .map((s) => s.trim());
                    archInfo.availableFilters = allowed.filter((s) =>
                        ['day', 'week', 'month', 'year'].includes(s)
                    );
                }

                if (node.hasAttribute('form_view_id')) {
                    archInfo.formViewId = parseInt(node.getAttribute('form_view_id'), 10);
                }
                if (node.hasAttribute('on_create')) {
                    archInfo.createAction = node.getAttribute('on_create');
                }

                const string = node.getAttribute('string');
                if (string) {
                    archInfo.string = string;
                }
            }

            // --- Parse <field> elements for additional data loading ---
            if (node.tagName === 'field' && node.hasAttribute('name')) {
                const fieldName = node.getAttribute('name');
                extraFields.push(fieldName);
                if (node.hasAttribute('readonly')) {
                    archInfo.fieldReadonlyExpr[fieldName] = node.getAttribute('readonly');
                }
            }

            // --- Parse <templates> for custom popup rendering ---
            if (node.tagName === 'templates') {
                inTemplates = true;
            }
            if (inTemplates && node.tagName === 't' && node.hasAttribute('t-name')) {
                GanttPopup = {
                    name: node.getAttribute('t-name'),
                    xml: node.outerHTML,
                };
            }
        });

        // Store the list of extra field names in the archInfo
        archInfo.fieldNames = extraFields;

        // Store the custom popup template if one was found
        if (GanttPopup) {
            archInfo.ganttPopup = GanttPopup;
        }

        // --- Resolve deprecated field-name aliases ---
        // Deprecated aliases win only if the new *_field attributes aren't set,
        // to ease migration of existing views.
        if (!archInfo.progressField && archInfo.defaultProgress) {
            archInfo.progressField = archInfo.defaultProgress;
        }
        if (!archInfo.durationField && archInfo.defaultDuration) {
            archInfo.durationField = archInfo.defaultDuration;
        }
        if (!archInfo.overdueField && archInfo.defaultOverdue) {
            archInfo.overdueField = archInfo.defaultOverdue;
        }
        if (!archInfo.statusField && archInfo.availableStatus) {
            archInfo.statusField = archInfo.availableStatus;
        }

        // --- Validation: check required attributes and field existence ---
        if (!archInfo.dateStart) {
            archInfo.warnings.push("Missing required attribute 'date_start' on <miro_gantt>.");
        }
        if (!archInfo.dateEnd) {
            archInfo.warnings.push("Missing required attribute 'date_end' on <miro_gantt>.");
        }
        if (fields && archInfo.dateStart && !(archInfo.dateStart in fields)) {
            archInfo.warnings.push(
                `Field '${archInfo.dateStart}' (date_start) not found in model fields.`
            );
        }
        if (fields && archInfo.dateEnd && !(archInfo.dateEnd in fields)) {
            archInfo.warnings.push(
                `Field '${archInfo.dateEnd}' (date_end) not found in model fields.`
            );
        }
        if (archInfo.statusField && fields && !(archInfo.statusField in fields)) {
            archInfo.warnings.push(
                `Field '${archInfo.statusField}' (status_field) not found in model fields.`
            );
        }

        // --- Resolve sidebar/taskbar label fields ---
        // 1. Deprecated aliases (`name`, `default_name`) win only if the new
        //    attributes aren't set, to ease migration of existing views.
        if (!archInfo.sidebarLabelField && archInfo.name) {
            archInfo.sidebarLabelField = archInfo.name;
        }
        if (!archInfo.taskbarLabelField && archInfo.defaultName) {
            archInfo.taskbarLabelField = archInfo.defaultName;
        }
        // 2. Cross-fallback: if only one of the two is configured, reuse it
        //    for the other spot rather than leaving it blank.
        if (!archInfo.sidebarLabelField && archInfo.taskbarLabelField) {
            archInfo.sidebarLabelField = archInfo.taskbarLabelField;
        }
        if (!archInfo.taskbarLabelField && archInfo.sidebarLabelField) {
            archInfo.taskbarLabelField = archInfo.sidebarLabelField;
        }
        // Note: `fields` here may only contain fields already referenced
        // elsewhere (search view, groupby...), not the model's full field
        // list — so a missing entry does NOT mean the field doesn't exist.
        // Only warn, never null out the resolved value.
        if (archInfo.sidebarLabelField && fields && !(archInfo.sidebarLabelField in fields)) {
            archInfo.warnings.push(
                `Field '${archInfo.sidebarLabelField}' (sidebar_label_field) not found in the ` +
                `fields passed to the view — this may be a false positive if it's not ` +
                `referenced elsewhere in the arch.`
            );
        }
        if (archInfo.taskbarLabelField && fields && !(archInfo.taskbarLabelField in fields)) {
            archInfo.warnings.push(
                `Field '${archInfo.taskbarLabelField}' (taskbar_label_field) not found in the ` +
                `fields passed to the view — this may be a false positive if it's not ` +
                `referenced elsewhere in the arch.`
            );
        }

        return archInfo;
    }
}
