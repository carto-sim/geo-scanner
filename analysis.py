"""Analyse géographique des couches"""

from qgis.core import (QgsGeometry, QgsCoordinateTransform, QgsProject,
                       QgsSpatialIndex, QgsFeatureRequest, QgsMessageLog)
from collections import defaultdict
import random

from .compat import NoGeometryFlag, LogWarning

_TAG = "Geo File Scanner"


class GeographicAnalyzer:
    """Analyse la couverture géographique des fichiers"""

    def __init__(self, departement_layer, region_layer):
        self.departement_layer = departement_layer
        self.region_layer = region_layer
        self._dept_index = self._build_index(departement_layer)
        self._reg_index = self._build_index(region_layer)

    def _build_index(self, layer):
        """Construit un index spatial sur une couche de référence."""
        if layer and layer.isValid():
            return QgsSpatialIndex(layer.getFeatures())
        return None

    def analyze_coverage(self, layer):
        """Analyse la couverture d'une couche"""
        result = {
            'departement': '', 'departement_tooltip': '', 'departement_percent': 0, 'departement_italic': False,
            'region': '', 'region_tooltip': '', 'region_percent': 0, 'region_italic': False
        }

        try:
            feature_count = layer.featureCount()
            if feature_count == 0:
                return result

            if feature_count > 10000:
                # Collecte les IDs sans charger géométrie ni attributs
                id_request = QgsFeatureRequest().setNoAttributes().setFlags(NoGeometryFlag)
                all_ids = [f.id() for f in layer.getFeatures(id_request)]
                sample_ids = random.sample(all_ids, min(500, len(all_ids)))
                features = list(layer.getFeatures(QgsFeatureRequest().setFilterFids(sample_ids)))
            else:
                features = list(layer.getFeatures())

            sample_count = len(features)

            if self.departement_layer and self.departement_layer.isValid():
                dep_data = self._analyze_admin_level(
                    layer, features, sample_count,
                    self.departement_layer, "département", self._dept_index
                )
                result.update({
                    'departement': dep_data[0], 'departement_tooltip': dep_data[1],
                    'departement_percent': dep_data[2], 'departement_italic': dep_data[3]
                })

            if self.region_layer and self.region_layer.isValid():
                reg_data = self._analyze_admin_level(
                    layer, features, sample_count,
                    self.region_layer, "région", self._reg_index
                )
                result.update({
                    'region': reg_data[0], 'region_tooltip': reg_data[1],
                    'region_percent': reg_data[2], 'region_italic': reg_data[3]
                })

        except Exception as e:
            QgsMessageLog.logMessage(f"Erreur analyse couverture: {e}", _TAG, LogWarning)

        return result

    def _analyze_admin_level(self, layer, features, sample_count, admin_layer, level_type, admin_index=None):
        """Analyse un niveau administratif (département ou région)"""
        name = ""
        tooltip = ""
        percent = 0
        italic = False

        transform = None
        if layer.crs().authid() != admin_layer.crs().authid():
            transform = QgsCoordinateTransform(layer.crs(), admin_layer.crs(), QgsProject.instance())

        counts = defaultdict(int)
        for feat in features:
            if not feat.hasGeometry():
                continue

            geom = QgsGeometry(feat.geometry())
            if transform:
                try:
                    geom.transform(transform)
                except Exception:
                    continue

            # Pré-filtre par index spatial pour éviter O(n × m) tests d'intersection
            if admin_index is not None:
                candidate_ids = admin_index.intersects(geom.boundingBox())
                if not candidate_ids:
                    continue
                admin_features = admin_layer.getFeatures(
                    QgsFeatureRequest().setFilterFids(candidate_ids)
                )
            else:
                admin_features = admin_layer.getFeatures()

            for admin_feat in admin_features:
                if admin_feat.hasGeometry() and admin_feat.geometry().intersects(geom):
                    fields = admin_feat.fields().names()
                    nom = admin_feat['nom'] if 'nom' in fields else None
                    code = admin_feat['code'] if 'code' in fields else None
                    key = f"{nom} ({code})" if nom and code else (nom or "Inconnu")
                    counts[key] += 1
                    break

        if not counts:
            return name, tooltip, percent, italic

        threshold_90 = 0.9
        threshold_10 = 0.1

        matching = [(d, c) for d, c in counts.items() if c / sample_count >= threshold_90]

        if len(matching) == 1:
            name = matching[0][0]
            percent = matching[0][1] / sample_count
            tooltip = f"{name}: {percent * 100:.1f}%"
        elif len(matching) > 1:
            name = f"Plusieurs {level_type}s"
        else:
            top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:2]
            top_percent = top[0][1] / sample_count

            if top_percent >= threshold_10:
                all_below_50 = all(d[1] / sample_count < 0.5 for d in top)
                name = " / ".join(d[0] for d in top)
                percent = top_percent
                italic = all_below_50
                tooltip = " / ".join(f"{d[0]}: {d[1] / sample_count * 100:.1f}%" for d in top)

        return name, tooltip, percent, italic
