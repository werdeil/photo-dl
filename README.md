# school-photo-dl

Téléchargeurs de photos en ligne de commande pour deux plateformes scolaires françaises :

- [toutemonannee.com](https://www.toutemonannee.com)
- [fr.klass.ly](https://fr.klass.ly)

Pilote Chrome via Selenium, s'authentifie avec vos identifiants, parcourt les
albums/classes et enregistre les images HD localement, organisées par
album/classe et date.

## Installation

```bash
pip install school-photo-dl
```

Chrome doit être installé sur la machine. Le pilote ChromeDriver est récupéré
automatiquement par [webdriver-manager](https://pypi.org/project/webdriver-manager/).

## Configuration

Les identifiants et le dossier de téléchargement sont lus depuis les variables
d'environnement (chargées depuis un fichier `.env` du dossier courant si
présent). Voir [`.env.example`](.env.example).

### Partagé

```bash
DOWNLOAD_DIR="/chemin/vers/dossier"
HEADLESS="true"   # "false" pour voir le navigateur
```

### toutemonannee.com

```bash
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"
```

### fr.klass.ly

```bash
KLASSLY_USERNAME="+33600000000"
KLASSLY_PASSWORD="motdepasse"
```

## Utilisation

Une seule commande, deux sous-commandes :

```bash
school-photo-dl tma        # télécharge depuis toutemonannee.com
school-photo-dl klassly    # télécharge depuis fr.klass.ly
school-photo-dl --version
```

Sans sous-commande, la CLI lit `.env` et lance en séquence toutes les
plateformes pour lesquelles les identifiants sont renseignés :

```bash
school-photo-dl            # auto : TMA puis Klassly si les deux sont configurés
```

### Arborescence de sortie

- TMA : `{DOWNLOAD_DIR}/{nom_espace}/{date} - {titre}/*.jpg`
- Klassly : `{DOWNLOAD_DIR}/{nom_classe}/{YYYY-MM-DD} - {texte_post}/*.jpg`

## Développement

```bash
git clone https://github.com/werdeil/school-photo-dl
cd school-photo-dl
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Construire et publier sur PyPI :

```bash
python -m build
twine upload dist/*
```

## Licence

GPL-3.0-or-later. Voir [LICENSE](LICENSE).

## Avertissement

Cet outil est destiné à récupérer **vos propres** photos auxquelles vous avez
légalement accès via votre compte. L'utilisateur est responsable du respect des
conditions d'utilisation des plateformes concernées et des droits à l'image.
