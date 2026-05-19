"""Fonctions utilitaires"""

from qgis.core import QgsVectorLayer, QgsWkbTypes
from pathlib import Path
import os


def format_size(size_bytes):
    """Formate la taille du fichier"""
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} To"


def get_geometry_type_from_layer(layer):
    """Récupère le type de géométrie d'une couche"""
    if layer.isValid():
        geom_type = layer.geometryType()
        if geom_type == QgsWkbTypes.PointGeometry:
            return "Point"
        elif geom_type == QgsWkbTypes.LineGeometry:
            return "LineString"
        elif geom_type == QgsWkbTypes.PolygonGeometry:
            return "Polygon"
    return "Non détecté"


def get_epsg_from_layer(layer):
    """Récupère le code EPSG d'une couche"""
    if layer.isValid() and layer.crs().isValid():
        return layer.crs().authid()
    return "Non détecté"


def get_feature_count_from_layer(layer):
    """Récupère le nombre d'entités d'une couche"""
    if layer.isValid():
        return str(layer.featureCount())
    return "Non détecté"


def is_valid_geo_layer(layer):
    """Vérifie si une couche a une géométrie valide"""
    return (layer.isValid() and 
            layer.geometryType() not in [QgsWkbTypes.NullGeometry, QgsWkbTypes.UnknownGeometry])


def get_short_path(full_path, base_folder, all_files):
    """Calcule le chemin court pour affichage - gère les doublons de noms"""
    rel_path = os.path.relpath(full_path, base_folder)
    path_parts = list(Path(rel_path).parts)
    
    # Le nom affiché dans la colonne (peut contenir [layer_name])
    display_name = None
    for f in all_files:
        if f['path'] == full_path:
            display_name = f['name']
            break
    
    if not display_name:
        return "."
    
    # Trouve les fichiers avec le même nom affiché
    duplicates = [f for f in all_files if f['name'] == display_name and f['path'] != full_path]
    
    if len(path_parts) == 1:
        return "."
    
    if not duplicates:
        base_path = path_parts[0]
    else:
        # Il y a des doublons, calcule la partie discriminante
        current_path = path_parts[:-1]  # Enlève le nom du fichier
        all_dup_paths = [list(Path(os.path.relpath(d['path'], base_folder)).parts[:-1]) for d in duplicates]
        
        # Trouve préfixe commun
        common_prefix_len = 0
        min_len = min(len(current_path), min(len(p) for p in all_dup_paths) if all_dup_paths else 0)
        for i in range(min_len):
            if all(p[i] == current_path[i] for p in all_dup_paths if len(p) > i):
                common_prefix_len = i + 1
            else:
                break
        
        # Trouve suffixe commun
        common_suffix_len = 0
        for i in range(1, min_len + 1):
            if all(len(p) >= i and p[-i] == current_path[-i] for p in all_dup_paths):
                common_suffix_len = i
            else:
                break
        
        # Extrait partie discriminante (entre préfixe et suffixe)
        discriminant_start = common_prefix_len
        discriminant_end = len(current_path) - common_suffix_len
        
        if discriminant_end > discriminant_start:
            discriminant_parts = current_path[discriminant_start:discriminant_end]
            base_path = "/".join(discriminant_parts) if discriminant_parts else current_path[0]
        else:
            if common_suffix_len < len(current_path):
                base_path = current_path[-(common_suffix_len + 1)]
            else:
                base_path = current_path[0] if current_path else "."
    
    # Vérifie si trop de fichiers ont le même chemin (>50%)
    same_path_count = sum(1 for f in all_files if f.get('temp_short_path') == base_path)
    
    if same_path_count >= len(all_files) / 2 and len(path_parts) > 2:
        if len(path_parts) == 2:
            return f"{base_path} (racine)"
        else:
            next_level = path_parts[1] if path_parts[0] == base_path else path_parts[-2]
            return f"{base_path}/{next_level}"
    
    return base_path