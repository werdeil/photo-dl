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

Python 3.10 ou supérieur. Chrome doit être installé sur la machine. Le pilote
ChromeDriver est récupéré automatiquement par
[webdriver-manager](https://pypi.org/project/webdriver-manager/).

## Configuration

### Assistant interactif (recommandé)

La façon la plus simple de configurer l'outil est la commande `config`, qui pose
les questions une à une et génère (ou met à jour) le fichier `.env` pour vous :

```bash
school-photo-dl config
```

Elle propose des valeurs par défaut (dossier de téléchargement `~/Photos/school-photo-dl`),
réutilise les valeurs existantes si un `.env` est déjà présent (Entrée = inchangé)
et masque la saisie des mots de passe. Vous pouvez laisser vides les identifiants
d'une plateforme que vous n'utilisez pas.

> Pas besoin de lancer `config` au préalable : si vous exécutez `school-photo-dl`,
> `school-photo-dl tma` ou `school-photo-dl klassly` alors qu'une variable requise
> manque, l'assistant se lance automatiquement.

### Configuration manuelle

Les identifiants et le dossier de téléchargement sont lus depuis les variables
d'environnement (chargées depuis un fichier `.env` du dossier courant si
présent). Voir [`.env.example`](.env.example).

#### Partagé

```bash
DOWNLOAD_DIR="/chemin/vers/dossier"
HEADLESS="true"   # "false" pour voir le navigateur
```

#### toutemonannee.com

```bash
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"
```

#### fr.klass.ly

```bash
KLASSLY_USERNAME="+33600000000"
KLASSLY_PASSWORD="motdepasse"
```

## Utilisation

Une seule commande, plusieurs sous-commandes :

```bash
school-photo-dl config     # configure le fichier .env de façon interactive
school-photo-dl tma        # télécharge depuis toutemonannee.com
school-photo-dl klassly    # télécharge depuis fr.klass.ly
school-photo-dl --version
```

Sans sous-commande, la CLI lit `.env` et lance en séquence toutes les
plateformes pour lesquelles les identifiants sont renseignés :

```bash
school-photo-dl            # auto : TMA puis Klassly si les deux sont configurés
```

Si aucune variable n'est configurée (premier lancement, `.env` absent ou
incomplet), la CLI **lance automatiquement l'assistant `config`** pour vous
guider, puis enchaîne avec les téléchargements. Cela vaut aussi pour
`school-photo-dl tma` / `school-photo-dl klassly` : si une variable requise
(`DOWNLOAD_DIR` ou les identifiants de la plateforme) manque, l'assistant
s'ouvre avant de poursuivre. Inutile donc de lancer `config` manuellement au
premier usage.

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

Publication sur PyPI : pousser un tag `vX.Y.Z` déclenche
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) (Trusted
Publisher PyPI, aucun token à gérer).

```bash
git tag v0.1.0 && git push --tags
```

Pour un build local (test du paquet avant tag) :

```bash
python -m build
twine check dist/*
```

## Licence

GPL-3.0-or-later. Voir [LICENSE](LICENSE).

## Soutenez les plateformes

[toutemonannee.com](https://www.toutemonannee.com) et
[Klassly](https://fr.klass.ly) sont des services qui facilitent le lien entre
les familles et l'école au quotidien. Leur fonctionnement repose sur des
équipes qui développent et maintiennent ces outils.

**Si vous appréciez le service rendu, pensez à souscrire aux offres payantes
proposées par ces plateformes** (albums photo imprimés, abonnements premium,
etc.). C'est le meilleur moyen de les soutenir et de garantir leur pérennité.

Cet outil n'a pas vocation à se substituer à ces offres mais simplement à vous
permettre de conserver une copie locale de vos photos.

## Avertissement

Cet outil est destiné à récupérer **vos propres** photos auxquelles vous avez
légalement accès via votre compte. L'utilisateur est responsable du respect des
conditions d'utilisation des plateformes concernées et des droits à l'image.
