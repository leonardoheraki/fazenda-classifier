"""Regression tests for stale measurements, geometry and CSV output.

Run with python -m unittest discover -s tests from the plugin directory.
No QGIS or trained model is required for these state and numerical checks.
"""
import csv
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tree_under_test", ROOT / "tree.py")
tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tree)


def crown(record):
    record.set_crown([(542370, 7192080), (542378, 7192080),
                      (542378, 7192086), (542370, 7192086)])
    return record


class TreeTests(unittest.TestCase):
    def record(self):
        return tree.TreeMeasurement(542374, 7192083, "EPSG:31982")

    def test_metric_rectangle_at_large_utm_coordinates(self):
        record = crown(self.record())
        self.assertEqual(record.area, 48)
        self.assertEqual(record.diameter, 10)
        # Diameter is the maximum span; it is not derived from an equivalent circle.
        self.assertNotAlmostEqual(record.diameter, 2 * math.sqrt(record.area/math.pi))

    def test_area_remains_stable_after_large_coordinate_translation(self):
        points = [(0, 0), (0.1, 0), (0.1, 0.1), (0, 0.1)]
        _, area = tree.crown_metrics([(x+542374, y+7192083) for x, y in points])
        self.assertAlmostEqual(area, 0.01, places=9)

    def test_crown_rejects_line_duplicate_vertices_and_nonfinite_coordinates(self):
        for coordinates in ([(0, 0), (1, 1)], [(0, 0)]*3,
                            [(0, 0), (1, 1), (2, 2)],
                            [(0, 0), (1, 0), (float("nan"), 1)]):
            with self.subTest(coordinates=coordinates), self.assertRaises(ValueError):
                tree.crown_metrics(coordinates)

    def test_closed_ring_has_same_metrics(self):
        points = [(0, 0), (8, 0), (8, 6), (0, 6)]
        self.assertEqual(tree.crown_metrics(points), tree.crown_metrics(points+[points[0]]))


    def test_new_tree_cannot_inherit_previous_tree_measurements(self):
        previous = crown(self.record())
        previous.set_height(900, 874.29)
        current = self.record()
        self.assertIsNone(current.height)
        self.assertIsNone(current.area)


    def test_incomplete_crown_cannot_be_exported(self):
        with self.assertRaises(ValueError):
            self.record().as_csv_row()

    def test_height_missing_nodata_nonpositive_clears_old_height(self):
        record = self.record()
        for top, ground in ((None, 100), (120, None), (float("nan"), 100),
                            (100, 100), (99, 100)):
            record.set_height(120, 100)
            record.set_height(top, ground)
            self.assertIsNone(record.height)
            self.assertNotEqual(record.height_status, "valido")

    def test_csv_includes_area_crs_and_selected_center_not_first_vertex(self):
        record = crown(self.record())
        record.crs_mds = record.crs_mdt = record.crs_rgb = "EPSG:31982"
        record.set_height(900, 874.29)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"tree.csv"
            tree.write_tree_csv(path, record)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(float(row["area_copa"]), 48)
        self.assertEqual(float(row["diametro_copa"]), 10)
        self.assertAlmostEqual(float(row["altura"]), 25.71)
        self.assertEqual(row["crs_trabalho"], "EPSG:31982")
        self.assertEqual(row["coord_tree"], "(542374.0, 7192083.0)")
        self.assertNotEqual((float(row["x_arvore"]), float(row["y_arvore"])), record.coordinates[0])
        self.assertIn("7192080.0", row["crown_coords"])


if __name__ == "__main__":
    unittest.main()
