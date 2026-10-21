/** @odoo-module **/

import { computeBandHeight } from '@miro_gantt_view/utils/config';

/**
 * Converts a raw group-by field value from a record into an array of { key, label } entries.
 * Handles several input formats:
 *   - Array of { id, ... } objects (M2M): each item becomes one entry.
 *   - Array of [id, name] pairs: extracts first pair only.
 *   - Scalar value (string/number/boolean): single entry.
 *   - undefined/null/false: returns [{ key: "__ungrouped__", label: "None" }].
 *
 * @param {*} val - The raw field value from the record
 * @returns {Array<{key: string|number, label: string}>} Array of group entries
 */
function getGroupEntries(val) {
    if (Array.isArray(val)) {
        // M2M format: array of { id, name } objects
        if (val.length > 0 && typeof val[0] === 'object' && val[0] !== null && 'id' in val[0]) {
            return val.map((item) => ({ key: item.id, label: item.name || `Group ${item.id}` }));
        }
        // M2O format: array of [id, name]
        if (val.length >= 1) {
            return [{ key: val[0] || 0, label: val[1] || `Group ${val[0]}` }];
        }
        return [{ key: '__ungrouped__', label: 'None' }];
    }
    if (val !== undefined && val !== null && val !== false) {
        return [{ key: val, label: String(val) }];
    }
    return [{ key: '__ungrouped__', label: 'None' }];
}

/**
 * Ensures a group with the given key exists in the groupMap and groups array.
 * This is the standard deduplication helper: if the key already exists in the map,
 * returns the existing group; otherwise creates a new group, inserts it into both
 * the map and the array, and returns it.
 *
 * @param {Map} groupMap - Map of key -> group for deduplication
 * @param {Object[]} groups - Array of groups to append to if new
 * @param {string|number} key - The group key
 * @param {string} label - The group display label
 * @param {string} field - The field name this group is based on
 * @returns {Object} The existing or newly created group object
 */
function ensureGroup(groupMap, groups, key, label, field) {
    if (!groupMap.has(key)) {
        const group = { key, name: label, field, records: [] };
        groupMap.set(key, group);
        groups.push(group);
    }
    return groupMap.get(key);
}

/**
 * Builds a nested group tree from records using the specified field hierarchy.
 * Each level groups by one field; deeper fields create child groups.
 * For M2M fields, a record appears in each matching group (one per assigned user).
 *
 * The tree structure uses:
 *   - group.path: slash-separated path (e.g. "12/5") for DOM identification
 *   - group.depth: nesting level (0 = root)
 *   - group.isParent: true if the group has deeper subgroups
 *   - group.children: sub-groups (null when isParent is false)
 *   - group.records: contained records (only on leaf groups, deleted after children are created)
 *
 * @param {Object[]} records - The task records to group
 * @param {string[]} groupByFields - Ordered field names (outermost first)
 * @param {number} depth - Recursion depth (internal)
 * @param {string} parentPath - Parent path prefix (internal)
 * @returns {Object[]} Nested group tree
 */
function buildGroupTree(records, groupByFields, depth = 0, parentPath = '') {
    if (!groupByFields || groupByFields.length === 0) return [];

    const [field, ...restFields] = groupByFields;
    const groups = [];
    const groupMap = new Map();

    // Distribute records into groups based on the current field
    for (const record of records) {
        const raw = record._raw || {};
        const entries = getGroupEntries(raw[field]);
        for (const { key, label } of entries) {
            ensureGroup(groupMap, groups, key, label, field).records.push(record);
        }
    }

    // Recursively build child groups for each parent group
    for (const group of groups) {
        const path = parentPath ? `${parentPath}/${group.key}` : `${group.key}`;
        group.path = path;
        group.depth = depth;

        if (restFields.length > 0) {
            group.children = buildGroupTree(group.records, restFields, depth + 1, path);
            group.isParent = group.children.length > 0;
            if (!group.isParent) {
                group.children = null;
            } else {
                delete group.records; // Clean up intermediate records array
            }
        } else {
            group.children = null;
            group.isParent = false;
        }
    }

    return groups;
}

/**
 * Groups records by the given field(s). Returns a nested tree when multiple
 * fields are provided, or a flat array for a single field.
 *
 * @param {Object[]} records - The task records to group
 * @param {string[]} groupByFields - Ordered field names for grouping
 * @returns {Object[]} Nested group tree
 */
export function groupRecords(records, groupByFields) {
    return buildGroupTree(records, groupByFields || []);
}

/**
 * Recursively flattens a nested group tree into a row layout for rendering.
 * Parent groups are rendered as collapsible headers; leaf groups show headers
 * followed by their task records packed into a single band.
 * Skips groups/records that fall outside the visible date range.
 *
 * @param {Object[]} groups - The nested group tree
 * @param {{start: Date, end: Date}} dateRange - Visible date range
 * @param {Function} isGroupCollapsed - Function(groupPath) => boolean to check collapse state
 * @returns {Object[]} Array of layout items: { type: "group"|"band", group, ... }
 */
function flattenGroupTree(groups, dateRange, isGroupCollapsed, grid = {}) {
    const layout = [];
    const { start, end } = dateRange;

    for (const group of groups) {
        if (group.isParent) {
            const visibleCount = countVisibleInTree(group, dateRange);
            if (visibleCount === 0) continue;

            const groupStart = computeGroupStart(group);
            layout.push({
                type: 'group',
                group,
                visibleCount,
                groupStart: groupStart ? groupStart.start : null,
                groupStartHasTime: groupStart ? groupStart.startHasTime : false,
                groupEnd: computeGroupEnd(group),
                groupDuration: computeGroupDuration(group),
            });
            if (!isGroupCollapsed(group.path)) {
                const childLayout = flattenGroupTree(group.children, dateRange, isGroupCollapsed, grid);
                layout.push(...childLayout);
            }
        } else {
            // Filter records to only those overlapping with the visible date range
            const visibleRecords = group.records.filter((r) => r.start < end && r.end >= start);
            if (visibleRecords.length === 0) continue;

            const groupStart = computeGroupStart(group);
            layout.push({
                type: 'group',
                group,
                visibleCount: visibleRecords.length,
                groupStart: groupStart ? groupStart.start : null,
                groupStartHasTime: groupStart ? groupStart.startHasTime : false,
                groupEnd: computeGroupEnd(group),
                groupDuration: computeGroupDuration(group),
            });
            if (!isGroupCollapsed(group.path)) {
                layout.push(buildBand(group, visibleRecords, grid));
            }
        }
    }
    return layout;
}

/**
 * Computes the earliest start date of a group subtree.
 * Walks the group tree (parent groups recurse into children, leaf groups
 * inspect their records) and returns the minimum valid start date. Records
 * with an unset/invalid start (epoch, getTime() === 0) are skipped.
 *
 * @param {Object} group - The group to compute the start for
 * @returns {{start: Date, startHasTime: boolean}|null} The earliest start
 *          date with its time flag, or null when no valid start exists
 */
function computeGroupStart(group) {
    let best = null;
    let bestHasTime = false;
    const visit = (g) => {
        if (g.isParent) {
            for (const child of g.children || []) visit(child);
            return;
        }
        for (const r of g.records || []) {
            if (!r.start || r.start.getTime() === 0) continue;
            if (!best || r.start < best) {
                best = r.start;
                bestHasTime = Boolean(r.startHasTime);
            }
        }
    };
    visit(group);
    return best ? { start: best, startHasTime: bestHasTime } : null;
}

/**
 * Computes the latest end date of a group subtree.
 * Walks the group tree (parent groups recurse into children, leaf groups
 * inspect their records) and returns the maximum valid end date. Records
 * with an unset/invalid end (epoch, getTime() === 0) are skipped.
 *
 * @param {Object} group - The group to compute the end for
 * @returns {Date|null} The latest end date, or null when no valid end exists
 */
function computeGroupEnd(group) {
    let best = null;
    const visit = (g) => {
        if (g.isParent) {
            for (const child of g.children || []) visit(child);
            return;
        }
        for (const r of g.records || []) {
            if (!r.end || r.end.getTime() === 0) continue;
            if (!best || r.end > best) best = r.end;
        }
    };
    visit(group);
    return best;
}

/**
 * Computes the total duration of a group subtree.
 * Sums the `duration` value of every record in the tree (parent groups recurse
 * into children, leaf groups inspect their records). Records without a numeric
 * duration are skipped.
 *
 * @param {Object} group - The group to compute the duration for
 * @returns {number} The summed duration (0 when no record has a duration)
 */
function computeGroupDuration(group) {
    let total = 0;
    const visit = (g) => {
        if (g.isParent) {
            for (const child of g.children || []) visit(child);
            return;
        }
        for (const r of g.records || []) {
            const d = typeof r.duration === 'number' && isFinite(r.duration) ? r.duration : 0;
            total += d;
        }
    };
    visit(group);
    return total;
}

/**
 * Counts how many records in a group subtree are visible within the given date range.
 * Recursively walks through child groups to accumulate the total.
 *
 * @param {Object} group - The group to count records for
 * @param {{start: Date, end: Date}} dateRange - Visible date range
 * @returns {number} Number of visible records in this group and its children
 */
function countVisibleInTree(group, dateRange) {
    const { start, end } = dateRange;
    if (group.isParent) {
        return group.children.reduce((sum, child) => sum + countVisibleInTree(child, dateRange), 0);
    }
    return group.records.filter((r) => r.start < end && r.end >= start).length;
}

/**
 * Builds a band layout item from a set of visible records sharing the same row
 * group (a leaf group, or all records in ungrouped mode). Each record gets its
 * OWN row via `assignPillLevels`; every record receives an explicit
 * `_laneIndex` and `_maxPillLevels` used by the renderer to compute its Y
 * offset. The band height grows with the number of records.
 *
 * @param {Object|null} group - The leaf group, or null in ungrouped mode
 * @param {Object[]} records - Records overlapping the visible date range
 * @param {{laneStore?: Map}} [grid] - Grid context used to persist each
 *        taskbar's row across renders/reloads
 * @returns {Object} Band item: { type, group, records, lanes, height }
 */
function buildBand(group, records, grid = {}) {
    const { levelMap, maxLevels } = assignPillLevels(records || [], {
        ...grid,
        groupKey: group ? String(group.path) : null,
    });
    for (const record of records || []) {
        record._laneIndex = levelMap.get(record.id) || 0;
        record._maxPillLevels = maxLevels;
    }
    return {
        type: 'band',
        group,
        records: records || [],
        laneMap: levelMap,
        lanes: maxLevels,
        height: computeBandHeight(maxLevels),
    };
}

/**
 * Builds the layout for rendering (groups + task bands).
 * Filters records to only include those overlapping with the visible date range.
 * For grouped mode, skips empty groups and tracks visible count per group.
 *
 * @param {Object[]} records - All task records
 * @param {Object[]|null} groups - Group tree or null
 * @param {{start: Date, end: Date}} dateRange - Visible date range
 * @param {boolean} hasGroups - Whether groups are configured
 * @param {Function} isGroupCollapsed - Function(groupPath) => boolean
 * @param {{laneStore?: Map}} [grid] - Grid context used to persist each
 *        taskbar's row across renders/reloads
 * @returns {Object[]} Layout items: { type: "band"|"group", ... }
 */
export function computeRowLayout(records, groups, dateRange, hasGroups, isGroupCollapsed, grid = {}) {
    const { start, end } = dateRange;
    if (!grid.rangeStart) grid = { ...grid, rangeStart: start };
    if (!hasGroups || !groups) {
        // No grouping: pack all visible records into a single band
        const visibleRecords = records.filter((r) => r.start < end && r.end >= start);
        return visibleRecords.length ? [buildBand(null, visibleRecords, grid)] : [];
    }
    // Grouped mode: flatten the group tree into band layout items
    return flattenGroupTree(groups, dateRange, isGroupCollapsed, grid);
}

/**
 * Returns the leaf-group path for a given record in the nested group tree.
 * Searches depth-first through the group hierarchy. If the record is not found
 * in any leaf group, returns null.
 * This is used during drag operations to determine the record's original group
 * for cross-group move detection.
 *
 * @param {Object} record - The task record to find
 * @param {Object[]} groups - The nested group tree
 * @returns {string|null} The group path, or null if not found
 */
export function getRecordGroupKey(record, groups) {
    if (!groups) return null;
    for (const group of groups) {
        if (group.isParent) {
            const found = getRecordGroupKey(record, group.children);
            if (found) return found;
        } else if (group.records.some((r) => r.id === record.id)) {
            return group.path;
        }
    }
    return null;
}

/**
 * Flattens all groups (including nested) into a single array.
 * Used to build the flat _allGroupsFlat array for fast group lookups
 * during drag-and-drop target resolution.
 *
 * @param {Object[]} groups - The nested group tree
 * @returns {Object[]} Flat array of all groups
 */
export function flattenGroups(groups) {
    const result = [];
    for (const group of groups) {
        result.push(group);
        if (group.isParent && group.children) {
            result.push(...flattenGroups(group.children));
        }
    }
    return result;
}

/**
 * Captures the current child ordering of every group level into a map.
 * The map keys are the parent group paths ('' for the root level) and the
 * values are the ordered arrays of child group keys. Used as the session
 * fallback that keeps groups at their initial position across reloads.
 *
 * @param {Object[]} groups - The nested group tree
 * @param {string} parentPath - Parent path prefix (internal)
 * @param {Map<string, (string|number)[]>} map - Accumulated order map (internal)
 * @returns {Map<string, (string|number)[]>} The order map
 */
export function captureGroupOrder(groups, parentPath = '', map = new Map()) {
    const keys = groups.map((g) => g.key);
    map.set(parentPath, keys);
    for (const group of groups) {
        if (group.isParent && group.children) {
            captureGroupOrder(group.children, group.path, map);
        }
    }
    return map;
}

/**
 * Reorders the children of every group level according to the preserved order.
 * Known keys keep their preserved relative position; unknown keys (groups
 * created after the order was captured) are appended at the end in their
 * natural derived order. The map is updated with the resulting order so that
 * new groups are persisted too.
 *
 * @param {Object[]} groups - The nested group tree
 * @param {Map<string, (string|number)[]>} orderMap - The preserved order map
 * @param {string} parentPath - Parent path prefix (internal)
 * @returns {Map<string, (string|number)[]>} The updated order map
 */
export function applyGroupOrder(groups, orderMap, parentPath = '') {
    const preserved = orderMap.get(parentPath);
    if (preserved && preserved.length) {
        const pos = new Map(preserved.map((key, i) => [String(key), i]));
        groups.sort((a, b) => {
            const posA = pos.get(String(a.key));
            const posB = pos.get(String(b.key));
            if (posA !== undefined && posB !== undefined) return posA - posB;
            if (posA !== undefined) return -1;
            if (posB !== undefined) return 1;
            return 0;
        });
        orderMap.set(parentPath, groups.map((g) => g.key));
    }
    for (const group of groups) {
        if (group.isParent && group.children) {
            applyGroupOrder(group.children, orderMap, group.path);
        }
    }
    return orderMap;
}

/**
 * Assigns the vertical row of each task bar within a group of records.
 * Every taskbar gets its OWN row and KEEPS it: rows are persisted in the
 * `laneStore` (keyed by group + record id), so re-renders and drag & drops
 * never change a taskbar's row. In particular, dragging a taskbar left/right
 * (changing its dates within the same group) keeps it on its row.
 *
 * Assignment rule:
 * - A record with a stored row that is still free keeps it.
 * - New records (no stored row) receive the first free row, in start-date
 *   order, so the first render still stacks the rows chronologically.
 *
 * @param {Object[]} records - Records sharing the same band (must have .start)
 * @param {{laneStore?: Map, groupKey?: string|null}} [grid] - Grid context:
 *        - laneStore persists row indices (key `${groupKey}:${recordId}`) so
 *          rows are stable across renders/reloads
 *        - groupKey distinguishes the band in the laneStore
 * @returns {{levelMap: Map<number, number>, maxLevels: number}}
 *   levelMap: record.id -> row index (0-based)
 *   maxLevels: total number of rows (== number of records)
 */
function assignPillLevels(records, grid = {}) {
    const { laneStore, groupKey = null } = grid;
    const laneKey = (id) => `${groupKey ?? ''}:${id}`;
    const storeGet = (id) => (laneStore ? laneStore.get(laneKey(id)) : null);
    const storeSet = (id, lane) => {
        if (laneStore) laneStore.set(laneKey(id), lane);
    };

    if (!records || records.length === 0) {
        return { levelMap: new Map(), maxLevels: 1 };
    }
    if (records.length === 1) {
        const singleMap = new Map();
        singleMap.set(records[0].id, 0);
        storeSet(records[0].id, 0);
        return { levelMap: singleMap, maxLevels: 1 };
    }

    const sorted = [...records].sort((a, b) => a.start.getTime() - b.start.getTime());

    const levelMap = new Map();
    const usedLanes = new Set();

    for (const rec of sorted) {
        const prev = storeGet(rec.id);
        let level;
        if (prev != null && !usedLanes.has(prev)) {
            // The taskbar keeps its row (dragging left/right never changes it).
            level = prev;
        } else {
            // New record (or a row already taken): land on the first free row.
            level = 0;
            let _maxIter = records.length + 1;
            while (usedLanes.has(level) && --_maxIter > 0) level++;
        }
        levelMap.set(rec.id, level);
        usedLanes.add(level);
        storeSet(rec.id, level);
    }

    // Compact lanes: remap used lanes to 0-based contiguous sequence.
    // When a record moves out of a group, its stored lane may leave a gap
    // (e.g., {1, 2} instead of {0, 1}). Without compaction, lane 0 is
    // empty and the band height / Y offsets are wrong.
    const sortedLanes = [...usedLanes].sort((a, b) => a - b);
    const remap = new Map(sortedLanes.map((old, i) => [old, i]));
    for (const [id, oldLevel] of levelMap) {
        const newLevel = remap.get(oldLevel);
        if (newLevel !== oldLevel) {
            levelMap.set(id, newLevel);
            storeSet(id, newLevel);
        }
    }

    return { levelMap, maxLevels: Math.max(1, sortedLanes.length) };
}

/**
 * Finds a group by its path in the nested tree.
 * Performs a depth-first search.
 *
 * @param {Object[]} groups - The nested group tree
 * @param {string} path - The slash-separated group path to find
 * @returns {Object|null} The group object, or null if not found
 */
export function findGroupByPath(groups, path) {
    for (const group of groups) {
        if (group.path === path) return group;
        if (group.isParent && group.children) {
            const found = findGroupByPath(group.children, path);
            if (found) return found;
        }
    }
    return null;
}
