/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Icône d'une phase selon son code (gabarits de phases)
const PHASE_ICONS = {
    coffrage: "fa-th-large",
    ferraillage: "fa-bars",
    coulage: "fa-tint",
    decoffrage: "fa-th",
    elevation: "fa-building-o",
};

const STATUS = {
    done: { label: "Terminé", cls: "is-done" },
    late: { label: "En retard", cls: "is-late" },
    progress: { label: "En cours", cls: "is-progress" },
    todo: { label: "À faire", cls: "is-todo" },
};

/** État d'un nœud : le plus urgent l'emporte (le retard avant l'avancement). */
function nodeStatus(node) {
    const progress = node.x_avancement_global || 0;
    if (progress >= 100) return "done";
    if (node.x_est_en_retard) return "late";
    if (progress > 0) return "progress";
    return "todo";
}

export class ConstructionTaskNode extends Component {
    static template = "miro_construction_project.TaskNode";
    static props = ["store", "taskId", "depth"];

    setup() {
        this.action = useService("action");
    }

    get task() {
        return this.props.store.tasksById[this.props.taskId];
    }

    get allChildIds() {
        return this.props.store.childrenByParent[this.props.taskId] || [];
    }

    get childIds() {
        if (!this.props.store.visibleIds) return this.allChildIds;
        return this.allChildIds.filter((id) => this.props.store.visibleIds.has(id));
    }

    get hasChildren() {
        return this.allChildIds.length > 0;
    }

    get isExpanded() {
        if (this.props.store.visibleIds) return true;
        return !!this.props.store.expanded[this.props.taskId];
    }

    get isElement() {
        return this.task.kind === "element";
    }

    get isOuvrage() {
        return this.task.kind === "task" && (this.task.is_ouvrage || this.props.depth === 0) && this.hasChildren;
    }

    get roundedProgress() {
        return Math.round(this.task.x_avancement_global || 0);
    }

    /** Un repère vertical par niveau d'indentation */
    get indents() {
        return Array.from({ length: this.props.depth }, (_, i) => i);
    }

    get status() {
        return STATUS[nodeStatus(this.task)];
    }

    get kindIcon() {
        if (this.isElement) return "fa-cube";
        if (this.isOuvrage) return this.isExpanded ? "fa-folder-open" : "fa-folder";
        return PHASE_ICONS[this.task.phase_type] || "fa-circle-o";
    }

    get kindClass() {
        if (this.isElement) return "is-element";
        if (this.isOuvrage) return "is-ouvrage";
        return "is-phase";
    }

    get subtitle() {
        if (this.isElement) {
            return [this.task.element_type_id && this.task.element_type_id[1],
                    this.task.level_id && this.task.level_id[1]].filter((v) => v).join(" · ");
        }
        return this.task.x_corps_metier_label || "";
    }

    get deadline() {
        const d = this.task.date_deadline;
        if (!d) return "";
        const [y, m, day] = d.slice(0, 10).split("-");
        return `${day}/${m}/${y}`;
    }

    get deadlinePassed() {
        const d = this.task.date_deadline;
        return d && (this.task.x_avancement_global || 0) < 100
            && new Date(d.slice(0, 10)) < new Date(new Date().toDateString());
    }

    toggle(ev) {
        ev.stopPropagation();
        if (!this.hasChildren) return;
        const id = this.props.taskId;
        this.props.store.expanded[id] = !this.props.store.expanded[id];
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
        this.statusFilters = [
            { key: "all", label: "Toutes", icon: "fa-list-ul" },
            { key: "progress", label: "En cours", icon: "fa-hourglass-half" },
            { key: "late", label: "En retard", icon: "fa-exclamation-triangle" },
            { key: "done", label: "Terminées", icon: "fa-check" },
            { key: "todo", label: "À faire", icon: "fa-circle-o" },
        ];

        this.store = useState({
            tasksById: {},
            parentOf: {},
            childrenByParent: {},
            rootIds: [],
            expanded: {},
            projectName: "",
            loading: true,
            search: "",
            filter: "all",
            visibleIds: null,
            stats: { total: 0, done: 0, progress: 0, late: 0, todo: 0 },
            counts: { ouvrages: 0, elements: 0, phases: 0 },
            globalProgress: 0,
        });

        onWillStart(() => this._loadData());
    }

    // ------------------------------------------------------------------
    // Affichage
    // ------------------------------------------------------------------
    get visibleRootIds() {
        if (!this.store.visibleIds) return this.store.rootIds;
        return this.store.rootIds.filter((id) => this.store.visibleIds.has(id));
    }

    get globalProgress() {
        return this.store.globalProgress;
    }

    /** Anneau d'avancement : longueur du trait sur la circonférence (r = 42). */
    get ringDash() {
        const c = 2 * Math.PI * 42;
        return `${(c * this.globalProgress) / 100} ${c}`;
    }

    statCount(key) {
        return key === "all" ? this.store.stats.total : this.store.stats[key];
    }

    // ------------------------------------------------------------------
    // Recherche et filtres : un nœud reste visible s'il correspond, avec
    // tous ses ancêtres (pour garder le chemin jusqu'à lui).
    // ------------------------------------------------------------------
    onSearchInput(ev) {
        this.store.search = ev.target.value;
        this._computeVisible();
    }

    clearSearch() {
        this.store.search = "";
        this._computeVisible();
    }

    setFilter(key) {
        this.store.filter = this.store.filter === key ? "all" : key;
        this._computeVisible();
    }

    _computeVisible() {
        const q = this.store.search.toLowerCase().trim();
        const filter = this.store.filter;
        if (!q && filter === "all") {
            this.store.visibleIds = null;
            return;
        }
        const visible = new Set();
        for (const id in this.store.tasksById) {
            const node = this.store.tasksById[id];
            // Le filtre d'état porte sur les phases (les tâches qui ont un
            // avancement propre), pas sur les regroupements.
            const isLeaf = !(this.store.childrenByParent[id] || []).length;
            if (filter !== "all" && (!isLeaf || nodeStatus(node) !== filter)) continue;
            if (q && !(node.name || "").toLowerCase().includes(q)) continue;
            let pid = id;
            while (pid) {
                visible.add(pid);
                pid = this.store.parentOf[pid];
            }
        }
        this.store.visibleIds = visible;
    }

    expandAll() {
        const expanded = {};
        for (const id of Object.keys(this.store.tasksById)) expanded[id] = true;
        this.store.expanded = expanded;
    }

    collapseAll() {
        this.store.expanded = {};
    }

    /** Déplie les ouvrages seulement : on voit leurs éléments, pas les phases. */
    expandOuvrages() {
        const expanded = {};
        for (const id of this.store.rootIds) expanded[id] = true;
        this.store.expanded = expanded;
    }

    // ------------------------------------------------------------------
    // Données
    // ------------------------------------------------------------------
    async _loadData() {
        const context = (this.props.action && this.props.action.context) || {};
        this.projectId = context.default_project_id || context.active_id || false;

        const domain = this.projectId ? [["project_id", "=", this.projectId]] : [];
        const [tasks, corpsSelection] = await Promise.all([
            this.orm.searchRead("project.task", domain, [
                "name",
                "parent_id",
                "construction_element_id",
                "x_avancement_global",
                "x_est_en_retard",
                "x_corps_metier",
                "x_responsable_technique_id",
                "is_ouvrage",
                "phase_type",
                "date_deadline",
            ]),
            this.orm.call("project.task", "fields_get", [["x_corps_metier"]], { attributes: ["selection"] }),
        ]);
        const corpsLabels = Object.fromEntries(
            (corpsSelection.x_corps_metier && corpsSelection.x_corps_metier.selection) || []);

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
        const stats = { total: 0, done: 0, progress: 0, late: 0, todo: 0 };
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

        let phases = 0;
        let ouvrages = 0;
        for (const task of tasks) {
            const nodeId = `t${task.id}`;
            tasksById[nodeId] = {
                ...task,
                kind: "task",
                resId: task.id,
                x_corps_metier_label: corpsLabels[task.x_corps_metier] || "",
            };
            const elementNode = task.construction_element_id
                && `e${task.construction_element_id[0]}`;
            let parentId = null;
            if (elementNode && tasksById[elementNode]) parentId = elementNode;
            else if (task.parent_id && taskIds.has(task.parent_id[0])) {
                parentId = `t${task.parent_id[0]}`;
            }
            attach(nodeId, parentId);
            if (task.is_ouvrage) ouvrages++;
            if (task.construction_element_id) phases++;

            // Une phase en retard met son élément en retard.
            if (parentId === elementNode && task.x_est_en_retard
                    && (task.x_avancement_global || 0) < 100) {
                tasksById[elementNode].x_est_en_retard = true;
            }

            stats.total++;
            progressSum += task.x_avancement_global || 0;
            stats[nodeStatus(task)]++;
        }

        // Avancement global = moyenne de l'avancement de toutes les tâches.
        const globalProgress = stats.total
            ? Math.round(progressSum / stats.total)
            : 0;

        this.store.tasksById = tasksById;
        this.store.parentOf = parentOf;
        this.store.childrenByParent = childrenByParent;
        this.store.rootIds = rootIds;
        this.store.stats = stats;
        this.store.counts = { ouvrages, elements: elements.length, phases };
        this.store.globalProgress = globalProgress;
        this.store.loading = false;

        if (this.projectId) {
            const projects = await this.orm.read(
                "project.project", [this.projectId], ["name"]
            );
            this.store.projectName = projects.length ? projects[0].name : "";
        }
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------
    openProject() {
        if (!this.projectId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            res_id: this.projectId,
            views: [[false, "form"]],
            target: "current",
        });
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
