/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ConstructionTaskNode extends Component {
    static template = "miro_construction_project.TaskNode";
    static props = ["store", "taskId", "depth"];

    setup() {
        this.action = useService("action");
    }

    get task() {
        return this.props.store.tasksById[this.props.taskId];
    }

    get childIds() {
        const all = this.props.store.childrenByParent[this.props.taskId] || [];
        if (!this.props.store.visibleIds) return all;
        return all.filter((id) => this.props.store.visibleIds.has(id));
    }

    get hasChildren() {
        return (this.props.store.childrenByParent[this.props.taskId] || []).length > 0;
    }

    get isExpanded() {
        if (this.props.store.visibleIds) return true;
        return !!this.props.store.expanded[this.props.taskId];
    }

    get roundedProgress() {
        return Math.round(this.task.x_avancement_global || 0);
    }

    get isDone() {
        return (this.task.x_avancement_global || 0) >= 100;
    }

    get statusDotClass() {
        if (this.isDone) return "is-done";
        if (this.task.x_est_en_retard) return "is-late";
        if ((this.task.x_avancement_global || 0) > 0) return "is-info";
        return "is-empty";
    }

    get progressBarClass() {
        if (this.isDone) return "is-done";
        if (this.task.x_est_en_retard) return "is-late";
        return "";
    }

    toggle(ev) {
        ev.stopPropagation();
        if (!this.hasChildren) return;
        const id = this.props.taskId;
        this.props.store.expanded[id] = !this.props.store.expanded[id];
    }

    get isElement() {
        return this.task.kind === "element";
    }

    async openForm() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.isElement ? "construction.element" : "project.task",
            res_id: this.task.resId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

ConstructionTaskNode.components = { ConstructionTaskNode };


export class ProjectTaskHierarchy extends Component {
    static template = "miro_construction_project.TaskHierarchy";
    static components = { ConstructionTaskNode };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.store = useState({
            tasksById: {},
            parentOf: {},
            childrenByParent: {},
            rootIds: [],
            expanded: {},
            projectName: "",
            loading: true,
            search: "",
            visibleIds: null,
            stats: { total: 0, done: 0, inProgress: 0, late: 0 },
            globalProgress: 0,
        });

        onWillStart(() => this._loadData());
    }
        
    get visibleRootIds() {
        if (!this.store.visibleIds) return this.store.rootIds;
        return this.store.rootIds.filter((id) => this.store.visibleIds.has(id));
    }

    get globalProgress() {
        return this.store.globalProgress;
    }

    onSearchInput(ev) {
        this.store.search = ev.target.value;
        this._computeVisible();
    }

    clearSearch() {
        this.store.search = "";
        this.store.visibleIds = null;
    }

    _computeVisible() {
        const q = this.store.search.toLowerCase().trim();
        if (!q) {
            this.store.visibleIds = null;
            return;
        }
        const visible = new Set();
        for (const id in this.store.tasksById) {
            const task = this.store.tasksById[id];
            if (task.name && task.name.toLowerCase().includes(q)) {
                let pid = id;
                while (pid) {
                    visible.add(pid);
                    pid = this.store.parentOf[pid];
                }
            }
        }
        this.store.visibleIds = visible;
    }

    async _loadData() {
        const context = (this.props.action && this.props.action.context) || {};
        this.projectId = context.default_project_id || context.active_id || false;

        const domain = this.projectId ? [["project_id", "=", this.projectId]] : [];
        const tasks = await this.orm.searchRead(
            "project.task",
            domain,
            [
                "name",
                "parent_id",
                "construction_element_id",
                "x_avancement_global",
                "x_est_en_retard",
                "x_corps_metier",
                "x_responsable_technique_id",
            ]
        );

        // Éléments de construction : niveau intermédiaire entre l'Ouvrage et
        // ses phases. Une phase a pour parent_id l'Ouvrage (hiérarchie Odoo,
        // qui fait remonter l'avancement) et pour construction_element_id son
        // élément : c'est ce second lien qui place la phase sous l'élément
        // dans le diagramme, sans dupliquer la parenté dans un autre champ.
        const elementIds = [
            ...new Set(
                tasks
                    .filter((t) => t.construction_element_id)
                    .map((t) => t.construction_element_id[0])
            ),
        ];
        const elementDomain = this.projectId
            ? ["|", ["project_id", "=", this.projectId], ["id", "in", elementIds]]
            : [["id", "in", elementIds]];
        const elements = await this.orm.searchRead(
            "construction.element",
            elementDomain,
            [
                "name",
                "key",
                "element_type_id",
                "level_id",
                "ouvrage_task_id",
                "progress",
                "dimension_summary",
                "has_missing_fields",
            ]
        );

        // Les nœuds sont indexés par une clé typée (« t12 » pour une tâche,
        // « e5 » pour un élément) : un même id peut exister dans les deux modèles.
        const tasksById = {};
        const parentOf = {};
        const childrenByParent = {};
        const rootIds = [];
        const stats = { total: 0, done: 0, inProgress: 0, late: 0 };
        let progressSum = 0;

        const attach = (nodeId, parentId) => {
            parentOf[nodeId] = parentId;
            if (!parentId) {
                rootIds.push(nodeId);
                return;
            }
            if (!childrenByParent[parentId]) childrenByParent[parentId] = [];
            childrenByParent[parentId].push(nodeId);
        };

        const taskIds = new Set(tasks.map((t) => t.id));
        for (const element of elements) {
            const nodeId = `e${element.id}`;
            tasksById[nodeId] = {
                ...element,
                kind: "element",
                resId: element.id,
                name: element.key && element.key !== element.name
                    ? `${element.key} — ${element.name}`
                    : element.name,
                x_avancement_global: element.progress || 0,
                x_est_en_retard: false,
            };
        }
        for (const element of elements) {
            const ouvrage = element.ouvrage_task_id && element.ouvrage_task_id[0];
            attach(`e${element.id}`, ouvrage && taskIds.has(ouvrage) ? `t${ouvrage}` : null);
        }

        for (const task of tasks) {
            const nodeId = `t${task.id}`;
            tasksById[nodeId] = { ...task, kind: "task", resId: task.id };
            const elementNode = task.construction_element_id
                && `e${task.construction_element_id[0]}`;
            let parentId = null;
            if (elementNode && tasksById[elementNode]) parentId = elementNode;
            else if (task.parent_id && taskIds.has(task.parent_id[0])) {
                parentId = `t${task.parent_id[0]}`;
            }
            attach(nodeId, parentId);

            // Une phase en retard met son élément en retard.
            if (parentId === elementNode && task.x_est_en_retard
                    && (task.x_avancement_global || 0) < 100) {
                tasksById[elementNode].x_est_en_retard = true;
            }

            stats.total++;
            const progress = task.x_avancement_global || 0;
            progressSum += progress;

            if (progress >= 100) stats.done++;
            else if (task.x_est_en_retard) stats.late++;
            else if (progress > 0) stats.inProgress++;
        }

        // Avancement global = moyenne de l'avancement de toutes les tâches.
        // (Mettre sur les tâches racines seulement est une alternative métier.)
        const globalProgress = stats.total
            ? Math.round(progressSum / stats.total)
            : 0;

        this.store.tasksById = tasksById;
        this.store.parentOf = parentOf;
        this.store.childrenByParent = childrenByParent;
        this.store.rootIds = rootIds;
        this.store.stats = stats;
        this.store.globalProgress = globalProgress;
        this.store.loading = false;

        if (this.projectId) {
            const projects = await this.orm.read(
                "project.project", [this.projectId], ["name"]
            );
            this.store.projectName = projects.length ? projects[0].name : "";
        }
    }

    expandAll() {
        const expanded = {};
        for (const id of Object.keys(this.store.tasksById)) expanded[id] = true;
        this.store.expanded = expanded;
    }

    collapseAll() {
        this.store.expanded = {};
    }

    /** Maquette 3D du projet, reconstruite à partir de ses éléments de
     *  construction (cf. controllers/viewer_3d.py). */
    openViewer3D() {
        if (!this.projectId) return;
        this.action.doAction({
            type: "ir.actions.act_url",
            url: `/construction/3d/${this.projectId}`,
            target: "new",
        });
    }
}

registry.category("actions").add(
    "miro_construction_project.task_hierarchy",
    ProjectTaskHierarchy
);