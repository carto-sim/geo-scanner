"""Fonctions utilitaires"""

from pathlib import Path
import os

from .compat import GeomPoint, GeomLine, GeomPolygon, GeomNull, GeomUnknown


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
        if geom_type == GeomPoint:
            return "Point"
        elif geom_type == GeomLine:
            return "LineString"
        elif geom_type == GeomPolygon:
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
            layer.geometryType() not in [GeomNull, GeomUnknown])


def _compute_base_path(full_path, display_name, base_folder, all_files):
    """Calcule le chemin de base brut (sans la règle des 50%)."""
    rel_path = os.path.relpath(full_path, base_folder)
    path_parts = list(Path(rel_path).parts)

    if len(path_parts) == 1:
        return "."

    duplicates = [f for f in all_files if f['name'] == display_name and f['path'] != full_path]

    if not duplicates:
        return path_parts[0]

    current_path = path_parts[:-1]
    all_dup_paths = [
        list(Path(os.path.relpath(d['path'], base_folder)).parts[:-1])
        for d in duplicates
    ]

    min_len = min(len(current_path), min((len(p) for p in all_dup_paths), default=0))

    common_prefix_len = 0
    for i in range(min_len):
        if all(len(p) > i and p[i] == current_path[i] for p in all_dup_paths):
            common_prefix_len = i + 1
        else:
            break

    common_suffix_len = 0
    for i in range(1, min_len + 1):
        if all(len(p) >= i and p[-i] == current_path[-i] for p in all_dup_paths):
            common_suffix_len = i
        else:
            break

    discriminant_start = common_prefix_len
    discriminant_end = len(current_path) - common_suffix_len

    if discriminant_end > discriminant_start:
        parts = current_path[discriminant_start:discriminant_end]
        return "/".join(parts) if parts else current_path[0]

    if common_suffix_len < len(current_path):
        return current_path[-(common_suffix_len + 1)]
    return current_path[0] if current_path else "."


def compute_short_paths(geo_files, base_folder):
    """Calcule les chemins courts pour tous les fichiers en deux passes nettes.

    Passe 1 : chemin de base brut (logique des doublons, sans seuil de concentration).
    Passe 2 : si ≥50 % des fichiers partagent le même chemin de base, on descend
              d'un niveau supplémentaire pour distinguer.
    """
    # Passe 1 : chemin de base brut pour chaque fichier
    base_paths = {
        f['path']: _compute_base_path(f['path'], f['name'], base_folder, geo_files)
        for f in geo_files
    }

    # Comptage des occurrences de chaque chemin de base
    from collections import Counter
    counts = Counter(base_paths.values())
    threshold = len(geo_files) / 2

    # Passe 2 : ajustement si concentration > 50 %
    for f in geo_files:
        base = base_paths[f['path']]
        if counts[base] >= threshold:
            rel = os.path.relpath(f['path'], base_folder)
            parts = list(Path(rel).parts)
            if len(parts) > 2:
                base_idx = parts.index(base) if base in parts else 0
                next_idx = base_idx + 1
                if next_idx < len(parts) - 1:
                    f['short_path'] = f"{base}/{parts[next_idx]}"
                else:
                    f['short_path'] = f"{base} (racine)"
            else:
                f['short_path'] = f"{base} (racine)" if len(parts) == 2 else base
        else:
            f['short_path'] = base
