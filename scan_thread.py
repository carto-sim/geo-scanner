"""Thread pour scanner les fichiers en arrière-plan"""

from qgis.PyQt.QtCore import QThread, pyqtSignal
import time


class ScanThread(QThread):
    """Thread pour scanner les fichiers en arrière-plan"""
    progress = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(list, float)
    
    def __init__(self, plugin, folder_path):
        super().__init__()
        self.plugin = plugin
        self.folder_path = folder_path
        self.is_canceled = False
    
    def cancel(self):
        self.is_canceled = True
    
    def run(self):
        start_time = time.time()
        geo_files = self.plugin.scan_folder(self.folder_path, self)
        elapsed_time = time.time() - start_time
        
        if not self.is_canceled:
            self.finished_signal.emit(geo_files, elapsed_time)