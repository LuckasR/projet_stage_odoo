# Apprendre Git avec le terminal

## 1. Les commandes essentielles

### Initialiser un dépôt

```bash
git init
```

Crée un dépôt Git dans le projet courant.

### Voir l'état du projet

```bash
git status
```

Permet de voir les fichiers modifiés, ajoutés ou non suivis.

### Ajouter les modifications

```bash
git add .
```

Ajoute toutes les modifications à la zone de préparation (*staging*).

Pour ajouter un seul fichier :

```bash
git add nom_du_fichier.py
```

### Créer un commit

```bash
git commit -m "Message du commit"
```

Enregistre les modifications dans l'historique Git.

Exemple :

```bash
git commit -m "Ajout de l'extraction des métadonnées DXF"
```

### Voir l'historique

```bash
git log
```

Affiche les commits précédents.

Version plus compacte :

```bash
git log --oneline
```

### Voir les modifications

```bash
git diff
```

Affiche les modifications qui ne sont pas encore ajoutées avec `git add`.

### Voir les branches

```bash
git branch
```

Affiche les branches locales.

### Créer une branche

```bash
git switch -c develop
```

Crée la branche `develop` et se positionne dessus.

### Voir le dépôt distant

```bash
git remote -v
```

Affiche les dépôts distants associés au projet.

### Envoyer les commits vers GitHub

```bash
git push
```

Envoie les commits locaux vers le dépôt distant.

### Récupérer les modifications

```bash
git pull
```

Récupère les modifications du dépôt distant et les intègre dans la branche courante.

---

# 2. Utiliser Git avec un projet Odoo

Se placer dans le projet :

```bash
cd ~/Documents/Stage/code/ton-projet
```

Initialiser Git :

```bash
git init
```

Vérifier l'état :

```bash
git status
```

Avant le premier `git add`, créer un fichier `.gitignore` afin d'éviter d'envoyer des fichiers inutiles ou sensibles.

Ensuite :

```bash
git add .
```

Créer le premier commit :

```bash
git commit -m "Initialisation du projet Odoo"
```

---

# 3. Exemple de `.gitignore` pour un projet Odoo

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo

# Environnements virtuels
venv/
.venv/
env/

# Odoo
*.log
*.pid

# Configuration locale
.env
odoo.conf
*.conf

# PostgreSQL
*.sql
*.dump
*.backup

# Odoo filestore
filestore/
.odoo/

# Fichiers temporaires
*.tmp
*.temp
*.swp
*~

# IDE
.vscode/
.idea/

# Fichiers système
.DS_Store
Thumbs.db

# Plans / fichiers lourds
*.dwg
*.dxf

# Python packaging
*.egg-info/
dist/
build/
```

> Attention : si certains fichiers `.conf` ou `.dxf` font partie volontairement du code ou de la configuration distribuée du projet, il faut adapter le `.gitignore`.

---

# 4. Structure recommandée du projet

Un projet Odoo peut être organisé ainsi :

```text
mon-projet-construction/
│
├── addons/
│   └── miro_construction_management/
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── models/
│       ├── controllers/
│       ├── views/
│       ├── security/
│       └── static/
│
├── scripts/
├── README.md
├── .gitignore
└── docker-compose.yml
```

Le code source doit être versionné.

En revanche, il ne faut généralement pas mettre dans Git :

- la base PostgreSQL réelle ;
- le filestore Odoo ;
- les mots de passe ;
- les clés API ;
- les environnements virtuels Python ;
- les fichiers temporaires ;
- les fichiers DWG/DXF lourds.

---

# 5. Le cycle Git à retenir

Le cycle de base est :

```text
                 Code
                  │
                  ▼
             git status
                  │
                  ▼
               git add
                  │
                  ▼
             git commit
                  │
                  ▼
              git push
                  │
                  ▼
               GitHub
```

Pour récupérer le travail depuis GitHub :

```text
              GitHub
                 │
                 ▼
              git pull
                 │
                 ▼
            Modification
                 │
                 ▼
              git add
                 │
                 ▼
             git commit
                 │
                 ▼
              git push
```

---

# 6. Les commandes à maîtriser en priorité

Ne cherche pas à mémoriser toutes les commandes Git immédiatement.

Commence par maîtriser :

```bash
git status
git add .
git commit -m "message"
git log --oneline
git diff
git pull
git push
```

Ensuite, apprends progressivement :

```bash
git branch
git switch
git merge
git stash
git restore
```

Puis les notions plus avancées :

- branches ;
- merge ;
- conflits ;
- rebase ;
- cherry-pick ;
- tags ;
- GitHub Pull Requests.

---

# 7. Exemple de travail quotidien

Après avoir modifié ton module Odoo :

```bash
git status
```

Regarder les changements :

```bash
git diff
```

Ajouter les fichiers :

```bash
git add .
```

Créer un commit clair :

```bash
git commit -m "Ajout des métadonnées DXF"
```

Envoyer vers GitHub :

```bash
git push
```

Un commit doit idéalement représenter une modification logique et compréhensible.

Exemples :

```bash
git commit -m "Ajout du modèle des métadonnées DXF"
git commit -m "Ajout de la conversion DWG vers DXF"
git commit -m "Ajout du contrôleur de visualisation DXF"
git commit -m "Ajout de la récupération des calques DXF"
```

---

# 8. Objectif d'apprentissage

Pour ton projet Odoo + DXF, l'objectif est de savoir faire ce cycle sans interface graphique :

```text
Modifier le code
      ↓
git status
      ↓
git diff
      ↓
git add
      ↓
git commit
      ↓
git push
```

Puis savoir récupérer les changements :

```text
git pull
```

Qui est connecter : 

git config --global user.name
git config --global user.email

Une fois ce cycle maîtrisé, tu pourras travailler avec des branches et apprendre à gérer les conflits Git.
