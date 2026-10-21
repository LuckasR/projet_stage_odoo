/** @odoo-module **/

import { Model } from '@web/model/model';
import { ZOOM_CONFIG } from '@miro_gantt_view/utils/config';
import {
    buildFieldList as _buildFieldListFn,
    fetchRecords as _fetchRecordsFn,
    mapRecords as _mapRecordsFn,
    resolveRelatedColors as _resolveRelatedColorsFn,
    resolveM2MNames as _resolveM2MNamesFn,
    resolveAvatarModels as _resolveAvatarModelsFn,
    sortBySequence as _sortBySequenceFn,
    refreshRecord as _refreshRecordFn,
    fetchNewRecord as _fetchNewRecordFn,
    addNewRecord as _addNewRecordFn,
} from '@miro_gantt_view/model/records';
import {
    buildGroups as _buildGroupsFn,
    toggleGroup as _toggleGroupFn,
    isGroupCollapsed as _isGroupCollapsedFn,
    setRecordOnTopOfGroup as _setRecordOnTopOfGroupFn,
    setRecordInGroupAtPosition as _setRecordInGroupAtPositionFn,
    computeGroupOrder as _computeGroupOrderFn,
    persistGroupOrder as _persistGroupOrderFn,
    buildGroupContext as _buildGroupContextFn,
    setSortOrder as _setSortOrderFn,
    sortRecords as _sortRecordsFn,
    _findGroupByPath as _findGroupByPathFn,
} from '@miro_gantt_view/model/groups';

export class GanttModel extends Model {
    /**
     * Initializes model state from the parsed parameters: zoom scales, default
     * filter, sequence field detection, and empty records/groups containers.
     * @param {Object} params - view properties (archInfo + fields + resModel)
     */
    setup(params) {
        let scaleIds = params.availableFilters || [];
        if (typeof scaleIds[0] === 'object') {
            scaleIds = scaleIds.map((s) => s.id || s);
        }
        const scales = (scaleIds.length ? scaleIds : ['day', 'week', 'month', 'year']).map(
            (s) => ZOOM_CONFIG[s] || ZOOM_CONFIG.month
        );
        const defaultFilter = params.defaultFilter || 'month';
        // The sidebar_label_field stays the pinned "name" column (always
        // first, never toggleable): it is excluded from the dynamic
        // `sidebar_column_fields` (and so is "id", always available) to avoid
        // duplicating it as a regular info column.
        const sidebarLabelField = params.sidebarLabelField || '';
        const excludedColumns = new Set(
            [sidebarLabelField, 'id'].filter(Boolean)
        );
        this.metaData = {
            ...params,
            scales,
            scale: ZOOM_CONFIG[defaultFilter] || ZOOM_CONFIG.month,
            sidebarColumnFieldDefs: (params.sidebarColumnFields || [])
                .filter((fname) => !excludedColumns.has(fname))
                .map((fname) => {
                    const def = (params.fields || {})[fname] || {};
                    return {
                        name: fname,
                        label: def.string || fname,
                        type: def.type || 'char',
                        selection: def.selection || null,
                        digits: def.digits || null,
                    };
                }),
        };
        // The sidebar header title (defaultTitle) follows the label of the
        // sidebar_label_field: the pinned name column displays the human
        // readable field label instead of a hard-coded arch title.
        if (this.metaData.sidebarLabelField && params.fields) {
            const labelFieldDef = params.fields[this.metaData.sidebarLabelField];
            if (labelFieldDef && labelFieldDef.string) {
                this.metaData.defaultTitle = labelFieldDef.string;
            }
        }
        if (!this.metaData.sequence && params.fields) {
            const sequenceField = Object.entries(params.fields).find(
                ([fieldName, fieldDef]) =>
                    fieldName === 'sequence' && fieldDef && fieldDef.type === 'integer' && !fieldDef.readonly
            );
            if (sequenceField) this.metaData.sequence = sequenceField[0];
        }
        this.records = [];
        this.groups = null;
        this._allGroupsFlat = [];
        this.searchParams = null;
        this.collapsedGroups = new Set();
        this._groupRecordOrder = {};
        this._laneAssignments = new Map();
        this._groupOrder = null;
        this.offset = 0;
        this.limit = 81;
        this.count = 0;
        this._groupByFields = [];
        this._sortOrder = null;
        this._sortField = 'name';
        this._loadVersion = 0;
        this._ungroupedOrderKey = '__ungrouped__';
        this.loading = false;
        this.loadError = null;
        this.revision = 0;
    }

    /**
     * Loads records for the given search params: fetches, maps, resolves colors
     * / m2m names / avatars, sorts, and rebuilds groups, then notifies the view.
     * Stale responses (superseded by a newer load) are discarded.
     * @param {Object} searchParams - Domain/context/groupBy/offset/limit
     */
    async load(searchParams) {
        const version = ++this._loadVersion;
        const prevGroupBy = this._groupByFields;
        this.loading = true;
        this.loadError = null;
        try {
            this.searchParams = searchParams;
            const { resModel = '' } = this.metaData || {};
            this._updateGroupByFields(searchParams);
            const fields = this._buildFieldList();
            const records = await this._fetchRecords(resModel, searchParams, fields);
            if (version !== this._loadVersion) return;
            this._mapRecords(records);
            await this._resolveRelatedColors();
            await this._resolveM2MNames();
            if (version !== this._loadVersion) return;
            await this._resolveAvatarModels();
            if (version !== this._loadVersion) return;
            this._sortBySequence();
            if (this._sortOrder) this._sortRecords();
            this._buildGroups(prevGroupBy);
            this.revision++;
            this.notify();
        } catch (error) {
            console.error('Failed to load gantt data:', error);
            if (version === this._loadVersion) {
                this.loadError = error;
                this.notify();
            }
        } finally {
            if (version === this._loadVersion) this.loading = false;
        }
    }

    /**
     * Updates the active group-by fields, prioritizing the search-bar groupBy
     * over the arch default_group_by, and strips any field modifiers after ":".
     * @param {Object} searchParams - The current search params
     */
    _updateGroupByFields(searchParams) {
        const { defaultGroupBy = [] } = this.metaData || {};
        const groupByFromSearch = searchParams.groupBy?.length ? searchParams.groupBy : [];
        const effectiveGroupBy = groupByFromSearch.length ? groupByFromSearch : defaultGroupBy;
        this._groupByFields = effectiveGroupBy.map((f) => f.split(':')[0]);
    }

    /** Builds the ORM field list via the records helper. */
    _buildFieldList() { return _buildFieldListFn(this); }

    /** Fetches records from the ORM via the records helper. */
    async _fetchRecords(resModel, searchParams, fields) { return _fetchRecordsFn(this, resModel, searchParams, fields); }

    /** Maps raw records onto the model via the records helper. */
    _mapRecords(records) { _mapRecordsFn(this, records); }

    /** Resolves related-field colors via the records helper. */
    async _resolveRelatedColors() { return _resolveRelatedColorsFn(this); }

    /** Resolves m2m display names via the records helper. */
    async _resolveM2MNames() { return _resolveM2MNamesFn(this); }

    /** Resolves avatar availability via the records helper. */
    async _resolveAvatarModels() { return _resolveAvatarModelsFn(this); }

    /** Sorts records by sequence via the records helper. */
    _sortBySequence() { _sortBySequenceFn(this); }

    /** Refreshes a single record via the records helper. */
    async refreshRecord(taskId) { return _refreshRecordFn(this, taskId); }

    /** Fetches a newly-created record via the records helper. */
    async fetchNewRecord(resId) { return _fetchNewRecordFn(this, resId); }

    /** Inserts a new record into the model via the records helper. */
    async addNewRecord(rawRecord) { return _addNewRecordFn(this, rawRecord); }

    /** Rebuilds the group tree via the groups helper. */
    _buildGroups(prevGroupBy, forceRebuild) { _buildGroupsFn(this, prevGroupBy, forceRebuild); }

    /** Finds a group by path via the groups helper. */
    _findGroupByPath(path) { return _findGroupByPathFn(this, path); }

    /** Sorts records by the active sort order via the groups helper. */
    _sortRecords() { _sortRecordsFn(this); }

    /** Toggles a group's collapsed state via the groups helper. */
    toggleGroup(key) { _toggleGroupFn(this, key); }

    /** Returns whether a group is collapsed via the groups helper. */
    isGroupCollapsed(key) { return _isGroupCollapsedFn(this, key); }

    /** Places a record at the top of a group via the groups helper. */
    setRecordOnTopOfGroup(recordId, groupPath) { _setRecordOnTopOfGroupFn(this, recordId, groupPath); }

    /** Places a record at a position in a group via the groups helper. */
    setRecordInGroupAtPosition(recordId, groupPath, index) { _setRecordInGroupAtPositionFn(this, recordId, groupPath, index); }

    /** Computes the group order after moving a record via the groups helper. */
    computeGroupOrder(groupPath, movedId, index) { return _computeGroupOrderFn(this, groupPath, movedId, index); }

    /** Persists a group order via the groups helper. */
    async persistGroupOrder(groupPath, orderIds) { return _persistGroupOrderFn(this, groupPath, orderIds); }

    /** Builds a create context from a group path via the groups helper. */
    buildGroupContext(groupPath, baseContext) { return _buildGroupContextFn(this, groupPath, baseContext); }

    /** Sets the sort order via the groups helper. */
    setSortOrder(sortOrder, sortField) { _setSortOrderFn(this, sortOrder, sortField); }

    /**
     * Returns whether a field is avatar-capable (has resolved avatar models).
     * @param {string} fieldName - The field name
     * @returns {boolean}
     */
    isAvatarField(fieldName) { return Boolean(this._avatarModels?.[fieldName]); }

    /**
     * Returns the avatar image URL for a record ID of an avatar field, or null
     * when the record has no image.
     * @param {string} fieldName - The avatar field name
     * @param {number} id - The related record ID
     * @returns {string|null} The image URL, or null
     */
    getAvatarUrl(fieldName, id) {
        const model = this._avatarModels?.[fieldName];
        if (!model || id == null) return null;
        const idsWithImage = this._avatarIdsWithImage?.[fieldName];
        if (idsWithImage === undefined) return null;
        if (!idsWithImage.has(id)) return null;
        return `/web/image?model=${model}&id=${id}&field=image_128`;
    }
}
