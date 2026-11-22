"""Real serializers and independent reader checks; no QGIS or trained weights."""
import csv
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_tree import tree, crown

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("csv_exports_under_test", ROOT / "csv_exports.py")
exports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exports)


def measured_tree():
    record = crown(tree.TreeMeasurement(542374, 7192083, "EPSG:31982"))
    record.arvore_id, record.ua = "0007", "001"
    record.set_height(900, 874.29)
    return record


def raster_points():
    return [dict(UA="001", subparcela_id="P01", ponto_id=i + 1,
                 altura_m=float(10 + i), status="valido", x_utm=543000.25,
                 y_utm=7192000.125, crs_trabalho="EPSG:31982") for i in range(5)]


class CsvExportsTests(unittest.TestCase):


    def test_invalid_raster_sample_is_retained_with_no_height(self):
        points = raster_points()
        points.append(dict(points[0], ponto_id=6, status="sem_dados_mds", altura_m=None))
        rows = exports.prepare_conglomerate_rows(points, "EPSG:31982")
        self.assertEqual(len(rows), 6)
        self.assertIsNone(rows[-1]["altura_m"])
        self.assertEqual(rows[-1]["status"], "sem_dados_mds")
        self.assertEqual(rows[0]["unidade_registro"], "ponto_amostral_raster")
        self.assertNotIn("especie", rows[0])
        self.assertNotIn("area_copa_m2", rows[0])

    def test_five_valid_heights_required_for_each_ua_not_for_entire_file(self):
        with self.assertRaisesRegex(ValueError, "cinco alturas"):
            exports.prepare_conglomerate_rows(raster_points()[:4], "EPSG:31982")
        rows = raster_points() + [dict(raster_points()[0], UA="002")]
        with self.assertRaisesRegex(ValueError, "002"):
            exports.prepare_conglomerate_rows(rows, "EPSG:31982")

    def test_diagnostic_report_retains_samples_when_h5_cannot_be_calculated(self):
        rows = exports.prepare_conglomerate_rows(raster_points()[:4], "EPSG:31982", require_h5=False)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["perfil_csv"], "conglomerados_alturas_diagnostico")

    def test_duplicates_invalid_coordinates_and_falsely_valid_heights_are_rejected(self):
        cases = [raster_points() + [raster_points()[0]],
                 [dict(r, x_utm=float("nan")) for r in raster_points()],
                 [dict(r, altura_m=0) for r in raster_points()]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(ValueError):
                exports.prepare_conglomerate_rows(records, "EPSG:31982")


    def test_failed_validation_or_replace_preserves_existing_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.csv"
            path.write_bytes(b"previous bytes")
            with self.assertRaises(ValueError):
                exports.write_csv(path, ["x"], [{"x": float("nan")}])
            self.assertEqual(path.read_bytes(), b"previous bytes")
            with patch.object(exports.os, "replace", side_effect=PermissionError("file in use")):
                with self.assertRaises(PermissionError):
                    exports.write_csv(path, ["x"], [{"x": 1}])
            self.assertEqual(path.read_bytes(), b"previous bytes")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["old.csv"])


if __name__ == "__main__":
    unittest.main()
