"""Plugin QGIS - Geo File Scanner"""

def classFactory(iface):
    from .geo_scanner import GeoFileScannerPlugin
    return GeoFileScannerPlugin(iface)

"""
Je viens de tester, voici quelques petites choses à régler :
* Il n'affiche pas la liste des schémas dans la liste déroulante
* Il ne semble pas créer de nouveau schéma si je choisis cette option
* Pour les imports en parallèle, s'assurer que les plus gros fichiers sont importés en premier, et les plus petits à la fin
* Je voudrais que les fonctionnalités d'analyse et d'import apparaissent dans la même fenêtre : un onglet pour l'analyse, un onglet pour l'import
* Si un import échoue, afficher le message d'erreur associé à l'échec.
"""
