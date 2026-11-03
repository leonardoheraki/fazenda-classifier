"""Run the actual window selection/callback methods with small UI adapters.

These checks catch state/routing regressions; they do not replace a QGIS GUI test.
"""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Point:
    def __init__(self, x, y): self.values = x, y
    def x(self): return self.values[0]
    def y(self): return self.values[1]


class Widget:
    def setText(self, value): self.text = value
    def setEnabled(self, value): self.enabled = value
    def reset(self, *args): pass


def window_class(project):
    """Import the actual plugin with isolated adapters, without generating code.

    The real QGIS constructor is deliberately not called. Only API calls outside
    these routing/state checks are adapted, and sys.modules is restored on exit.
    """
    modules = {name: types.ModuleType(name) for name in (
        "qgis", "qgis.PyQt", "qgis.PyQt.uic", "qgis.PyQt.QtWidgets",
        "qgis.PyQt.QtGui", "qgis.PyQt.QtCore", "qgis.core", "qgis.gui",
        "numpy", "PIL",
    )}
    for name in ("qgis", "qgis.PyQt", "PIL"):
        modules[name].__path__ = []
    modules["qgis.PyQt"].uic = modules["qgis.PyQt.uic"]
    modules["PIL"].Image = None
    groups = {
        "qgis.PyQt.QtWidgets": (
            "QFileDialog QMessageBox QMainWindow QPushButton QLabel QComboBox QFrame QAction"
        ),
        "qgis.PyQt.QtGui": "QIcon QColor QImage QPainter",
        "qgis.PyQt.QtCore": "QVariant QObject",
        "qgis.core": (
            "QgsSettings QgsMessageLog Qgis QgsRectangle QgsRasterLayer QgsRaster "
            "QgsRasterPipe QgsRasterFileWriter QgsVectorLayer QgsField QgsFeature "
            "QgsGeometry QgsMapSettings QgsMapRendererCustomPainterJob "
            "QgsCoordinateTransform QgsUnitTypes"
        ),
        "qgis.gui": "QgsMapToolEmitPoint QgsRubberBand",
    }
    for module_name, names in groups.items():
        for name in names.split():
            setattr(modules[module_name], name, type(name, (), {}))
    modules["qgis.PyQt.QtCore"].Qt = types.SimpleNamespace(LeftButton=1)
    modules["qgis.PyQt.QtCore"].pyqtSignal = lambda *args: None
    core = modules["qgis.core"]
    core.QgsProject = types.SimpleNamespace(instance=lambda: project)
    core.QgsWkbTypes = types.SimpleNamespace(PolygonGeometry=3)
    core.QgsPointXY = Point
    core.QgsCsException = RuntimeError
    modules["qgis.PyQt.QtWidgets"].QMessageBox = types.SimpleNamespace(
        warning=lambda *args: None, information=lambda *args: None,
    )
    package = "_fazenda_headless_plugin"
    spec = importlib.util.spec_from_file_location(
        package, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)],
    )
    plugin = importlib.util.module_from_spec(spec)
    modules[package] = plugin
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(plugin)
    plugin.require_metric_crs = lambda crs: None
    plugin.crs_label = lambda crs: crs
    plugin.transform_point = lambda point, *args: point
    return plugin.MainWindow


class SpeciesFeature:
    def __init__(self, feature_id, ua_id):
        self.feature_id, self.ua_id = feature_id, ua_id

    def id(self):
        return self.feature_id

    def __getitem__(self, name):
        if name != "UA":
            raise KeyError(name)
        return self.ua_id


class SpeciesLayer:
    def __init__(self, *, has_ua=True, can_delete=True):
        self.has_ua, self.can_delete = has_ua, can_delete
        self.features = [SpeciesFeature(1, "CG_001"), SpeciesFeature(2, "CG_002"),
                         SpeciesFeature(3, "CG_001")]
        self.delete_calls = []

    def fields(self):
        return types.SimpleNamespace(indexFromName=lambda name: 0 if self.has_ua else -1)

    def getFeatures(self):
        return iter(self.features)

    def dataProvider(self):
        return self

    def deleteFeatures(self, ids):
        self.delete_calls.append(list(ids))
        if self.can_delete:
            self.features = [f for f in self.features if f.id() not in ids]
        return self.can_delete

    def updateExtents(self):
        return None

    def triggerRepaint(self):
        return None


class WindowFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = "EPSG:31982"
        self.project = types.SimpleNamespace(crs=lambda: self.work)
        window_type = window_class(self.project)
        self.window = window_type.__new__(window_type)
        w = self.window
        w._closed = False
        w._classification_pending = False
        w._tree_request = 0
        w._tree_record = None
        w._tree_crs = None
        w._capture_active = False
        w.capture_points = []
        for name in ("crownDiameterLabel", "crownAreaLabel", "exportButton", "heightLabel",
                     "resultLabel", "rubber_band"):
            setattr(w, name, Widget())
        w.iface = types.SimpleNamespace(mapCanvas=lambda: types.SimpleNamespace(
            mapSettings=lambda: types.SimpleNamespace(destinationCrs=lambda: self.work)))
        w.mdsComboBox, w.mdtComboBox = object(), object()
        self.mds = types.SimpleNamespace(crs=lambda: self.work)
        self.mdt = types.SimpleNamespace(crs=lambda: self.work)
        self.rgb = types.SimpleNamespace(crs=lambda: self.work)
        w.get_selected_raster_layer = lambda c: self.mds if c is w.mdsComboBox else self.mdt
        w.get_raster_value_at_point = lambda layer, point: 120 if layer is self.mds else 100
        w.validate_ortho_layer = lambda: self.rgb
        w._ensure_model = lambda: True
        w.model = object()
        w.get_temp_folder = lambda: self.directory.name
        self.crops, self.jobs = [], []
        w.save_raster_subset = lambda layer, point, path: self.crops.append(layer) or True
        w.executor = types.SimpleNamespace(submit=lambda *args: self.jobs.append(args))
        w.auto_convert_and_classify = lambda *args: None

    def completed_result(self):
        return dict(final_class="Cedrela fissilis", predicted_class="Cedrela fissilis",
                    confidence=0.8, threshold=0.6, status="aceita")

    def test_selection_uses_chosen_rgb_without_querying_active_vector_layer(self):
        self.window.select_area(Point(10, 20), 1)
        self.assertIs(self.crops[0], self.rgb)
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.window._tree_record.height, 20)
        self.assertTrue(self.window._classification_pending)
        self.assertEqual(self.window._tree_record.classification_status, "em_processamento")

    def test_new_selection_clears_previous_inference_height_and_crown(self):
        w = self.window
        w.select_area(Point(10, 20), 1)
        w._show_classification((w._tree_request, self.completed_result()))
        w._tree_record.set_crown([(9, 19), (11, 19), (11, 21), (9, 21)])
        w.get_raster_value_at_point = lambda *args: None
        w._ensure_model = lambda: False
        w.select_area(Point(50, 60), 1)
        self.assertEqual((w._tree_record.x, w._tree_record.y), (50, 60))
        self.assertIsNone(w._tree_record.height)
        self.assertIsNone(w._tree_record.area)
        self.assertIsNone(w.last_classification_result)
        self.assertIsNone(w.classified_species)
        self.assertEqual(w._tree_record.classification_status, "nao_executada")
        self.assertFalse(w.exportButton.enabled)

    def test_old_worker_callback_cannot_fill_a_new_tree(self):
        w = self.window
        w.select_area(Point(10, 20), 1)
        old_id = w._tree_request
        w._show_classification((old_id, self.completed_result()))
        w._ensure_model = lambda: False
        w.select_area(Point(50, 60), 1)
        w._show_classification((old_id, self.completed_result()))
        self.assertIsNone(w._tree_record.classification)
        self.assertEqual(w._tree_record.classification_status, "nao_executada")

    def test_pending_worker_blocks_a_new_selection(self):
        w = self.window
        w.select_area(Point(10, 20), 1)
        w.select_area(Point(50, 60), 1)
        self.assertEqual(w._tree_request, 1)
        self.assertEqual((w._tree_record.x, w._tree_record.y), (10, 20))
        self.assertEqual(len(self.jobs), 1)

    def test_polygon_cannot_finalize_with_only_two_vertices(self):
        w = self.window
        w._ensure_model = lambda: False
        w.select_area(Point(10, 20), 1)
        w.capture_points = [Point(0, 0), Point(1, 1)]
        w._capture_active = True
        w.finish_polygon_capture()
        self.assertIsNone(w._tree_record.area)

    def test_changed_project_crs_blocks_crown_and_export(self):
        w = self.window
        w._ensure_model = lambda: False
        w.select_area(Point(10, 20), 1)
        self.work = "EPSG:32722"
        with self.assertRaises(ValueError):
            w._require_tree_crs()

    def test_reclassification_removes_only_the_selected_ua(self):
        layer = SpeciesLayer()
        self.assertEqual(self.window.clear_species_results_for_ua(layer, "CG_001"), 2)
        self.assertEqual([feature.id() for feature in layer.features], [2])
        self.assertEqual(layer.delete_calls, [[1, 3]])

    def test_missing_ua_field_cannot_delete_existing_samples(self):
        layer = SpeciesLayer(has_ua=False)
        with self.assertRaisesRegex(ValueError, "campo obrigatório UA"):
            self.window.clear_species_results_for_ua(layer, "CG_001")
        self.assertEqual(len(layer.features), 3)
        self.assertEqual(layer.delete_calls, [])

    def test_failed_deletion_stops_reclassification(self):
        layer = SpeciesLayer(can_delete=False)
        with self.assertRaisesRegex(ValueError, "evitar duplicação"):
            self.window.clear_species_results_for_ua(layer, "CG_001")
        self.assertEqual(len(layer.features), 3)


if __name__ == "__main__":
    unittest.main()
