"""Run the actual window selection/callback methods with small UI adapters.

These checks catch state/routing regressions; they do not replace a QGIS GUI test.
"""
import ast
import importlib.util
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tree_flow_record", ROOT / "tree.py")
tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tree)


class Point:
    def __init__(self, x, y): self.values = x, y
    def x(self): return self.values[0]
    def y(self): return self.values[1]


class Widget:
    def setText(self, value): self.text = value
    def setEnabled(self, value): self.enabled = value
    def reset(self, *args): pass


def window_class(project):
    source = ast.parse((ROOT / "__init__.py").read_text())
    original = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
    names = {"select_area", "_show_classification", "_show_classification_error",
             "_update_tree_classification_label", "_require_tree_crs", "finish_polygon_capture"}
    methods = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in names]
    cls = ast.ClassDef(name="Window", bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    environment = dict(
        QgsProject=types.SimpleNamespace(instance=lambda: project),
        Qt=types.SimpleNamespace(LeftButton=1),
        QgsWkbTypes=types.SimpleNamespace(PolygonGeometry=3),
        require_metric_crs=lambda crs: None, crs_label=lambda crs: crs,
        transform_point=lambda p, *args: p, TreeMeasurement=tree.TreeMeasurement,
        SpatialError=ValueError, os=__import__("os"),
        QMessageBox=types.SimpleNamespace(warning=lambda *args: None, information=lambda *args: None),
    )
    exec(compile(module, str(ROOT / "__init__.py"), "exec"), environment)
    return environment["Window"]


class WindowFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = "EPSG:31982"
        self.project = types.SimpleNamespace(crs=lambda: self.work)
        self.window = window_class(self.project)()
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


if __name__ == "__main__":
    unittest.main()
