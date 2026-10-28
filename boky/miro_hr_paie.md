# Présences et paie (`miro_hr_paie`)

> Ce module ajoute à Odoo Community une paie simple adaptée aux ouvriers de chantier : à partir des pointages de présence, il calcule chaque mois un bulletin de paie (salaire à la journée, à l'heure ou au mois, heures supplémentaires, cotisations sociales, impôt IRSA) et l'imprime au format PDF Miro Construction. Il fournit aussi les paramètres de temps de travail et de charges sur lesquels s'appuie le chiffrage de la main-d'œuvre des autres modules.

| Fiche | |
|---|---|
| Nom technique | `miro_hr_paie` |
| Version | 17.0.1.0.0 |
| Catégorie | Human Resources/Payroll |
| Dépend de | `hr` (Employés), `hr_attendance` (Présences), `miro_report_layout` (mise en page des PDF Miro) |
| Utilisé par | `miro_construction_planning` (coût horaire des métiers), et indirectement `miro_construction_journal` (coût de la main-d'œuvre saisie au journal) |
| Auteur / licence | Miro Construction / LGPL-3 |

## 1. Le besoin métier

Une entreprise de construction emploie surtout des ouvriers payés **à la journée** (maçons, coffreurs, manœuvres), parfois **à l'heure**, et un personnel d'encadrement payé **au mois**. Chaque fin de mois, il faut transformer les présences réelles en un montant à payer, en tenant compte :

- des **heures supplémentaires** faites au-delà de la journée normale, majorées ;
- des **absences** des salariés mensuels ;
- des **cotisations sociales** (CNaPS, organisme de santé) salariales et patronales ;
- de l'**impôt sur les revenus salariaux (IRSA)**, calculé par tranches.

Or Odoo Community ne propose aucun module de paie (la paie est réservée à l'édition Enterprise). Ce module en fournit une version volontairement simple, branchée sur le pointage standard d'Odoo (`hr_attendance`). Le manifeste le précise : les taux et barèmes livrés (contexte malgache, en Ariary) sont **indicatifs** et doivent être validés par le service comptable.

Second besoin, moins visible mais important pour la suite du projet : connaître le **coût horaire chargé** d'un ouvrier (salaire ramené à l'heure + charges patronales). Ce module stocke tous les paramètres nécessaires à ce calcul (heures par jour, jours de référence par mois, taux patronaux), réutilisés par le planning et le journal de chantier.

## 2. Fonctionnalités

### 2.1 Fiche de paie de l'employé

Sur la fiche d'un employé, un nouvel onglet **« Paie »** (visible des responsables RH) permet de saisir :

- le **mode de paie** (boutons radio) : Journalier, Horaire ou Mensuel ;
- le **taux** correspondant, seul affiché et obligatoire selon le mode : taux journalier, taux horaire ou salaire mensuel ;
- le **métier** en texte libre (maçon, coffreur, manœuvre…) ;
- le **numéro CNaPS**, l'assujettissement aux **cotisations sociales** et à l'**IRSA**, et le nombre de **personnes à charge** (qui réduit l'IRSA).

Un bouton statistique **« Bulletins »** en haut de la fiche affiche le nombre de bulletins de l'employé et ouvre leur liste.

### 2.2 Bulletin de paie calculé depuis les présences

Dans **Employés > Paie > Bulletins de paie**, l'utilisateur crée un bulletin en choisissant un employé et une période (par défaut, le mois en cours). Le bouton **« Calculer »** :

1. lit les pointages terminés de la période et en déduit les jours travaillés, les heures travaillées et les heures supplémentaires ;
2. compare aux jours ouvrés du calendrier de travail de l'employé pour obtenir les jours d'absence ;
3. génère les **rubriques** (lignes du bulletin) : salaire de base, absences, heures supplémentaires, cotisations, IRSA ;
4. affiche les totaux : salaire brut, total des retenues, **net à payer**, charges patronales et **coût employeur**.

Le bulletin garde une copie du mode de paie, du taux et de l'emploi au moment du calcul : si le taux de l'employé change ensuite, le bulletin reste juste.

### 2.3 Primes, indemnités et avances saisies à la main

Dans l'onglet « Rubriques », l'utilisateur peut ajouter ses propres lignes : une prime ou une indemnité (nature « Gain ») ou une avance sur salaire (nature « Retenue »). Ces lignes manuelles sont **conservées** quand on relance le calcul, et les primes sont intégrées au brut avant le calcul des cotisations et de l'IRSA. Si l'on saisit un nombre et un taux unitaire, le montant se calcule automatiquement.

### 2.4 Cycle de vie du bulletin

Le bulletin passe par les états **Brouillon → Validé → Payé** (ou Annulé), avec un bouton par étape :

| Bouton | Effet |
|---|---|
| Calculer | (Re)calcule un bulletin brouillon |
| Valider | Calcule le bulletin s'il n'a encore aucune ligne, puis le fige |
| Marquer comme payé | Passe un bulletin validé à « Payé » et enregistre la date du jour comme date de paiement |
| Remettre en brouillon | Depuis « Validé » ou « Annulé » |
| Annuler | Possible tant que le bulletin n'est pas payé |
| Imprimer le bulletin | Génère le PDF |

Les changements d'employé, d'état et de net à payer sont tracés dans le fil de discussion (chatter) du bulletin.

### 2.5 Génération des bulletins d'un mois en une fois

Le menu **« Générer les bulletins »** ouvre un assistant : on choisit la période, éventuellement un seul mode de paie (par exemple uniquement les journaliers), et la liste des employés se remplit automatiquement. Le bouton « Générer » crée et calcule un bulletin par employé, puis affiche la liste des bulletins créés. Les employés qui ont déjà un bulletin non annulé sur la période sont ignorés ; ceux dont le taux n'est pas renseigné ont leur bulletin créé mais non calculé, et un message récapitulatif est posté dans le chatter.

### 2.6 Bulletin de paie PDF

Le bulletin imprimé reprend la mise en page commune Miro Construction (`miro_report_layout`) et comporte :

- l'en-tête avec la référence (`PAIE/2026/10/0001`), la période, la date de paiement et une mention **BROUILLON** si le bulletin n'est pas validé ;
- les blocs **Employeur** (nom, adresse, NIF, STAT) et **Salarié** (matricule, emploi, service, mode de paie et taux, n° CNaPS) ;
- un bandeau des présences (jours, heures, heures supplémentaires, jours ouvrés, absences) ;
- le tableau des rubriques en colonnes Gains / Retenues, puis le **net à payer** mis en avant et écrit **en toutes lettres** ;
- les charges patronales et le coût total employeur, « à titre d'information » ;
- la note éventuelle, les zones de signature employeur et salarié, et la mention de conservation du bulletin.

### 2.7 Paramètres de paie

Dans **Paramètres > Employés**, un bloc « Paie » regroupe les réglages de la société :

| Groupe | Paramètres (valeur par défaut) |
|---|---|
| Temps de travail | Heures normales par jour (8), jours de référence par mois (26), majoration des heures supplémentaires (30 %), déduction des absences des mensuels (oui) |
| Cotisations sociales | CNaPS salariale (1 %) et patronale (13 %), plafond CNaPS ; organisme de santé (« OSTIE »), part salariale (1 %) et patronale (5 %), plafond santé |
| IRSA | Minimum de perception (3 000), réduction par personne à charge (2 000), lien vers le barème par tranches |

Le **barème IRSA** est une liste éditable de tranches (de, à, taux). Le barème livré est : 0 % jusqu'à 350 000, puis 5 %, 10 %, 15 % et 20 % au-delà de 600 000.

## 3. Qui l'utilise et comment

| Rôle | Ce qu'il fait |
|---|---|
| Responsable RH / gestionnaire de paie (groupe « Employés : Officier ») | Renseigne l'onglet Paie des employés, génère, contrôle, valide et imprime les bulletins |
| Administrateur RH (groupe « Employés : Administrateur ») | En plus, modifie le barème IRSA et les paramètres de paie |
| Pointeur / chef de chantier | Ne voit pas la paie : il alimente seulement les présences (module standard Présences) |

Parcours type de fin de mois :

1. Au fil du mois, les arrivées et départs des ouvriers sont pointés dans **Présences**.
2. Le gestionnaire de paie ouvre **Employés > Paie > Générer les bulletins**, garde la période du mois et lance la génération.
3. Il parcourt la liste des bulletins (regroupés par période), ouvre ceux à compléter (taux manquant signalé dans le chatter) et ajoute les primes ou avances du mois.
4. Il relance « Calculer » si besoin, puis **valide** les bulletins.
5. Il imprime les bulletins PDF et les fait signer.
6. Une fois le salaire versé, il clique **« Marquer comme payé »**.

## 4. Modèle de données

| Modèle | Rôle | Champs clés |
|---|---|---|
| `miro.payslip` (nouveau) | Bulletin de paie d'un employé sur une période | `name` (référence séquentielle), `employee_id`, `date_from`, `date_to`, `payment_date`, `state`, instantané (`pay_type`, `rate`, `job_label`), présences (`worked_days`, `worked_hours`, `overtime_hours`, `expected_days`, `absent_days`, `attendance_count`), totaux stockés (`gross`, `total_deductions`, `net`, `employer_charges`, `total_cost`), `taxable` |
| `miro.payslip.line` (nouveau) | Rubrique (ligne) d'un bulletin | `code` (BASE, ABS, HSUP, CNAPS, SANTE, IRSA, …_P), `name`, `category` (gain / retenue / charge patronale), `quantity`, `unit_amount`, `base`, `rate_pct`, `amount`, `manual` |
| `miro.irsa.bracket` (nouveau) | Tranche du barème IRSA, par société | `amount_from`, `amount_to` (vide = sans limite), `rate` |
| `miro.payslip.generate` (assistant, transitoire) | Génération groupée des bulletins | `date_from`, `date_to`, `employee_ids`, `pay_type` |
| `hr.employee` (étendu) | Données de paie de l'employé | `miro_pay_type`, `miro_daily_rate`, `miro_hourly_rate`, `miro_monthly_wage`, `miro_trade`, `miro_cnaps_number`, `miro_dependents`, `miro_social_contributions`, `miro_subject_irsa`, `miro_payslip_ids` |
| `res.company` (étendu) | Paramètres de paie de la société | `miro_hours_per_day`, `miro_month_days`, `miro_overtime_rate`, `miro_deduct_absences`, taux et plafonds CNaPS et santé, `miro_irsa_minimum`, `miro_irsa_dependent_reduction`, `miro_irsa_bracket_ids` |
| `res.config.settings` (étendu) | Écran de paramètres | Champs liés (« related ») aux paramètres de la société |

Relations importantes :

- un employé a plusieurs bulletins ; un bulletin a plusieurs rubriques (supprimées avec lui) ;
- le bulletin lit les pointages `hr.attendance` de l'employé et son calendrier de travail (`resource_calendar_id`), sans lien stocké ;
- les tranches IRSA et tous les taux sont rattachés à la **société** : chaque société d'une base multi-sociétés peut avoir ses propres règles.

## 5. Règles métier et calculs

Toutes les règles de calcul sont dans `models/payslip.py` (méthode `_compute_sheet`).

**Présences** (`_attendance_summary`, `_expected_days`) :

- seuls les pointages **terminés** (avec heure de sortie) dont l'entrée tombe dans la période sont pris en compte ;
- les heures sont regroupées par jour **dans le fuseau horaire de l'employé** (et non en UTC), pour qu'un pointage du soir ne bascule pas sur le lendemain ;
- jours travaillés = nombre de jours ayant au moins une heure pointée ;
- heures supplémentaires = somme, jour par jour, des heures au-delà des heures normales par jour ;
- jours ouvrés = jours de travail du calendrier de l'employé sur la période ; jours d'absence = jours ouvrés − jours travaillés (jamais négatif).

**Salaire de base** selon le mode de paie :

| Mode | Rubrique de base | Taux horaire équivalent (pour les heures sup.) |
|---|---|---|
| Journalier | jours travaillés × taux journalier | taux journalier ÷ heures par jour |
| Horaire | (heures travaillées − heures sup.) × taux horaire | taux horaire |
| Mensuel | salaire mensuel ; si la déduction est activée : − jours d'absence × (salaire ÷ jours de référence) | (salaire ÷ jours de référence) ÷ heures par jour |

- **Heures supplémentaires** : heures sup. × taux horaire équivalent × (1 + majoration %).
- **Brut** = gains calculés + gains saisis à la main.
- **Cotisations** (si l'employé y est soumis) : base = brut, limitée au plafond s'il est renseigné ; une ligne salariale (retenue) et une ligne patronale (charge) pour la CNaPS et pour l'organisme de santé.
- **Revenu imposable** = brut − cotisations salariales, **arrondi à la centaine inférieure**.
- **IRSA** (si l'employé y est soumis) : si le revenu imposable dépasse la tranche exonérée (tranche à 0 %), l'impôt est calculé tranche par tranche (`models/irsa_bracket.py`, `_tax_for`), diminué de la réduction par personne à charge, et jamais inférieur au minimum de perception.
- **Net à payer** = brut − retenues ; **coût employeur** = brut + charges patronales (`_compute_totals`).

**Contraintes et verrous** :

- la date de début doit précéder la date de fin (contrainte SQL) ;
- un taux manquant sur la fiche employé bloque le calcul avec un message explicite ;
- seul un bulletin **brouillon** peut être recalculé ; les rubriques ne sont modifiables dans le formulaire qu'en brouillon ;
- un bulletin **validé ou payé ne peut pas être supprimé** : il faut l'annuler (`unlink`) ; un bulletin payé ne peut plus être annulé ni remis en brouillon ;
- au recalcul, seules les lignes calculées sont refaites ; les lignes `manual` sont conservées ;
- la référence est attribuée par une séquence `PAIE/année/mois/0001` (`data/ir_sequence_data.xml`) ;
- l'assistant ignore les employés ayant déjà un bulletin non annulé chevauchant la période, et isole chaque calcul dans un point de sauvegarde (savepoint) de base de données pour qu'une erreur sur un employé n'empêche pas les autres (`wizard/payslip_generate.py`).

## 6. Interfaces

| Type | Élément |
|---|---|
| Menus | Employés > Paie > **Bulletins de paie** ; Employés > Paie > **Générer les bulletins** ; Employés > Configuration > **Barème IRSA** (administrateurs) |
| Vues | Liste des bulletins (couleurs selon l'état, totaux en pied de colonne, regroupement par période par défaut), formulaire du bulletin (en-tête à boutons, présences, rubriques éditables, totaux, note, chatter), recherche (filtres Brouillons / Validés / Payés / Ce mois-ci, regroupements par employé, période, mode de paie, état), liste éditable du barème IRSA |
| Extensions de vues | Onglet « Paie » et bouton « Bulletins » sur la fiche employé ; bloc « Paie » dans les paramètres Employés |
| Assistant | « Générer les bulletins de paie » (`miro.payslip.generate`) |
| Rapport PDF | « Bulletin de paie » (`action_report_payslip`), disponible aussi depuis le menu Imprimer de la liste ; nom du fichier « Bulletin de paie - employé - référence » ; feuille de style dédiée `static/src/scss/payslip_report.scss` |
| Données | Séquence des bulletins, barème IRSA indicatif pour la société principale |
| Routes HTTP, tâches planifiées, JavaScript | Aucun |

## 7. Sécurité et droits d'accès

Fichier `security/ir.model.access.csv` :

| Modèle | Officier RH (`hr.group_hr_user`) | Administrateur RH (`hr.group_hr_manager`) |
|---|---|---|
| Bulletins et rubriques | Lecture, écriture, création, suppression | (hérité) |
| Barème IRSA | Lecture seule | Tous droits |
| Assistant de génération | Tous droits | (hérité) |

Tous les nouveaux champs de l'employé (taux, mode de paie, CNaPS…) sont protégés par `groups="hr.group_hr_user"` : un chef de chantier ne voit pas les salaires. Les modules qui ont besoin du coût horaire (journal de chantier, métiers du planning) le lisent en mode `sudo` (droits système) pour obtenir un montant sans exposer les taux individuels. Aucune règle d'enregistrement (filtrage par société) n'est définie sur les bulletins.

## 8. Intégration avec les autres modules

- **Présences (`hr_attendance`)** : source des jours et heures travaillés.
- **Calendriers de travail (`resource`, via `hr`)** : jours ouvrés attendus de l'employé.
- **`miro_report_layout`** : en-tête et pied de page communs des PDF, champ STAT de la société.
- **`miro_construction_planning`** : réutilise le mode de paie, les taux, l'assujettissement aux cotisations et les paramètres de la société pour calculer le **coût horaire chargé** d'un ouvrier (méthode `_miro_loaded_hourly_cost`). Précision : cette méthode est définie dans `miro_construction_planning/models/hr_employee.py`, pas dans ce module, mais elle n'utilise que des données créées ici. Le planning transforme aussi le métier en texte libre (`miro_trade`) en un vrai métier relationnel.
- **`miro_construction_journal`** : la main-d'œuvre saisie au journal de chantier prend par défaut `miro_hours_per_day` comme nombre d'heures et le coût horaire chargé de l'ouvrier comme coût.
- **`miro_mobile_api`** : expose `miro_hours_per_day` à l'application mobile.

## 9. Points techniques notables

- **Paie construite sans Odoo Enterprise** : un petit moteur de rubriques (gain / retenue / charge patronale) suffit à couvrir les besoins d'un chantier, avec des totaux calculés et stockés pour être filtrés, groupés et sommés dans les listes.
- **Instantané du contrat** : le bulletin copie le mode de paie, le taux et l'emploi au moment du calcul, ce qui garantit qu'un bulletin ancien ne change pas quand un salaire est revalorisé.
- **Coexistence calcul automatique / saisie manuelle** grâce au drapeau `manual` : on peut recalculer autant de fois que nécessaire sans perdre les primes saisies.
- **Gestion du fuseau horaire** : regroupement des pointages par jour local de l'employé.
- **Génération robuste** : chaque bulletin est calculé dans un savepoint ; les erreurs sont collectées et signalées au lieu de bloquer toute la génération.
- **Paramétrage plutôt que code** : taux, plafonds, barème, minimum et réductions sont modifiables par l'utilisateur, ce qui rend le module adaptable si la législation évolue.
- **PDF compatible wkhtmltopdf** : la feuille de style utilise des tableaux plutôt que flexbox (non supporté par le moteur PDF d'Odoo), et le net est écrit en toutes lettres via la devise de la société.
- **Socle pour le chiffrage** : les paramètres de temps de travail et de charges servent ensuite au planning et au journal, ce qui assure qu'un même ouvrier a le même coût horaire partout.

## 10. Limites et pistes d'amélioration

- **Taux et barèmes indicatifs** : à faire valider par le service comptable ; le barème IRSA n'est livré que pour la société principale.
- **Pas de lien avec la comptabilité** : aucune écriture comptable n'est générée à la validation ou au paiement, et aucun ordre de virement.
- **Congés non pris en compte** : les jours ouvrés sont calculés sans les congés (`compute_leaves=False`), donc un congé approuvé d'un mensuel est compté comme absence et déduit si la déduction est activée. Une intégration avec `hr_holidays` serait nécessaire.
- **Journée comptée dès la première heure** pour un journalier : une demi-journée pointée est payée comme une journée entière.
- **Heures supplémentaires simplifiées** : un seul taux de majoration, calcul par jour uniquement (pas de distinction nuit, dimanche, jour férié, ni de seuil hebdomadaire).
- **Verrou partiel** : la protection d'un bulletin validé repose surtout sur l'interface (rubriques en lecture seule) et sur l'interdiction de suppression ; il n'y a pas de blocage côté serveur des modifications d'un bulletin validé.
- **Messages de l'assistant** : le récapitulatif des erreurs est posté uniquement dans le chatter du premier bulletin créé, ce qui le rend peu visible.
- **Pas de tests automatisés** dans le module.
- Pistes : livre de paie mensuel (récapitulatif PDF ou export), déclarations CNaPS/IRSA, prise en compte des congés, gestion des acomptes récurrents.
