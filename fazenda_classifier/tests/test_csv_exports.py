"""Real serializers and independent reader checks; no QGIS or trained weights."""
import csv
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_tree import tree, crown, result

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("csv_exports_under_test", ROOT / "csv_exports.py")
exports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exports)


def measured_tree():
    record = crown(tree.TreeMeasurement(542374, 7192083, "EPSG:31982"))
    record.arvore_id, record.ua = "0007", "001"
    record.set_height(900, 874.29)
    record.set_classification(result())
    return record


def raster_points():
    return [dict(UA="001", subparcela_id="P01", ponto_id=i + 1,
                 altura_m=float(10 + i), status="valido", x_utm=543000.25,
                 y_utm=7192000.125, crs_trabalho="EPSG:31982") for i in range(5)]




class CsvExportsTests(unittest.TestCase):
    def test_tree_schema_has_explicit_units_without_duplicate_height_alias(self):
        record = measured_tree()
        row = exports.prepare_tree_rows([record])[0]
        self.assertEqual((row["arvore_id"], row["UA"]), ("0007", "001"))
        self.assertEqual(row["especie"], "Cedrela fissilis")
        self.assertAlmostEqual(row["altura_m"], 25.71)
        self.assertEqual(row["area_copa_m2"], 48)
        self.assertEqual(row["diametro_copa_max_m"], 10)
        self.assertAlmostEqual(row["diametro_copa_equivalente_m"], 7.817640190446719)
        self.assertEqual(row["unidade_registro"], "arvore_individual_delimitada")
        self.assertNotIn("altura", row)
        self.assertNotIn("area_copa", row)
        self.assertNotIn("dap_cm", row)
        self.assertNotIn("H5", row)
        self.assertEqual(len(exports.TREE_ECO_FIELDS), len(set(exports.TREE_ECO_FIELDS)))

    def test_tree_id_is_stable_for_reexport_and_unique_for_new_selection(self):
        a, b = measured_tree(), measured_tree()
        a.arvore_id = "ARV_" + "a" * 32
        self.assertEqual(exports.prepare_tree_rows([a])[0]["arvore_id"], a.arvore_id)
        a = tree.TreeMeasurement(0, 0, "EPSG:31982")
        b = tree.TreeMeasurement(0, 0, "EPSG:31982")
        self.assertNotEqual(a.arvore_id, b.arvore_id)
        self.assertEqual(a.ua, "")

    def test_rejected_missing_or_failed_classification_is_not_an_accepted_species(self):
        for status in ("abaixo_do_limiar", "nao_executada", "erro_processamento"):
            with self.subTest(status=status):
                record = measured_tree()
                if status == "abaixo_do_limiar":
                    record.set_classification(result(False))
                elif status == "nao_executada":
                    record.classification = None
                    record.classification_status = status
                else:
                    record.classification_failed("sem RGB")
                with self.assertRaisesRegex(ValueError, "classificação aceita"):
                    exports.prepare_tree_rows([record])
                # The separate complete report remains available for audit.
                self.assertEqual(record.as_csv_row()["status"], status)

    def test_accepted_class_must_have_coherent_probability_units(self):
        for change in ({"confidence": 80}, {"confidence": .59}, {"threshold": None},
                       {"final_class": "espécie não identificada"}):
            record = measured_tree()
            record.classification.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                exports.prepare_tree_rows([record])

    def test_no_height_exports_blank_for_dap_only_without_inventing_zero(self):
        record = measured_tree()
        record.set_height(None, 100)
        row = exports.prepare_tree_rows([record])[0]
        self.assertIsNone(row["altura_m"])
        self.assertEqual(row["calculo_disponivel"], "somente_DAP")
        self.assertEqual(row["status_altura"], "sem_dados_mds_ou_mdt")

    def test_duplicate_tree_ids_in_same_ua_are_rejected(self):
        a, b = measured_tree(), measured_tree()
        with self.assertRaisesRegex(ValueError, "repetidos"):
            exports.prepare_tree_rows([a, b])
        b.ua = "002"
        self.assertEqual(len(exports.prepare_tree_rows([a, b])), 2)

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

    def test_grid_diagnostic_preserves_rejection_and_cannot_claim_a_tree_area(self):
        source = dict(UA="001", amostra_id=1, pred_class="Cedrela fissilis",
                      final_class="espécie não identificada", confidence=.5921592712402344,
                      threshold=.6, status="abaixo_do_limiar", prob_CF=.5921592712402344)
        row = exports.prepare_species_diagnostic_rows([source], "EPSG:31982")[0]
        self.assertEqual(row["predicted_class"], "Cedrela fissilis")
        self.assertEqual(row["confidence"], .5921592712402344)
        self.assertEqual(row["status"], "abaixo_do_limiar")
        self.assertEqual(row["prob_Cedrela_fissilis"], .5921592712402344)
        self.assertEqual(row["unidade_registro"], "recorte_RGB_grade_nao_e_arvore")
        self.assertNotIn("area_copa_m2", row)
        self.assertNotIn("especie", row)






    def test_writer_uses_bom_semicolon_decimal_comma_and_full_precision(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "copas.CSV"
            record = measured_tree()
            record.classification["confidence"] = .9123456789012345
            rows = exports.prepare_tree_rows([record])
            exports.write_csv(path, exports.TREE_ECO_FIELDS, rows)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(row["arvore_id"], "0007")
            self.assertEqual(row["UA"], "001")
            self.assertEqual(float(row["confidence"].replace(",", ".")), .9123456789012345)
            self.assertEqual(float(row["area_copa_m2"].replace(",", ".")), 48)
            self.assertTrue(row["crown_coords"].startswith("[["))

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
