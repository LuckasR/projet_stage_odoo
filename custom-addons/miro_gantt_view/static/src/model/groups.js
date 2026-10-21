/** @odoo-module **/

import {
    groupRecords,
    flattenGroups,
    findGroupByPath,
    captureGroupOrder,
    applyGroupOrder,
} from '@miro_gantt_view/utils/group_by';

/**
 * Toggles the expanded/collapsed state of a group and notifies the view.
 * @param {Object} model - The Gantt model instance
 * @param {string} key - The group path to toggle
 */
function toggleGroup(model, key) {
    if (model.collapsedGroups.has(key)) {
        model.collapsedGroups.delete(key);
    } else {
        model.collapsedGroups.add(key);
    }
    model.notify();
}

/**
 * Returns whether a group is currently collapsed.
 * @param {Object} model - The Gantt model instance
 * @param {string} key - The group path
 * @returns {boolean} True when the group is collapsed
 */
function isGroupCollapsed(model, key) {
    return model.collapsedGroups.has(key);
}

/**
 * Places a record at the top (index 0) of a group's persisted order.
 * @param {Object} model - The Gantt model instance
 * @param {number} recordId - The record ID to move
 * @param {string|null} groupPath - The target group path (null for ungrouped)
 */
function setRecordOnTopOfGroup(model, recordId, groupPath) {
    setRecordInGroupAtPosition(model, recordId, groupPath, 0);
}

/**
 * Persists the session order of records within a group (or the ungrouped
 * list) by storing the reordered record ID list on the model. The record is
 * removed from its previous position and inserted at the requested index.
 * @param {Object} model - The Gantt model instance
 * @param {number} recordId - The record ID to reposition
 * @param {string|null} groupPath - The group path (null for ungrouped)
 * @param {number} index - The target insertion index
 */
function setRecordInGroupAtPosition(model, recordId, groupPath, index) {
    if (recordId == null) return;
    const isUngrouped = groupPath == null || String(groupPath) === model._ungroupedOrderKey;
    const key = isUngrouped ? model._ungroupedOrderKey : String(groupPath);
    const group = isUngrouped ? null : findGroupByPath(model.groups || [], String(groupPath));
    const base = isUngrouped
        ? model.records.map((r) => r.id)
        : group && Array.isArray(group.records)
            ? group.records.map((r) => r.id)
            : model._groupRecordOrder[key] || [];
    const list = base.filter((id) => id !== recordId);
    const idx = Math.max(0, Math.min(index == null ? 0 : index, list.length));
    list.splice(idx, 0, recordId);
    model._groupRecordOrder[key] = list;
}

/**
 * Computes the record ID order that results from moving a record to a given
 * index within a group (or the ungrouped list). Used to derive sequence values
 * before persisting a reorder.
 * @param {Object} model - The Gantt model instance
 * @param {string|null} groupPath - The group path (null for ungrouped)
 * @param {number} movedId - The record ID being moved
 * @param {number} index - The target insertion index
 * @returns {number[]} The resulting ordered record ID list
 */
function computeGroupOrder(model, groupPath, movedId, index) {
    const isUngrouped = groupPath == null || String(groupPath) === model._ungroupedOrderKey;
    if (isUngrouped) {
        const ids = (model.records || []).map((r) => r.id).filter((id) => id !== movedId);
        const idx = Math.max(0, Math.min(index == null ? 0 : index, ids.length));
        ids.splice(idx, 0, movedId);
        return ids;
    }
    const group = findGroupByPath(model.groups || [], groupPath);
    if (!group || !Array.isArray(group.records)) return [movedId];
    const ids = group.records.map((r) => r.id).filter((id) => id !== movedId);
    const idx = Math.max(0, Math.min(index == null ? 0 : index, ids.length));
    ids.splice(idx, 0, movedId);
    return ids;
}

/**
 * Persists a group's reordered record ID list to the database by writing the
 * configured sequence field on each record (1-based index). No-op when no
 * sequence field is configured.
 * @param {Object} model - The Gantt model instance
 * @param {string|null} groupPath - The group path (unused for persistence)
 * @param {number[]} orderIds - The ordered record ID list
 */
async function persistGroupOrder(model, groupPath, orderIds) {
    const seq = model.metaData.sequence;
    if (!seq || !Array.isArray(orderIds)) return;
    const entries = orderIds.map((id, index) => ({ id, vals: { [seq]: index + 1 } }));
    await batchWrite(model, model.metaData.resModel, entries);
}

/**
 * Writes a list of ORM write entries efficiently by grouping entries that share
 * identical values into a single write call per unique value set.
 * @param {Object} model - The Gantt model instance
 * @param {string} resModel - The model name to write on
 * @param {Array<{id: number, vals: Object}>} entries - Write entries
 */
async function batchWrite(model, resModel, entries) {
    if (!entries || !entries.length) return;
    const byVals = new Map();
    for (const entry of entries) {
        if (!entry || entry.id == null) continue;
        const key = JSON.stringify(entry.vals);
        if (!byVals.has(key)) byVals.set(key, { ids: [], vals: entry.vals });
        byVals.get(key).ids.push(entry.id);
    }
    for (const { ids, vals } of byVals.values()) {
        try {
            await model.orm.write(resModel, ids, vals);
        } catch (error) {
            console.warn('Failed to batch write records:', error);
        }
    }
}

/**
 * Builds a create context (default_* keys) from a group path so that a task
 * created on a group's row inherits the group's field values. Handles M2M
 * fields ([[6,0,ids]]), relational/integer/monetary fields, and string keys.
 * @param {Object} model - The Gantt model instance
 * @param {string|null} groupPath - The group path (null/no fields returns base)
 * @param {Object} [baseContext] - Extra default context to start from
 * @returns {Object} Context with default_* keys for each group-by field
 */
function buildGroupContext(model, groupPath, baseContext = {}) {
    const ctx = { ...(baseContext || {}) };
    if (groupPath == null || groupPath === 'undefined') return ctx;
    const fields = model._groupByFields || [];
    if (!fields.length) return ctx;
    const parts = String(groupPath).split('/').filter((p) => p && p !== 'undefined');
    const fieldDefs = model.metaData.fields || {};
    for (let i = 0; i < parts.length; i++) {
        const field = fields[i];
        if (!field) continue;
        const rawKey = parts[i];
        if (rawKey === '__ungrouped__' || rawKey === 'false' || rawKey === 'null') continue;
        const fdef = fieldDefs[field];
        if (fdef?.type === 'many2many') {
            const ids = rawKey.split(',').map(Number).filter((n) => Number.isFinite(n));
            if (ids.length) ctx[`default_${field}`] = [[6, 0, ids]];
        } else if (['many2one', 'one2many', 'integer', 'monetary'].includes(fdef?.type)) {
            const num = Number(rawKey);
            ctx[`default_${field}`] = Number.isFinite(num) ? num : rawKey;
        } else {
            ctx[`default_${field}`] = rawKey;
        }
    }
    return ctx;
}

/**
 * Sorts the model's records in place according to the active sort order. With
 * no sort order, falls back to ascending record ID. Supports sorting by name,
 * start/end date, or status; "desc" reverses the resulting order.
 * @param {Object} model - The Gantt model instance
 */
function sortRecords(model) {
    const sortOrder = model._sortOrder;
    if (!sortOrder) {
        model.records.sort((a, b) => a.id - b.id);
        return;
    }
    const sortField = model._sortField || 'name';
    model.records.sort((a, b) => {
        let comparison = 0;
        if (sortField === 'name') {
            comparison = a.name.localeCompare(b.name);
        } else if (sortField === 'dateStart' || sortField === 'start') {
            comparison = (a.start || new Date(0)).getTime() - (b.start || new Date(0)).getTime();
        } else if (sortField === 'dateEnd' || sortField === 'end') {
            comparison = (a.end || new Date(0)).getTime() - (b.end || new Date(0)).getTime();
        } else if (sortField === 'status') {
            comparison = (a.status || '').localeCompare(b.status || '');
        }
        return sortOrder === 'asc' ? comparison : -comparison;
    });
}

/**
 * Sets the active sort order + field on the model, re-sorts the records and
 * group tree, rebuilds the groups, and notifies the view.
 * @param {Object} model - The Gantt model instance
 * @param {string|null} sortOrder - "asc", "desc", or null to clear sorting
 * @param {string} [sortField] - The field to sort by (default "name")
 */
function setSortOrder(model, sortOrder, sortField = 'name') {
    model._sortOrder = sortOrder;
    model._sortField = sortField;
    sortRecords(model);
    buildGroups(model, model._groupByFields);
    model.notify();
}

/**
 * Recursively sorts sibling groups by name in the given order, including
 * nested child groups.
 * @param {Object[]} groups - The group tree (mutated in place)
 * @param {string} order - "asc" or "desc"
 */
function sortGroupsByName(groups, order) {
    if (!Array.isArray(groups)) return;
    groups.sort((a, b) => {
        const cmp = (a.name || '').localeCompare(b.name || '');
        return order === 'asc' ? cmp : -cmp;
    });
    for (const g of groups) {
        if (Array.isArray(g.children)) sortGroupsByName(g.children, order);
    }
}

/**
 * Reorders the model's records and each leaf group's records according to the
 * persisted session order captured in `model._groupRecordOrder`. Only applied
 * when no sequence field is configured (records are persisted anyway) and no
 * explicit sort is active.
 * @param {Object} model - The Gantt model instance
 */
function applyGroupRecordOrder(model) {
    if (!model._groupRecordOrder) return;
    const ungroupedIds = model._groupRecordOrder[model._ungroupedOrderKey];
    if (Array.isArray(ungroupedIds)) {
        const idSet = new Set(ungroupedIds);
        const ordered = [];
        const rest = [];
        for (const rec of model.records) {
            (idSet.has(rec.id) ? ordered : rest).push(rec);
        }
        if (ordered.length) {
            ordered.sort((a, b) => ungroupedIds.indexOf(a.id) - ungroupedIds.indexOf(b.id));
            model.records = [...ordered, ...rest];
        }
    }
    if (!model.groups) return;
    for (const [path, ids] of Object.entries(model._groupRecordOrder)) {
        if (path === model._ungroupedOrderKey) continue;
        const group = findGroupByPath(model.groups, path);
        if (!group || group.isParent || !Array.isArray(group.records)) continue;
        const idSet = new Set(ids);
        const ordered = [];
        const rest = [];
        for (const rec of group.records) {
            (idSet.has(rec.id) ? ordered : rest).push(rec);
        }
        if (!ordered.length) continue;
        ordered.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
        group.records = [...ordered, ...rest];
    }
}

/**
 * Rebuilds the group tree from the current records and group-by fields, then
 * reapplies the preserved group/record order. Falls back to no grouping when
 * no group-by fields are set. Notifies-dependent state (group order) is
 * re-established after loading.
 * @param {Object} model - The Gantt model instance
 * @param {string[]} prevGroupBy - The previously active group-by fields
 * @param {boolean} [forceRebuild] - Force refreshing the group order
 */
function buildGroups(model, prevGroupBy, forceRebuild = false) {
    const rawGroupByFields = model._groupByFields;
    if (rawGroupByFields.length) {
        const tree = groupRecords(model.records, rawGroupByFields);
        model._allGroupsFlat = tree ? flattenGroups(tree) : [];
        model.groups = tree;
    } else {
        model.groups = null;
        model._allGroupsFlat = [];
    }
    const userGroupedFromSearchBar = Array.isArray(model.searchParams?.groupBy) && model.searchParams.groupBy.length > 0;
    if (userGroupedFromSearchBar && (forceRebuild || JSON.stringify(prevGroupBy) !== JSON.stringify(rawGroupByFields))) {
        model._groupOrder = null;
    }
    if (model.groups && !model._sortOrder) {
        if (!model._groupOrder) {
            model._groupOrder = captureGroupOrder(model.groups);
        } else {
            applyGroupOrder(model.groups, model._groupOrder);
        }
    }
    if (model.groups && model._sortOrder) {
        sortGroupsByName(model.groups, model._sortOrder);
    }
    if (!model.metaData.sequence && !model._sortOrder) {
        applyGroupRecordOrder(model);
    }
}

/**
 * Finds a group in the tree by its slash-separated path.
 * @param {Object} model - The Gantt model instance
 * @param {string} path - The group path to find
 * @returns {Object|null} The matching group, or null
 */
function _findGroupByPath(model, path) {
    return findGroupByPath(model.groups || [], path);
}

export {
    buildGroups,
    toggleGroup,
    isGroupCollapsed,
    setRecordOnTopOfGroup,
    setRecordInGroupAtPosition,
    computeGroupOrder,
    persistGroupOrder,
    batchWrite,
    buildGroupContext,
    setSortOrder,
    sortRecords,
    _findGroupByPath,
};
