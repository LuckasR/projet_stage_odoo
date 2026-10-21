# -*- coding: utf-8 -*-
{
    "name": "Gantt View",
    "summary": "Interactive Gantt view for Odoo.",
    "description": """
        Gantt View
        This module adds a modern and interactive Gantt view to Odoo.
        Features:
        - Interactive Gantt timeline.
        - Drag-and-drop task scheduling.
        - Task resizing.
        - Multiple zoom levels (Day, Week, Month, Year).
        - Grouping support.
        - Progress visualization.
        - Custom coloring.
        - Extensible architecture for custom business modules.
    """,
    "category": "Hidden",
    "version": "17.0.1.0.2",
    "author": "A. M. Herijaona, MIRO K.E.",
    "website": "https://miroke.com",
    "depends": ["web"],
    "data": [
        "security/groups.xml",
    ],
    # Backend assets
    "assets": {
        "web.assets_backend": [
            # Chart.js v4 is bundled here (instead of relying on the isolated
            # `web.chartjs_lib` bundle, which fails to serve on some servers:
            # GET /web/assets/debug/web.chartjs_lib.js -> 500).
            "web/static/lib/Chart/Chart.js",
            "miro_gantt_view/static/src/*.js",
            "miro_gantt_view/static/src/**/*.js",
            "miro_gantt_view/static/src/**/*.xml",
            "miro_gantt_view/static/src/**/**/*.js",
            "miro_gantt_view/static/src/**/**/*.xml",
            "miro_gantt_view/static/src/utils/**/*.scss",
            "miro_gantt_view/static/src/utils/*.js",
        ],
    },
    "license": "Other proprietary",
    "installable": True,
    "application": False,
    "auto_install": False,
}
