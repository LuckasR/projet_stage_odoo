# Documentation des modules Odoo — Miro Construction

Ce dossier rassemble la documentation des modules Odoo 17 développés pour Miro Construction, rédigée pour le livre de stage. Chaque module a son propre fichier. Ce sommaire présente l'ensemble et la façon dont les modules s'articulent.

Tous les fichiers suivent le même plan :

1. le besoin métier ;
2. les fonctionnalités ;
3. les utilisateurs et leurs parcours ;
4. le modèle de données ;
5. les règles métier et les calculs ;
6. les interfaces ;
7. la sécurité ;
8. l'intégration avec les autres modules ;
9. les points techniques notables ;
10. les limites et les pistes d'amélioration.

## Les modules par domaine

| Domaine | Module | En une phrase |
|---|---|---|
| Socle chantier | [`miro_construction_project`](miro_construction_project.md) | Le cœur du projet : chantiers, ouvrages, phases, hiérarchie des tâches, avancement, coûts, incidents, plans et visionneuses. |
| Socle chantier | [`miro_gantt_view`](miro_gantt_view.md) | Vue Gantt interactive pour planifier et visualiser les tâches dans le temps. |
| Matières | [`construction_product_management`](construction_product_management.md) | Gestion des produits de construction (ciment, sable, gravier…). |
| Matières | [`miro_construction_bom`](miro_construction_bom.md) | Relie les métrés des ouvrages aux nomenclatures : besoins matériaux par phase, achats et consommations. |
| Matières | [`construction_composants`](construction_composants.md) | Suivi des composants de construction (semelles, murs, poteaux…) par niveau et par projet. |
| Main-d'œuvre | [`miro_hr_paie`](miro_hr_paie.md) | Présences et paie des ouvriers (à la journée, à l'heure ou au mois), bulletin de paie PDF. |
| Main-d'œuvre | [`miro_construction_planning`](miro_construction_planning.md) | Métiers, équipes types et cadences : durée, effectif et coût de main-d'œuvre de chaque phase. |
| Terrain | [`miro_construction_journal`](miro_construction_journal.md) | Journal de chantier quotidien, validé ligne par ligne : coûts réels et avancement calculés. |
| Terrain | [`miro_mobile_api`](miro_mobile_api.md) | API de l'application mobile SuiviChantier, utilisable hors-ligne et avec détection des conflits. |
| Pilotage | [`miro_construction_overview`](miro_construction_overview.md) | Tableau de bord du chantier : indicateurs, alertes, avancement par ouvrage, coûts prévus et réels. |
| Intelligence artificielle | [`miro_ai_assistant`](miro_ai_assistant.md) | Assistant IA dans la messagerie d'Odoo (Discuss) : avancement, retards, matériaux et planning des chantiers. |
| Historique | [`miro_construction_project_analysis`](miro_construction_project_analysis.md) | Première version de l'analyse de plans, en morceaux à intégrer (non installable) ; depuis reprise et remplacée dans `miro_construction_project`. |
| Documents | [`miro_report_layout`](miro_report_layout.md) | Mise en page Miro Construction pour tous les PDF (factures, bons de commande, bons de livraison…). |
| Documents | [`miro_custom_pdf`](miro_custom_pdf.md) | Personnalisation du design des factures PDF. |
| Module tiers | [`queue`](queue.md) | Dépôt OCA `queue_job` : exécution de tâches en arrière-plan, utilisé par l'assistant IA et le socle chantier. |

Le dossier `custom-addons/miro_construction_management/` est vide : ce n'est pas un module, il n'a donc pas de fichier ici.

## Comment les modules dépendent les uns des autres

Une flèche se lit « dépend de ». Les modules standard d'Odoo (`project`, `stock`, `mrp`, `purchase`, `hr`, `account`…) ne sont pas représentés.

```
miro_mobile_api ──────────────┐
miro_construction_overview ───┤
                              ▼
                 miro_construction_journal
                    │                 │
                    ▼                 ▼
       miro_construction_bom   miro_construction_planning
         │            │           │            │
         ▼            │           ▼            ▼
construction_product_ │      miro_hr_paie   miro_gantt_view
     management       │           │            ▲
                      ▼           ▼            │
          miro_construction_project      miro_report_layout
              │          │                     
              ▼          ▼                     
          queue_job   miro_gantt_view          

miro_ai_assistant ──► miro_construction_project, queue_job
construction_composants, miro_custom_pdf : indépendants (modules standard seulement)
```

Les liens principaux :

- **`miro_construction_project`** est le socle : presque tous les modules métier en dépendent, directement ou non.
- **Le journal de chantier** est le point de convergence. Il réunit les matières (`miro_construction_bom`), la main-d'œuvre (`miro_construction_planning` et `miro_hr_paie`) et les phases (`miro_construction_project`) pour calculer le coût réel et l'avancement.
- **Le tableau de bord** et **l'API mobile** s'appuient sur le journal : le premier pour afficher les chiffres réels, la seconde pour les saisir depuis le terrain.

## Le flux d'un chantier, de l'étude au suivi

1. **Étude.** Le chantier est découpé en ouvrages et en phases avec leurs métrés (`miro_construction_project`). Chaque phase reçoit ses besoins matériaux (`miro_construction_bom`) et sa durée, son effectif et son coût de main-d'œuvre (`miro_construction_planning`). Le planning se lit dans la vue Gantt (`miro_gantt_view`).
2. **Approvisionnement.** Les besoins matériaux deviennent des achats et des réceptions en stock (`miro_construction_bom`, `construction_product_management`).
3. **Exécution.** Chaque jour, le chef de chantier remplit le journal (`miro_construction_journal`), dans Odoo ou sur son téléphone (`miro_mobile_api` et l'application SuiviChantier). Chaque ligne validée sort les matières du stock, compte dans le coût réel et fait avancer la phase.
4. **Main-d'œuvre.** Les présences des ouvriers donnent leur paie et leur coût horaire chargé (`miro_hr_paie`), repris par le journal pour le coût réel.
5. **Pilotage.** La direction suit les indicateurs, les alertes et l'écart entre prévu et réel sur le tableau de bord (`miro_construction_overview`). Elle peut aussi interroger l'assistant IA (`miro_ai_assistant`).
6. **Documents.** Factures, bons et bulletins de paie sortent avec la mise en page de l'entreprise (`miro_report_layout`, `miro_custom_pdf`).
