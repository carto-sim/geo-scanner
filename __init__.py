"""Plugin QGIS - Geo File Scanner"""


def classFactory(iface):
    from .geo_scanner import GeoFileScannerPlugin
    return GeoFileScannerPlugin(iface)
