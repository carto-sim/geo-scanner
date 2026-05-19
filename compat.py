"""Compatibility layer for QGIS 3/4 and PyQt5/PyQt6."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QHeaderView, QMessageBox
from qgis.PyQt.QtGui import QValidator


def _attr(obj, *names):
    """Return the first attribute found on obj, supporting dotted paths."""
    for name in names:
        try:
            v = obj
            for part in name.split('.'):
                v = getattr(v, part)
            return v
        except AttributeError:
            continue
    raise AttributeError(f"None of {names!r} found on {obj!r}")


# Qt orientation  (Qt.Horizontal  →  Qt.Orientation.Horizontal in PyQt6)
Qt_Horizontal = _attr(Qt, 'Horizontal', 'Orientation.Horizontal')

# Table / list selection  (QAbstractItemView.SelectRows  →  .SelectionBehavior.SelectRows)
SelectRows = _attr(QAbstractItemView, 'SelectRows', 'SelectionBehavior.SelectRows')
MultiSelection = _attr(QAbstractItemView, 'MultiSelection', 'SelectionMode.MultiSelection')

# Header resize modes  (QHeaderView.ResizeToContents  →  .ResizeMode.ResizeToContents)
ResizeToContents = _attr(QHeaderView, 'ResizeToContents', 'ResizeMode.ResizeToContents')
HeaderStretch = _attr(QHeaderView, 'Stretch', 'ResizeMode.Stretch')

# Validator states  (QValidator.Acceptable  →  .State.Acceptable)
ValidatorAcceptable = _attr(QValidator, 'Acceptable', 'State.Acceptable')
ValidatorInvalid = _attr(QValidator, 'Invalid', 'State.Invalid')

# Item flags  (Qt.ItemIsEditable  →  Qt.ItemFlag.ItemIsEditable)
ItemIsEditable = _attr(Qt, 'ItemIsEditable', 'ItemFlag.ItemIsEditable')

# Message box buttons  (QMessageBox.Yes  →  .StandardButton.Yes)
MsgYes = _attr(QMessageBox, 'Yes', 'StandardButton.Yes')
MsgNo = _attr(QMessageBox, 'No', 'StandardButton.No')

# QGIS geometry types  (Qgis.GeometryType since 3.26 / QgsWkbTypes before)
try:
    from qgis.core import Qgis as _Qgis
    GeomPoint = _Qgis.GeometryType.Point
    GeomLine = _Qgis.GeometryType.Line
    GeomPolygon = _Qgis.GeometryType.Polygon
    GeomNull = _Qgis.GeometryType.Null
    GeomUnknown = _Qgis.GeometryType.Unknown
except AttributeError:
    from qgis.core import QgsWkbTypes as _QgsWkbTypes
    GeomPoint = _QgsWkbTypes.PointGeometry
    GeomLine = _QgsWkbTypes.LineGeometry
    GeomPolygon = _QgsWkbTypes.PolygonGeometry
    GeomNull = _QgsWkbTypes.NullGeometry
    GeomUnknown = _QgsWkbTypes.UnknownGeometry
