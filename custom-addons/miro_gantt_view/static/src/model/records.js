/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { extractErrorMessage } from "@miro_gantt_view/utils/error_message";
import { parseDate, hasTime } from "@miro_gantt_view/utils/dates";
import { COLOR_PALETTE } from "@miro_gantt_view/utils/config";

/**
 * Resolves the display label for a status value. When a status_field
 * selection field is configured, maps the stored value to its translated
 * label; otherwise returns the raw string form.
 * @param {Object} model - The Gantt model instance
 * @param {*} value - The raw status value
 * @returns {string|null} The display label, or null when value is null/undefined
 */
function statusLabel(model, value) {
  if (value == null) return null;
  const { statusField = "" } = model.metaData || {};
  const statusFieldDef = (model.metaData.fields || {})[statusField];
  if (
    statusFieldDef &&
    statusFieldDef.type === "selection" &&
    Array.isArray(statusFieldDef.selection)
  ) {
    const match = statusFieldDef.selection.find(
      ([v]) => String(v) === String(value),
    );
    if (match) return match[1];
  }
  return String(value);
}

/**
 * Converts an HTML field value (fields.Html, e.g. a `description` column used
 * as a label) into a plain-text label. The sidebar/pill labels are rendered
 * with `t-esc`, so raw markup would be displayed literally (attributes such as
 * `data-last-history-steps` included). Non-HTML fields are returned unchanged,
 * keeping the existing label logic untouched.
 * @param {Object} model - The Gantt model instance
 * @param {string} fieldName - The label field name
 * @param {*} value - The raw field value
 * @returns {*} The plain-text value for HTML fields, else the original value
 */
let _labelCleanEl = null;
function cleanLabelValue(model, fieldName, value) {
  if (value == null || typeof value !== "string") return value;
  const fieldDefs = (model.metaData || {}).fields || {};
  if (!fieldDefs[fieldName] || fieldDefs[fieldName].type !== "html") {
    return value;
  }
  // Keep a word separation where HTML uses line-break/block boundaries,
  // otherwise consecutive blocks would concatenate ("word1word2").
  const html = value
    .replace(/<\s*(?:br|hr)\s*\/?\s*>/gi, " ")
    .replace(
      /<\s*\/\s*(?:p|div|li|ul|ol|table|tbody|tr|td|th|h[1-6]|blockquote|pre)\s*>/gi,
      " ",
    );
  let text;
  if (typeof document !== "undefined" && document.createElement) {
    // Detached node: parses the markup and decodes entities (&amp; -> &)
    // without executing anything (never inserted in the document).
    if (!_labelCleanEl) _labelCleanEl = document.createElement("div");
    _labelCleanEl.innerHTML = html;
    text = _labelCleanEl.textContent || "";
    _labelCleanEl.innerHTML = "";
  } else {
    text = html.replace(/<[^>]*>/g, "");
  }
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Builds the list of fields to read from the ORM, combining the date fields,
 * the name/colored_by/status/progress/duration fields, group-by fields, and
 * any extra fields declared in the arch.
 * @param {Object} model - The Gantt model instance
 * @returns {string[]} The deduplicated field name list
 */
function buildFieldList(model) {
  const {
    dateStart = "",
    dateEnd = "",
    coloredBy = "",
    sidebarLabelField = "",
    taskbarLabelField = "",
    fieldNames = [],
    statusField = "",
    progressField = "",
    durationField = "",
    overdueField = "",
    sidebarColumnFields = [],
    sequence = "",
  } = model.metaData || {};
  const fields = [dateStart, dateEnd];
  if (coloredBy) {
    const rootField = coloredBy.includes(".")
      ? coloredBy.split(".")[0]
      : coloredBy;
    if (!fields.includes(rootField)) fields.push(rootField);
  }
  if (sequence) fields.push(sequence);
  // Both label fields are potentially needed at once (sidebar vs taskbar
  // pill are two distinct display targets, not a fallback chain), so both
  // are fetched from the ORM when configured.
  if (sidebarLabelField && !fields.includes(sidebarLabelField)) {
    fields.push(sidebarLabelField);
  }
  if (taskbarLabelField && !fields.includes(taskbarLabelField)) {
    fields.push(taskbarLabelField);
  }
  if (
    !sidebarLabelField &&
    !taskbarLabelField &&
    !fields.includes("display_name")
  ) {
    fields.push("display_name");
  }
  for (const f of model._groupByFields) {
    if (!fields.includes(f)) fields.push(f);
  }
  for (const f of fieldNames) {
    if (!fields.includes(f)) fields.push(f);
  }
  for (const f of sidebarColumnFields) {
    if (!fields.includes(f)) fields.push(f);
  }
  if (statusField && !fields.includes(statusField)) fields.push(statusField);
  if (progressField && !fields.includes(progressField))
    fields.push(progressField);
  if (durationField && !fields.includes(durationField))
    fields.push(durationField);
  if (overdueField && !fields.includes(overdueField)) fields.push(overdueField);
  return fields;
}

/**
 * Loads records from the ORM using searchRead and updates the total count via
 * searchCount. Stores the applied offset/limit on the model.
 * @param {Object} model - The Gantt model instance
 * @param {string} resModel - The model name to read
 * @param {Object} searchParams - Domain/context/offset/limit
 * @param {string[]} fields - Fields to read
 * @returns {Promise<Object[]>} The fetched raw records
 */
async function fetchRecords(model, resModel, searchParams, fields) {
  const domain = searchParams.domain || [];
  const context = searchParams.context || {};
  const offset =
    searchParams.offset !== undefined ? searchParams.offset : model.offset;
  const limit =
    searchParams.limit !== undefined ? searchParams.limit : model.limit;
  let records;
  try {
    records = await model.orm.searchRead(resModel, domain, fields, {
      context,
      offset,
      limit,
    });
    try {
      model.count = await model.orm.searchCount(resModel, domain, { context });
    } catch {
      model.count = records.length;
    }
  } catch (error) {
    console.error("Failed to load records:", error);
    throw error;
  }
  model.offset = offset;
  model.limit = limit;
  return records;
}

/**
 * Maps a single raw ORM record into the Gantt's internal record shape, parsing
 * dates, deriving the display name and color, and storing the raw record on
 * `_raw` for later use (grouping, popups, writes).
 * @param {Object} model - The Gantt model instance
 * @param {Object} record - The raw ORM record
 * @returns {Object} The mapped Gantt record
 */
function mapRecord(model, record) {
  const {
    dateStart = "",
    dateEnd = "",
    coloredBy = "",
    sidebarLabelField = "",
    taskbarLabelField = "",
    statusField = "",
    progressField = "",
    durationField = "",
    overdueField = "",
  } = model.metaData || {};
  let colorIndex = 0;
  if (coloredBy && !coloredBy.includes(".")) {
    if (record[coloredBy]) {
      if (Array.isArray(record[coloredBy])) {
        colorIndex = record[coloredBy][0] % COLOR_PALETTE.length;
      } else if (typeof record[coloredBy] === "number") {
        colorIndex = record[coloredBy];
      }
    }
  }
  // Sidebar display name (e.g. a reference code), falling back to
  // display_name / #id if missing.
  const sidebarLabel = sidebarLabelField
    ? cleanLabelValue(model, sidebarLabelField, record[sidebarLabelField])
    : null;
  let recordName;
  if (sidebarLabel) {
    recordName = sidebarLabel;
  } else if (record.display_name) {
    recordName = record.display_name;
  } else {
    recordName = `#${record.id}`;
  }
  // Taskbar pill label (e.g. a longer description), falling back to the
  // sidebar name above when not configured/empty so the pill is never left
  // blank.
  let pillLabel;
  if (taskbarLabelField && record[taskbarLabelField]) {
    pillLabel =
      cleanLabelValue(model, taskbarLabelField, record[taskbarLabelField]) ||
      recordName;
  } else {
    pillLabel = recordName;
  }
  return {
    id: record.id,
    name: recordName,
    pillLabel: pillLabel,
    start: parseDate(record[dateStart]),
    end: parseDate(record[dateEnd]),
    startHasTime: hasTime(record[dateStart]),
    endHasTime: hasTime(record[dateEnd]),
    color: COLOR_PALETTE[Math.abs(colorIndex) % COLOR_PALETTE.length],
    status: statusLabel(model, statusField ? record[statusField] : null),
    progress: progressField ? record[progressField] : null,
    duration:
      durationField && record[durationField] != null
        ? Number(record[durationField])
        : null,
    isOverdue: overdueField ? Boolean(record[overdueField]) : false,
    _raw: record,
  };
}

/**
 * Maps all raw ORM records onto the model's `records` array.
 * @param {Object} model - The Gantt model instance
 * @param {Object[]} records - The raw ORM records
 */
function mapRecords(model, records) {
  model.records = records.map((record) => mapRecord(model, record));
}

/**
 * Resolves bar colors for records colored by a "related" field of the form
 * "root.subfield", reading the target field value from the related model.
 * @param {Object} model - The Gantt model instance
 */
async function resolveRelatedColors(model) {
  const coloredBy = model.metaData?.coloredBy || "";
  if (!coloredBy.includes(".")) return;
  const [rootField, subField] = coloredBy.split(".");
  const fieldDefs = model.metaData?.fields || {};
  const relatedModel = fieldDefs[rootField]?.relation;
  if (!relatedModel || !subField) return;
  const idSet = new Set();
  for (const rec of model.records) {
    const val = rec._raw?.[rootField];
    const id = Array.isArray(val) ? val[0] : val;
    if (id) idSet.add(id);
  }
  if (!idSet.size) return;
  const relatedRecords = await model.orm.read(
    relatedModel,
    [...idSet],
    [subField],
  );
  const colorMap = {};
  for (const rr of relatedRecords) {
    const hex = rr[subField];
    if (hex && /^#[0-9a-fA-F]{3,8}$/.test(hex)) {
      colorMap[rr.id] = hex;
    } else {
      colorMap[rr.id] = COLOR_PALETTE[rr.id % COLOR_PALETTE.length];
    }
  }
  for (const rec of model.records) {
    const val = rec._raw?.[rootField];
    const id = Array.isArray(val) ? val[0] : val;
    rec.color = colorMap[id] || COLOR_PALETTE[0];
  }
}

/**
 * Resolves display names for many2many fields referenced in the extra field
 * list, the sidebar columns or the group-by fields, writing `{ id, name }`
 * objects into each record's raw m2m values.
 * @param {Object} model - The Gantt model instance
 */
async function resolveM2MNames(model) {
  const allFields = model.metaData.fields || {};
  const fieldNames = model.metaData.fieldNames || [];
  const groupByFields = model._groupByFields || [];
  const sidebarColumnFields = model.metaData.sidebarColumnFields || [];
  const targetFields = [
    ...new Set([...fieldNames, ...sidebarColumnFields, ...groupByFields]),
  ];
  const m2mFields = targetFields.filter(
    (f) => allFields[f]?.type === "many2many",
  );
  if (!m2mFields.length) return;
  await Promise.all(
    m2mFields.map(async (fieldName) => {
      const field = allFields[fieldName];
      const uniqueIds = [
        ...new Set(model.records.flatMap((r) => r._raw[fieldName] || [])),
      ];
      if (!uniqueIds.length) return;
      try {
        const rows = await model.orm.searchRead(
          field.relation,
          [["id", "in", uniqueIds]],
          ["display_name"],
        );
        const nameMap = Object.fromEntries(
          rows.map((r) => [r.id, r.display_name]),
        );
        for (const record of model.records) {
          const ids = record._raw[fieldName] || [];
          record._raw[fieldName] = ids.map((id) => ({
            id,
            name: nameMap[id] || `#${id}`,
          }));
        }
      } catch (e) {
        console.warn(`Failed to resolve names for ${fieldName}:`, e);
      }
    }),
  );
}

/**
 * Collects the IDs referenced by a relational field (many2one/many2many) across
 * all records, so avatar availability can be checked.
 * @param {Object} model - The Gantt model instance
 * @param {Object} field - The field definition
 * @param {string} fieldName - The field name
 * @returns {Set<number>} The set of referenced record IDs
 */
function getAvatarFieldIds(model, field, fieldName) {
  const ids = new Set();
  for (const record of model.records) {
    const val = record._raw[fieldName];
    if (field.type === "many2one" && Array.isArray(val) && val.length >= 1) {
      ids.add(val[0]);
    } else if (field.type === "many2many" && Array.isArray(val)) {
      for (const item of val) {
        const id = typeof item === "object" && item != null ? item.id : item;
        if (id != null) ids.add(id);
      }
    }
  }
  return ids;
}

/**
 * Detects avatar-capable group-by fields (many2one/many2many to res.users,
 * res.partner or hr.employee) and records which referenced records actually
 * have an image_128, so the sidebar can render avatars (or fall back).
 * @param {Object} model - The Gantt model instance
 */
async function resolveAvatarModels(model) {
  const fields = model.metaData.fields || {};
  const AVATAR_MODELS = ["res.users", "res.partner", "hr.employee"];
  model._avatarModels = {};
  model._avatarIdsWithImage = {};
  for (const fieldName of model._groupByFields) {
    const field = fields[fieldName];
    if (
      field &&
      (field.type === "many2one" || field.type === "many2many") &&
      AVATAR_MODELS.includes(field.relation)
    ) {
      model._avatarModels[fieldName] = field.relation;
      const ids = getAvatarFieldIds(model, field, fieldName);
      const idArray = [...ids].filter((id) => id != null);
      if (!idArray.length) {
        model._avatarIdsWithImage[fieldName] = new Set();
        continue;
      }
      try {
        const result = await model.orm.searchRead(
          field.relation,
          [
            ["id", "in", idArray],
            ["image_128", "!=", false],
          ],
          ["id"],
        );
        model._avatarIdsWithImage[fieldName] = new Set(result.map((r) => r.id));
      } catch (e) {
        console.warn(
          `Avatar check failed for ${fieldName}, falling back to image load:`,
          e,
        );
        model._avatarIdsWithImage[fieldName] = undefined;
      }
    }
  }
}

/**
 * Sorts the model's records by the configured sequence field (ascending), with
 * records missing a sequence value pushed to the end. No-op without a sequence
 * field.
 * @param {Object} model - The Gantt model instance
 */
function sortBySequence(model) {
  const seq = model.metaData.sequence;
  if (!seq || !Array.isArray(model.records)) return;
  const seqOf = (r) => {
    const v = (r._raw || {})[seq];
    return v == null || v === "" ? Number.MAX_SAFE_INTEGER : Number(v);
  };
  model.records.sort((a, b) => seqOf(a) - seqOf(b));
}

/**
 * Re-resolves the display names of m2m fields on a single record after a
 * refresh, so stored { id, name } objects stay in sync with the database.
 * @param {Object} model - The Gantt model instance
 * @param {Object} record - The record to refresh m2m names for
 */
async function resolveRefreshedM2M(model, record) {
  const allFields = model.metaData.fields || {};
  const m2mFields = Object.keys(record._raw).filter(
    (f) => allFields[f]?.type === "many2many",
  );
  if (!m2mFields.length) return;
  await Promise.all(
    m2mFields.map(async (fieldName) => {
      const field = allFields[fieldName];
      const val = record._raw[fieldName];
      if (!Array.isArray(val) || !val.length) return;
      const ids = val.filter((id) => typeof id === "number");
      if (!ids.length) return;
      try {
        const rows = await model.orm.searchRead(
          field.relation,
          [["id", "in", ids]],
          ["display_name"],
        );
        const nameMap = Object.fromEntries(
          rows.map((r) => [r.id, r.display_name]),
        );
        record._raw[fieldName] = ids.map((id) => ({
          id,
          name: nameMap[id] || `#${id}`,
        }));
      } catch (e) {
        console.warn(`Failed to resolve M2M names for ${fieldName}:`, e);
      }
    }),
  );
}

/**
 * Refreshes a single record from the ORM after an edit, updating its mapped
 * values, color, status, and m2m names, then rebuilding groups and notifying.
 * @param {Object} model - The Gantt model instance
 * @param {number} taskId - The record ID to refresh
 */
async function refreshRecord(model, taskId) {
  const {
    dateStart,
    dateEnd,
    coloredBy,
    sidebarLabelField,
    taskbarLabelField,
    progressField,
    statusField,
    overdueField,
  } = model.metaData || {};
  const fields = buildFieldList(model);
  if (!fields.length) return;
  try {
    const [updated] = await model.orm.searchRead(
      model.metaData.resModel,
      [["id", "=", taskId]],
      fields,
      { context: model.searchParams?.context || {} },
    );
    if (!updated) return;
    const record = model.records.find((r) => r.id === taskId);
    if (!record) return;
    let colorIndex = 0;
    if (coloredBy && !coloredBy.includes(".")) {
      if (updated[coloredBy]) {
        if (Array.isArray(updated[coloredBy])) {
          colorIndex = updated[coloredBy][0] % COLOR_PALETTE.length;
        } else if (typeof updated[coloredBy] === "number") {
          colorIndex = updated[coloredBy];
        }
      }
    }
    const sidebarLabel = sidebarLabelField
      ? cleanLabelValue(model, sidebarLabelField, updated[sidebarLabelField])
      : null;
    let recordName;
    if (sidebarLabel) {
      recordName = sidebarLabel;
    } else if (updated.display_name) {
      recordName = updated.display_name;
    } else {
      recordName = record.name;
    }
    let pillLabel;
    if (taskbarLabelField && updated[taskbarLabelField]) {
      pillLabel =
        cleanLabelValue(model, taskbarLabelField, updated[taskbarLabelField]) ||
        recordName;
    } else {
      pillLabel = recordName;
    }
    record.name = recordName;
    record.pillLabel = pillLabel;
    record.start = parseDate(updated[dateStart]);
    record.end = parseDate(updated[dateEnd]);
    record.startHasTime = hasTime(updated[dateStart]);
    record.endHasTime = hasTime(updated[dateEnd]);
    record._raw = updated;
    if (coloredBy && coloredBy.includes(".")) {
      const [rootField, subField] = coloredBy.split(".");
      const fieldDefs = model.metaData?.fields || {};
      const relatedModel = fieldDefs[rootField]?.relation;
      const rootVal = updated[rootField];
      const rootId = Array.isArray(rootVal) ? rootVal[0] : rootVal;
      if (relatedModel && rootId && subField) {
        const [related] = await model.orm.read(
          relatedModel,
          [rootId],
          [subField],
        );
        const hex = related ? related[subField] : null;
        record.color =
          hex && /^#[0-9a-fA-F]{3,8}$/.test(hex)
            ? hex
            : COLOR_PALETTE[rootId % COLOR_PALETTE.length];
      } else {
        record.color =
          COLOR_PALETTE[rootId ? rootId % COLOR_PALETTE.length : 0];
      }
    } else {
      record.color = COLOR_PALETTE[Math.abs(colorIndex) % COLOR_PALETTE.length];
    }
    record.status = statusLabel(
      model,
      statusField ? updated[statusField] : null,
    );
    record.progress = progressField ? updated[progressField] : null;
    record.isOverdue = overdueField ? Boolean(updated[overdueField]) : false;
    await resolveRefreshedM2M(model, record);
    model._buildGroups(model._groupByFields);
    model.revision++;
    model.notify();
  } catch (error) {
    console.error("Failed to refresh record:", error);
  }
}

/**
 * Fetches a single freshly-created record from the ORM so it can be inserted
 * into the Gantt without a full reload.
 * @param {Object} model - The Gantt model instance
 * @param {number} resId - The created record ID
 * @returns {Promise<Object|null>} The raw record, or null if unavailable
 */
async function fetchNewRecord(model, resId) {
  if (resId == null) return null;
  const fields = buildFieldList(model);
  if (!fields.length) return null;
  try {
    const [record] = await model.orm.searchRead(
      model.metaData.resModel,
      [["id", "=", resId]],
      fields,
      { context: model.searchParams?.context || {} },
    );
    return record || null;
  } catch (error) {
    console.warn("Failed to fetch the created record:", error);
    return null;
  }
}

/**
 * Inserts a freshly-created raw record into the model (upsert by ID), resolves
 * its m2m names, rebuilds groups, and notifies the view.
 * @param {Object} model - The Gantt model instance
 * @param {Object} rawRecord - The raw ORM record to insert
 * @returns {Promise<Object|null>} The mapped record, or null if invalid
 */
async function addNewRecord(model, rawRecord) {
  if (!rawRecord || rawRecord.id == null) return null;
  const record = mapRecord(model, rawRecord);
  const idx = model.records.findIndex((r) => r.id === record.id);
  if (idx === -1) {
    model.records.push(record);
    if (typeof model.count === "number") model.count++;
  } else {
    model.records[idx] = record;
  }
  try {
    await resolveRefreshedM2M(model, record);
  } catch (error) {
    console.warn("Failed to resolve M2M names for the new record:", error);
  }
  model._buildGroups(model._groupByFields);
  model.revision++;
  model.notify();
  return record;
}

/**
 * Deletes a record by calling the ORM unlink method.
 * Shows a confirmation dialog before deletion.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The task record to delete
 */
async function deleteTaskBar(renderer, record) {
  const { resModel } = renderer.model.metaData;
  renderer.dialogService.add(ConfirmationDialog, {
    body: _t(
      "Are you sure you want to delete %s?",
      record.name || _t("this record"),
    ),
    confirmLabel: _t("Delete"),
    cancelLabel: _t("Cancel"),
    confirm: async () => {
      try {
        await renderer.orm.unlink(resModel, [record.id]);
        await renderer.model.load({
          ...renderer.model.searchParams,
          offset: renderer.model.offset,
          limit: renderer.model.limit,
        });
        renderer.renderGantt();
        renderer.notificationService.add("", {
          title: _t("%s deleted successfully", record.name || _t("record")),
          type: "info",
        });
      } catch (error) {
        renderer.notificationService.add(
          _t("Failed to delete record: ") + extractErrorMessage(error),
          { type: "danger" },
        );
      }
    },
    cancel: () => {},
  });
}

/**
 * Opens the form view for editing a record.
 * After the form is closed, refreshes the record data and re-renders.
 *
 * @param {Object} renderer - The GanttRenderer instance
 * @param {Object} record - The task record to edit
 * @param {string} [target='new'] - Action target: "new" opens a modal dialog,
 *   "current" replaces the current view with the full form.
 */
async function openFormView(renderer, record, target = "new") {
  const { resModel } = renderer.model.metaData;
  try {
    await renderer.actionService.doAction(
      {
        type: "ir.actions.act_window",
        res_model: resModel,
        res_id: record.id,
        views: [[false, "form"]],
        target,
      },
      {
        onClose: async () => {
          try {
            await renderer.model.refreshRecord(record.id);
            renderer.renderGantt();
          } catch (e) {
            console.error("Failed to reload after form edit:", e);
          }
        },
      },
    );
  } catch (error) {
    console.error("Failed to open form view:", error);
    try {
      renderer.notificationService.add(
        _t("Failed to open form view: ") + extractErrorMessage(error),
        { type: "danger" },
      );
    } catch (e) {
      console.warn("Notification failed:", e);
    }
  }
}

export {
  buildFieldList,
  fetchRecords,
  mapRecord,
  mapRecords,
  statusLabel,
  resolveRelatedColors,
  resolveM2MNames,
  resolveAvatarModels,
  sortBySequence,
  resolveRefreshedM2M,
  refreshRecord,
  fetchNewRecord,
  addNewRecord,
  deleteTaskBar,
  openFormView,
};
