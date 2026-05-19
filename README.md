# Geo File Scanner — Plugin QGIS

Plugin QGIS de scan et d'import de fichiers géographiques, avec détection automatique de la couverture départementale et régionale française.

---

## Fonctionnalités

### Scan de fichiers géographiques
- Scan récursif d'un dossier avec barre de progression en temps réel (QThread)
- Formats supportés : `.shp`, `.geojson`, `.json`, `.gpkg`, `.gml`, `.kml`, `.gpx`, `.tab`, `.mif`, `.dxf`, `.gdb`, `.sqlite`
- Gestion des fichiers multi-couches (GeoPackage, SpatiaLite, KML) : chaque couche est listée séparément
- Affichage dans un tableau de 9 colonnes : nom, dossier, type, géométrie, nb entités, taille, EPSG, département, région
- Détection automatique de la couverture géographique (départements et régions françaises) par analyse d'intersection
- Tri par colonne, sélection multiple, info-bulles avec pourcentages de couverture
- Bouton « Annuler » fonctionnel
- Limite de 100 fichiers par scan

### Import vers PostgreSQL/PostGIS
- Import en parallèle (4 threads) des couches sélectionnées
- Personnalisation des noms de tables (validation alphanumérique)
- Choix du schéma (existant ou nouveau à créer)
- Préfixage automatique des tables selon région ou département sélectionné (`r52_`, `d49_`, etc.)
- Préfixe de groupement libre (`projet_2024_ma_table`)
- Filtre spatial optionnel : seules les entités intersectant un buffer de 100 m autour de la zone choisie sont importées
- Vérification des doublons de noms et confirmation avant écrasement de tables existantes
- Affichage des messages d'erreur par couche en cas d'échec

---

## Prérequis

| Composant | Version minimale |
|-----------|-----------------|
| QGIS | 3.16 (LTR) ou 4.x |
| Python | 3.6+ |
| PostgreSQL/PostGIS | uniquement pour la fonctionnalité d'import |

Le plugin est compatible **QGIS 3.16+** (Qt5/PyQt5) et **QGIS 4.x** (Qt6/PyQt6).

---

## Installation

### Méthode manuelle
1. Télécharger ou cloner ce dépôt
2. Copier le dossier dans le répertoire des plugins QGIS :
   - Linux : `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/geo_scanner/`
   - Windows : `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\geo_scanner\`
   - macOS : `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/geo_scanner/`
3. Dans QGIS : **Extensions → Gérer et installer des extensions → Installées** → activer *Geo File Scanner*

---

## Utilisation

1. Cliquer sur l'icône **Scanner fichiers géographiques** dans la barre d'outils, ou via le menu **Extension → Geo Scanner**
2. Sélectionner le dossier à analyser
3. Patienter pendant le scan (annulable à tout moment)
4. Consulter les résultats dans le tableau :
   - Les colonnes **Département** et **Région** s'affichent en **gras** si ≥ 90 % des entités sont dans une même zone, en *italique* si la couverture est partagée
   - Survoler une cellule pour afficher les pourcentages détaillés
5. Sélectionner une ou plusieurs lignes puis cliquer sur **Import des données sur base PostgreSQL**
6. Configurer les paramètres d'import et lancer

---

## Données de référence

Le dossier `data/` contient les shapefiles de référence nécessaires à l'analyse géographique :

| Fichier | Contenu | Champs requis |
|---------|---------|---------------|
| `DEPARTEMENT.shp` | Départements français | `nom`, `code`, `code_reg` |
| `REGION.shp` | Régions françaises | `nom`, `code` |

---

## Configuration à personnaliser

Avant de publier ou de distribuer le plugin, mettre à jour les champs suivants dans `metadata.txt` :

```ini
author=Votre Nom
email=votre.email@example.com
```

---

## Structure du code

```
geo_scanner/
├── __init__.py          # Point d'entrée QGIS (classFactory)
├── geo_scanner.py       # Plugin principal et interface Qt
├── scan_thread.py       # Thread de scan (QThread)
├── analysis.py          # Analyse couverture départements/régions
├── utils.py             # Fonctions utilitaires
├── postgres_export.py   # Dialogue et thread d'import PostgreSQL
├── compat.py            # Couche de compatibilité QGIS 3/4, PyQt5/PyQt6
├── metadata.txt         # Métadonnées du plugin
├── resources.qrc        # Ressources Qt (icône)
├── icon.png             # Icône du plugin
└── data/
    ├── DEPARTEMENT.shp  # Référentiel départements
    └── REGION.shp       # Référentiel régions
```

---

## Licence

Ce plugin est distribué sous licence [GNU GPL v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html) ou ultérieure, conformément aux exigences de QGIS.
