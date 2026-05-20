"""Plugin principal de scan de fichiers géographiques"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAction, QFileDialog, QDialog, QVBoxLayout, QPushButton, QLabel,
                                 QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox)
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.core import QgsVectorLayer, QgsProviderRegistry
from pathlib import Path
import os

from .scan_thread import ScanThread
from .analysis import GeographicAnalyzer
from .compat import SelectRows, MultiSelection, ResizeToContents, HeaderStretch
from .utils import (compute_short_paths, is_valid_geo_layer, format_size,
                    get_epsg_from_layer, get_geometry_type_from_layer, get_feature_count_from_layer)


class GeoFileScannerPlugin:
    """Plugin principal"""

    GEO_EXTENSIONS = {'.shp', '.geojson', '.json', '.gml', '.gpx', '.tab', '.mif', '.dxf', '.gdb', '.sqlite', '.gpkg', '.kml'}
    MULTI_LAYER_FORMATS = {'.sqlite', '.gpkg', '.kml'}

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.scan_thread = None
        self.analyzer = None
        self.current_geo_files = []
        self._load_reference_layers()

    def _load_reference_layers(self):
        """Charge les couches de référence"""
        data_dir = os.path.join(self.plugin_dir, 'data')
        dep_layer = self._load_layer(os.path.join(data_dir, 'DEPARTEMENT.shp'))
        reg_layer = self._load_layer(os.path.join(data_dir, 'REGION.shp'))
        self.analyzer = GeographicAnalyzer(dep_layer, reg_layer)

    def _load_layer(self, path):
        """Charge une couche shapefile"""
        if os.path.exists(path):
            layer = QgsVectorLayer(path, "ref", "ogr")
            return layer if layer.isValid() else None
        return None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path) if os.path.exists(icon_path) else QIcon(),
                              "Scanner fichiers géographiques", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Geo Scanner", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Geo Scanner", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        folder = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "Sélectionner un dossier à scanner")
        if folder:
            self.show_scan_window(folder)

    def show_scan_window(self, folder):
        """Affiche la fenêtre avec barre de progression"""
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialog.setWindowTitle("Fichiers géographiques trouvés")
        self.dialog.resize(900, 600)
        self.dialog.setModal(False)

        layout = QVBoxLayout()

        self.info_label = QLabel(f"Dossier scanné : {folder}\nAnalyse en cours...")
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Préparation...")
        layout.addWidget(self.progress_label)

        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.cancel_scan)
        layout.addWidget(self.cancel_button)

        self.table = QTableWidget()
        self.table.setVisible(False)
        layout.addWidget(self.table)

        self.change_folder_button = QPushButton("Changer de dossier")
        self.change_folder_button.clicked.connect(self.change_folder)
        self.change_folder_button.setVisible(False)
        layout.addWidget(self.change_folder_button)

        self.close_button = QPushButton("Fermer")
        self.close_button.clicked.connect(self.dialog.close)
        self.close_button.setVisible(False)
        layout.addWidget(self.close_button)

        self.dialog.setLayout(layout)
        self.dialog.show()

        self.scan_thread = ScanThread(self, folder)
        self.scan_thread.progress.connect(self.update_progress)
        self.scan_thread.finished_signal.connect(self.scan_finished)
        self.scan_thread.start()

    def update_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        self.progress_label.setText(message)

    def cancel_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait()
            self.dialog.close()

    def scan_finished(self, geo_files, elapsed_time):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.cancel_button.setVisible(False)

        if len(geo_files) > 100:
            self.info_label.setText(f"Le dossier contient {len(geo_files)} fichiers.\n"
                                    f"Trop important (limite: 100).\nTemps: {elapsed_time:.2f}s")
            self.close_button.setVisible(True)
            return

        self.info_label.setText(f"Dossier : {self.scan_thread.folder_path}\n"
                                f"Fichiers : {len(geo_files)}\nTemps : {elapsed_time:.2f}s")

        self._populate_table(geo_files)
        self.table.setVisible(True)
        self.change_folder_button.setVisible(True)
        self.close_button.setVisible(True)

    def change_folder(self):
        folder = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "Nouveau dossier")
        if folder:
            self.dialog.close()
            self.show_scan_window(folder)

    def _populate_table(self, geo_files):
        """Remplit le tableau"""
        self.table.setRowCount(len(geo_files))
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['Nom', 'Dossier', 'Type', 'Géométrie', 'Nb entités',
                                              'Taille', 'EPSG', 'Département', 'Région'])

        self.table.setSelectionBehavior(SelectRows)
        self.table.setSelectionMode(MultiSelection)

        for row, f in enumerate(geo_files):
            items = [
                (f['name'], None, None),
                (f['short_path'], None, f['relative_path']),
                (f['extension'], None, None),
                (f['geom_type'], None, None),
                (f['feature_count'], None, None),
                (f['size'], None, None),
                (f['epsg'], None, None),
                (f['departement'], self._get_font(f['departement_percent'], f['departement_italic']), f['departement_tooltip']),
                (f['region'], self._get_font(f['region_percent'], f['region_italic']), f['region_tooltip'])
            ]

            for col, (text, font, tooltip) in enumerate(items):
                item = QTableWidgetItem(text)
                if font:
                    item.setFont(font)
                if tooltip:
                    item.setToolTip(tooltip)
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        for i in range(7):
            header.setSectionResizeMode(i, ResizeToContents)
        header.setSectionResizeMode(7, HeaderStretch)
        header.setSectionResizeMode(8, HeaderStretch)

        self.export_pg_button = QPushButton("Import des données sur base PostgreSQL")
        self.export_pg_button.clicked.connect(self.export_to_postgres)
        self.dialog.layout().insertWidget(self.dialog.layout().count() - 2, self.export_pg_button)
        self.export_pg_button.setVisible(True)

    def export_to_postgres(self):
        """Ouvre le dialogue d'import PostgreSQL"""
        selected_rows = set(item.row() for item in self.table.selectedItems())

        if not selected_rows:
            QMessageBox.warning(self.dialog, "Attention", "Veuillez sélectionner au moins une couche à importer")
            return

        from .postgres_export import PostgresImportDialog

        # Les lignes du tableau correspondent directement aux indices de current_geo_files
        selected_files = [self.current_geo_files[row] for row in sorted(selected_rows)]

        dialog = PostgresImportDialog(self.dialog, selected_files,
                                      self.analyzer.departement_layer,
                                      self.analyzer.region_layer)
        dialog.exec()

    def _get_font(self, percent, italic):
        """Retourne la police selon le pourcentage"""
        if percent == 0:
            return None
        font = QFont()
        if percent >= 0.9:
            font.setBold(True)
        elif italic:
            font.setItalic(True)
        return font if (font.bold() or font.italic()) else None

    def scan_folder(self, folder_path, thread=None):
        """Scanne le dossier"""
        geo_files = []
        total = sum(1 for _, _, files in os.walk(folder_path)
                    for f in files if Path(f).suffix.lower() in self.GEO_EXTENSIONS)
        current = 0

        for root, _, files in os.walk(folder_path):
            for file in files:
                if len(geo_files) > 100:
                    return geo_files

                if thread and thread.is_canceled:
                    return geo_files

                file_ext = Path(file).suffix.lower()
                if file_ext not in self.GEO_EXTENSIONS:
                    continue

                current += 1
                if thread:
                    thread.progress.emit(current, total, f"Analyse : {file}\n({current}/{total})")

                file_path = os.path.join(root, file)
                geo_files.extend(self._process_file(file_path, file, file_ext, folder_path, thread, current, total))

        self.current_geo_files = geo_files
        compute_short_paths(geo_files, folder_path)
        return geo_files

    def _process_file(self, file_path, file, file_ext, folder_path, thread, current, total):
        """Traite un fichier géographique"""
        if file_ext in self.MULTI_LAYER_FORMATS:
            return self._process_multi_layer(file_path, file, file_ext, folder_path, thread, current, total)

        layer = QgsVectorLayer(file_path, "temp", "ogr")
        if is_valid_geo_layer(layer):
            return [self._create_entry(file_path, file, file_ext, folder_path, Path(file).stem, layer, file_path)]
        return []

    def _process_multi_layer(self, file_path, file, file_ext, folder_path, thread, current, total):
        """Traite un fichier multi-couches"""
        results = []
        layer = QgsVectorLayer(file_path, "temp", "ogr")

        if not layer.isValid():
            return results

        metadata = QgsProviderRegistry.instance().providerMetadata('ogr')
        if not metadata:
            return results

        sublayers = metadata.querySublayers(file_path)

        if sublayers and len(sublayers) > 1:
            for sublayer in sublayers:
                if thread and thread.is_canceled:
                    return results

                layer_name = sublayer.name()
                layer_uri = sublayer.uri()
                test_layer = QgsVectorLayer(layer_uri, "test", "ogr")

                if is_valid_geo_layer(test_layer):
                    if thread:
                        thread.progress.emit(current, total, f"Analyse : {file} [{layer_name}]\n({current}/{total})")
                    results.append(self._create_entry(file_path, file, file_ext, folder_path,
                                                      f"{Path(file).stem} [{layer_name}]", test_layer, layer_uri))
        else:
            if is_valid_geo_layer(layer):
                results.append(self._create_entry(file_path, file, file_ext, folder_path, Path(file).stem, layer, file_path))

        return results

    def _create_entry(self, file_path, file, file_ext, folder_path, name, layer, uri):
        """Crée une entrée pour le tableau"""
        coverage = self.analyzer.analyze_coverage(layer)

        return {
            'path': file_path,
            'uri': uri,
            'relative_path': os.path.relpath(file_path, folder_path),
            'short_path': None,
            'name': name,
            'extension': file_ext,
            'size': format_size(os.path.getsize(file_path)),
            'epsg': get_epsg_from_layer(layer),
            'geom_type': get_geometry_type_from_layer(layer),
            'feature_count': get_feature_count_from_layer(layer),
            **coverage
        }
