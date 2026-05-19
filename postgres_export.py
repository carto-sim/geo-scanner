"""Import vers PostgreSQL"""

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
                                 QPushButton, QLineEdit, QCheckBox, QProgressBar, QMessageBox,
                                 QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QWidget,
                                 QRadioButton, QButtonGroup)
from qgis.PyQt.QtGui import QValidator
from qgis.core import (QgsProject, QgsDataSourceUri, QgsVectorLayer, QgsGeometry,
                       QgsCoordinateTransform, QgsFeatureRequest, QgsProviderRegistry)
import processing
import unicodedata
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


class AlphanumericValidator(QValidator):
    """Validateur pour caractères alphanumériques et underscore uniquement"""
    def validate(self, string, pos):
        if all(c.isalnum() or c == '_' for c in string):
            return QValidator.Acceptable, string, pos
        return QValidator.Invalid, string, pos


class ImportThread(QThread):
    """Thread pour importer vers PostgreSQL en parallèle"""
    progress = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, str, list)
    
    def __init__(self, layers_data, pg_params, prefix, apply_filter, filter_geom, filter_crs, dept_code, region_code):
        super().__init__()
        self.layers_data = layers_data
        self.pg_params = pg_params
        self.prefix = prefix
        self.apply_filter = apply_filter
        self.filter_geom = filter_geom
        self.filter_crs = filter_crs
        self.dept_code = dept_code
        self.region_code = region_code
        self.is_canceled = False
        self.completed = 0
        self.total = len(layers_data)
    
    def cancel(self):
        self.is_canceled = True
    
    def run(self):
        failed = []
        
        # Import en parallèle (max 4 threads)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self._import_layer, layer_info): layer_info for layer_info in self.layers_data}
            
            for future in as_completed(futures):
                if self.is_canceled:
                    self.finished_signal.emit(False, "Import annulé", [])
                    return
                
                layer_info = futures[future]
                try:
                    success = future.result()
                    if not success:
                        failed.append(layer_info['display_name'])
                except Exception as e:
                    failed.append(f"{layer_info['display_name']}: {str(e)}")
                
                self.completed += 1
                self.progress.emit(self.completed, self.total, f"Importé {self.completed}/{self.total}")
        
        if failed:
            msg = f"Échec de {len(failed)} import(s):\n" + "\n".join(failed[:5])
            if len(failed) > 5:
                msg += f"\n... et {len(failed)-5} autres"
            self.finished_signal.emit(False, msg, failed)
        else:
            self.finished_signal.emit(True, f"✓ {self.total} couche(s) importée(s) avec succès", [])
    
    def _import_layer(self, layer_info):
        """Importe une couche vers PostgreSQL"""
        layer = QgsVectorLayer(layer_info['uri'], "temp", "ogr")
        
        if not layer.isValid():
            return False
        
        # Vérifie intersection avec département/région si filtre actif
        if self.apply_filter and self.filter_geom:
            if not self._check_intersection(layer):
                return False
            layer = self._apply_spatial_filter(layer)
            if not layer or layer.featureCount() == 0:
                return False
        
        # Normalise le nom de la table
        table_name = normalize_table_name(layer_info['custom_name'])
        
        # Ajoute préfixes
        if self.dept_code:
            table_name = f"d{self.dept_code}_{table_name}"
        elif self.region_code:
            table_name = f"r{self.region_code}_{table_name}"
        
        if self.prefix:
            table_name = f"{self.prefix}_{table_name}"
        
        table_name = table_name[:63]  # Limite PostgreSQL
        
        # Import via processing
        uri = f"dbname='{self.pg_params['database']}' host={self.pg_params['host']} port={self.pg_params['port']} user='{self.pg_params['username']}' password='{self.pg_params['password']}' sslmode=disable table=\"{self.pg_params['schema']}\".\"{table_name}\" (geom)"
        
        try:
            processing.run("qgis:importintopostgis", {
                'INPUT': layer,
                'DATABASE': self.pg_params['conn_name'],
                'SCHEMA': self.pg_params['schema'],
                'TABLENAME': table_name,
                'PRIMARY_KEY': 'id',
                'GEOMETRY_COLUMN': 'geom',
                'ENCODING': 'UTF-8',
                'OVERWRITE': True,
                'CREATEINDEX': True,
                'LOWERCASE_NAMES': True,
                'DROP_STRING_LENGTH': False,
                'FORCE_SINGLEPART': False
            })
            return True
        except Exception as e:
            print(f"Erreur import {table_name}: {e}")
            return False
    
    def _check_intersection(self, layer):
        """Vérifie qu'au moins une entité intersecte le filtre"""
        if not self.filter_geom or not self.filter_crs:
            return True
        
        transform = QgsCoordinateTransform(self.filter_crs, layer.crs(), QgsProject.instance())
        filter_geom_transformed = QgsGeometry(self.filter_geom)
        filter_geom_transformed.transform(transform)
        
        for feat in layer.getFeatures():
            if feat.hasGeometry() and feat.geometry().intersects(filter_geom_transformed):
                return True
        
        return False
    
    def _apply_spatial_filter(self, layer):
        """Applique un filtre spatial sur la couche"""
        transform = QgsCoordinateTransform(self.filter_crs, layer.crs(), QgsProject.instance())
        filter_geom_transformed = QgsGeometry(self.filter_geom)
        filter_geom_transformed.transform(transform)
        
        buffer_geom = filter_geom_transformed.buffer(100, 5)
        
        request = QgsFeatureRequest().setFilterRect(buffer_geom.boundingBox())
        features = [f for f in layer.getFeatures(request) if f.geometry().intersects(buffer_geom)]
        
        filtered_layer = QgsVectorLayer(f"Point?crs={layer.crs().authid()}", "filtered", "memory")
        filtered_layer.dataProvider().addAttributes(layer.fields())
        filtered_layer.updateFields()
        filtered_layer.dataProvider().addFeatures(features)
        
        return filtered_layer


def normalize_table_name(name):
    """Normalise un nom de table : minuscules, sans accents, alphanum + underscore"""
    # Enlève les accents
    name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    # Minuscules
    name = name.lower()
    # Remplace non-alphanum par underscore
    name = re.sub(r'[^a-z0-9_]', '_', name)
    # Supprime underscores multiples
    name = re.sub(r'_+', '_', name)
    # Supprime underscores début/fin
    name = name.strip('_')
    return name


class PostgresImportDialog(QDialog):
    """Dialogue d'import vers PostgreSQL"""
    
    def __init__(self, parent, selected_files, departement_layer, region_layer):
        super().__init__(parent)
        self.selected_files = selected_files
        self.departement_layer = departement_layer
        self.region_layer = region_layer
        self.import_thread = None
        
        self.setWindowTitle("Import des données sur base PostgreSQL")
        self.resize(900, 600)
        self.setModal(False)
        self.setup_ui()
    
    def setup_ui(self):
        main_layout = QHBoxLayout()
        
        # Splitter gauche/droite
        splitter = QSplitter(Qt.Horizontal)
        
        # PARTIE GAUCHE : Tableau des couches
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel(f"<b>{len(self.selected_files)} couche(s) sélectionnée(s)</b>"))
        
        self.layers_table = QTableWidget()
        self.layers_table.setColumnCount(2)
        self.layers_table.setHorizontalHeaderLabels(['Nom original', 'Nom de table'])
        self.layers_table.setRowCount(len(self.selected_files))
        
        validator = AlphanumericValidator()
        
        for row, f in enumerate(self.selected_files):
            # Nom original (lecture seule)
            name_item = QTableWidgetItem(f['name'])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.layers_table.setItem(row, 0, name_item)
            
            # Nom de table (éditable)
            table_item = QTableWidgetItem(f['name'])
            self.layers_table.setItem(row, 1, table_item)
        
        self.layers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.layers_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        left_layout.addWidget(self.layers_table)
        
        # PARTIE DROITE : Paramètres
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("<b>Paramètres d'import</b>"))
        
        # Connexion PostgreSQL
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Connexion PostgreSQL:"))
        self.conn_combo = QComboBox()
        self._load_pg_connections()
        self.conn_combo.currentIndexChanged.connect(self._on_connection_changed)
        conn_layout.addWidget(self.conn_combo)
        right_layout.addLayout(conn_layout)
        
        # Schéma (existant ou nouveau)
        schema_label_layout = QHBoxLayout()
        schema_label_layout.addWidget(QLabel("Schéma:"))
        right_layout.addLayout(schema_label_layout)
        
        self.schema_group = QButtonGroup()
        self.schema_existing_radio = QRadioButton("Schéma existant")
        self.schema_new_radio = QRadioButton("Nouveau schéma")
        self.schema_group.addButton(self.schema_existing_radio)
        self.schema_group.addButton(self.schema_new_radio)
        self.schema_existing_radio.setChecked(True)
        self.schema_existing_radio.toggled.connect(self._on_schema_type_changed)
        
        right_layout.addWidget(self.schema_existing_radio)
        right_layout.addWidget(self.schema_new_radio)
        
        self.schema_combo = QComboBox()
        self.schema_edit = QLineEdit()
        self.schema_edit.setPlaceholderText("Nom du nouveau schéma")
        self.schema_edit.setVisible(False)
        
        right_layout.addWidget(self.schema_combo)
        right_layout.addWidget(self.schema_edit)
        
        # Région
        region_layout = QHBoxLayout()
        region_layout.addWidget(QLabel("Région:"))
        self.region_combo = QComboBox()
        self.region_combo.addItem("(Aucune)", None)
        self._load_regions()
        self.region_combo.currentIndexChanged.connect(self._on_region_changed)
        region_layout.addWidget(self.region_combo)
        right_layout.addLayout(region_layout)
        
        # Département
        dept_layout = QHBoxLayout()
        dept_layout.addWidget(QLabel("Département:"))
        self.dept_combo = QComboBox()
        self.dept_combo.addItem("(Aucun)", None)
        dept_layout.addWidget(self.dept_combo)
        right_layout.addLayout(dept_layout)
        
        # Préfixe groupement
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Préfixe groupement données:"))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setValidator(AlphanumericValidator())
        self.prefix_edit.setPlaceholderText("ex: projet_2024")
        prefix_layout.addWidget(self.prefix_edit)
        right_layout.addLayout(prefix_layout)
        
        # Filtre spatial
        self.filter_check = QCheckBox("Filtrer les entités (intersection avec buffer 100m)")
        right_layout.addWidget(self.filter_check)
        
        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        right_layout.addWidget(self.progress_label)
        
        # Boutons
        buttons_layout = QHBoxLayout()
        self.import_button = QPushButton("Importer")
        self.import_button.clicked.connect(self.start_import)
        buttons_layout.addWidget(self.import_button)
        
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        right_layout.addStretch()
        right_layout.addLayout(buttons_layout)
        
        # Ajoute au splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 500])
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
    
    def _load_pg_connections(self):
        """Charge les connexions PostgreSQL"""
        from qgis.core import QgsSettings
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/connections")
        connections = settings.childGroups()
        settings.endGroup()
        
        # Déconnecte temporairement le signal pour éviter l'appel prématuré
        self.conn_combo.blockSignals(True)
        
        for conn in connections:
            self.conn_combo.addItem(conn, conn)
        
        self.conn_combo.blockSignals(False)
        
        # Charge les schémas maintenant que l'interface est prête
        if self.conn_combo.count() > 0:
            self._on_connection_changed()
    
    def _on_connection_changed(self):
        """Charge les schémas de la connexion sélectionnée"""
        if not hasattr(self, 'schema_combo'):
            return  # L'interface n'est pas encore complètement initialisée
        
        self.schema_combo.clear()
        conn_name = self.conn_combo.currentData()
        if not conn_name:
            return
        
        # Charge les schémas existants
        pg_params = self._get_pg_params(conn_name)
        if pg_params:
            schemas = self._get_schemas(pg_params)
            self.schema_combo.addItems(schemas)
    
    def _on_schema_type_changed(self):
        """Bascule entre schéma existant et nouveau"""
        is_existing = self.schema_existing_radio.isChecked()
        self.schema_combo.setVisible(is_existing)
        self.schema_edit.setVisible(not is_existing)
    
    def _get_schemas(self, pg_params):
        """Récupère la liste des schémas"""
        try:
            uri = QgsDataSourceUri()
            uri.setConnection(pg_params['host'], pg_params['port'], pg_params['database'], 
                            pg_params['username'], pg_params['password'])
            
            metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
            conn = metadata.createConnection(uri.uri(), {})
            
            return [s for s in conn.schemas() if s not in ['information_schema', 'pg_catalog']]
        except:
            return ['public']
    
    def _load_regions(self):
        """Charge les régions"""
        if not self.region_layer or not self.region_layer.isValid():
            return
        
        regions = []
        for feat in self.region_layer.getFeatures():
            nom = feat['nom']
            code = feat['code']
            if nom and code:
                regions.append((f"{nom} ({code})", code))
        
        regions.sort()
        for nom, code in regions:
            self.region_combo.addItem(nom, code)
    
    def _on_region_changed(self):
        """Met à jour les départements"""
        self.dept_combo.clear()
        self.dept_combo.addItem("(Aucun)", None)
        
        region_code = self.region_combo.currentData()
        if not region_code or not self.departement_layer or not self.departement_layer.isValid():
            return
        
        depts = []
        for feat in self.departement_layer.getFeatures():
            if feat['code_reg'] == region_code:
                nom = feat['nom']
                code = feat['code']
                if nom and code:
                    depts.append((f"{nom} ({code})", code, feat.geometry()))
        
        depts.sort()
        for nom, code, geom in depts:
            self.dept_combo.addItem(nom, {'code': code, 'geom': geom})
    
    def start_import(self):
        """Démarre l'import"""
        # Validation
        if self.conn_combo.count() == 0:
            QMessageBox.warning(self, "Erreur", "Aucune connexion PostgreSQL configurée")
            return
        
        # Vérifie doublons de noms
        table_names = {}
        for row in range(self.layers_table.rowCount()):
            name = self.layers_table.item(row, 1).text().strip()
            if name in table_names:
                QMessageBox.warning(self, "Erreur", f"Nom de table en double: '{name}'")
                return
            table_names[name] = True
        
        # Récupère schéma
        if self.schema_existing_radio.isChecked():
            schema = self.schema_combo.currentText()
        else:
            schema = self.schema_edit.text().strip()
            if not schema:
                QMessageBox.warning(self, "Erreur", "Veuillez saisir un nom de schéma")
                return
        
        # Paramètres connexion
        conn_name = self.conn_combo.currentData()
        pg_params = self._get_pg_params(conn_name)
        if not pg_params:
            QMessageBox.warning(self, "Erreur", "Impossible de lire les paramètres")
            return
        
        pg_params['schema'] = schema
        pg_params['conn_name'] = conn_name
        
        # Vérifie écrasement tables existantes
        if self.schema_existing_radio.isChecked():
            existing_tables = self._get_existing_tables(pg_params)
            tables_to_overwrite = []
            
            for row in range(self.layers_table.rowCount()):
                custom_name = self.layers_table.item(row, 1).text().strip()
                normalized = normalize_table_name(custom_name)
                
                # Ajoute préfixes
                dept_data = self.dept_combo.currentData()
                region_code = self.region_combo.currentData()
                
                if dept_data:
                    normalized = f"d{dept_data['code']}_{normalized}"
                elif region_code:
                    normalized = f"r{region_code}_{normalized}"
                
                prefix = self.prefix_edit.text().strip()
                if prefix:
                    normalized = f"{prefix}_{normalized}"
                
                if normalized in existing_tables:
                    tables_to_overwrite.append(normalized)
            
            if tables_to_overwrite:
                msg = f"Les tables suivantes seront écrasées:\n" + "\n".join(tables_to_overwrite[:10])
                if len(tables_to_overwrite) > 10:
                    msg += f"\n... et {len(tables_to_overwrite)-10} autres"
                msg += "\n\nContinuer?"
                
                reply = QMessageBox.question(self, "Confirmation", msg, 
                                            QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    return
        
        # Prépare données
        dept_data = self.dept_combo.currentData()
        region_code = self.region_combo.currentData()
        
        filter_geom = None
        filter_crs = None
        dept_code = None
        
        if self.filter_check.isChecked():
            if dept_data:
                filter_geom = dept_data['geom']
                filter_crs = self.departement_layer.crs()
                dept_code = dept_data['code']
            elif region_code:
                for feat in self.region_layer.getFeatures():
                    if feat['code'] == region_code:
                        filter_geom = feat.geometry()
                        filter_crs = self.region_layer.crs()
                        break
        
        if dept_data:
            dept_code = dept_data['code']
        
        layers_data = []
        for row, file_info in enumerate(self.selected_files):
            custom_name = self.layers_table.item(row, 1).text().strip()
            layers_data.append({
                'display_name': file_info['name'],
                'custom_name': custom_name,
                'uri': file_info['uri']
            })
        
        # Lance l'import
        self.import_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        
        self.import_thread = ImportThread(layers_data, pg_params, self.prefix_edit.text().strip(),
                                         self.filter_check.isChecked(), filter_geom, filter_crs,
                                         dept_code, region_code)
        self.import_thread.progress.connect(self.update_progress)
        self.import_thread.finished_signal.connect(self.import_finished)
        self.import_thread.start()
    
    def update_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        self.progress_label.setText(message)
    
    def import_finished(self, success, message, failed):
        self.import_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Succès", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Erreur", message)
    
    def _get_existing_tables(self, pg_params):
        """Récupère les tables existantes dans le schéma"""
        try:
            uri = QgsDataSourceUri()
            uri.setConnection(pg_params['host'], pg_params['port'], pg_params['database'],
                            pg_params['username'], pg_params['password'])
            
            metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
            conn = metadata.createConnection(uri.uri(), {})
            
            return [t.tableName() for t in conn.tables(pg_params['schema'])]
        except:
            return []
    
    def _get_pg_params(self, conn_name):
        """Récupère les paramètres de connexion"""
        from qgis.core import QgsSettings
        settings = QgsSettings()
        settings.beginGroup(f"PostgreSQL/connections/{conn_name}")
        
        params = {
            'host': settings.value('host', ''),
            'port': settings.value('port', '5432'),
            'database': settings.value('database', ''),
            'username': settings.value('username', ''),
            'password': settings.value('password', '')
        }
        
        settings.endGroup()
        
        return params if params['host'] and params['database'] else None