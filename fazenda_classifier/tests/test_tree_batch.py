"""State and data-retention checks for multi-tree exports; synthetic crowns."""
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

from test_csv_exports import exports, measured_tree
from test_tree import tree

spec = importlib.util.spec_from_file_location("tree_batch_under_test", Path(__file__).resolve().parents[1] / "tree_batch.py")
batch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch_module)


class TreeBatchTests(unittest.TestCase):
    def setUp(self):
        self.batch = batch_module.TreeBatch()

    def test_next_measurement_cannot_change_a_queued_crown_or_classification(self):
        record = measured_tree()
        original = record.as_csv_row()
        self.batch.add(record, "0001", "001")
        record.clear_crown()
        record.classification_failed("next selection")
        saved = self.batch.records[0]
        self.assertEqual(saved.as_csv_row()["crown_coords"], original["crown_coords"])
        self.assertEqual(saved.classification["confidence"], original["confidence"])
        self.assertEqual(saved.arvore_id, "0001")
        self.assertEqual(saved.ua, "001")

    def test_duplicate_id_in_one_plot_is_rejected_without_replacing_a_tree(self):
        record = measured_tree()
        self.batch.add(record, "01", "001")
        with self.assertRaisesRegex(ValueError, "já está na lista"):
            self.batch.add(record, " 01 ", "001")
        self.assertEqual(len(self.batch), 1)
        self.batch.add(record, "01", "002")
        self.assertEqual(len(self.batch), 2)

    def test_incomplete_or_pending_measurement_cannot_be_added(self):
        record = measured_tree()
        record.clear_crown()
        with self.assertRaises(ValueError):
            self.batch.add(record, "01")
        record = measured_tree()
        record.begin_classification()
        with self.assertRaisesRegex(ValueError, "Aguarde"):
            self.batch.add(record, "01")
        self.assertEqual(len(self.batch), 0)

    def test_finalizing_twice_does_not_duplicate_records_and_adding_reopens_list(self):
        with self.assertRaises(ValueError):
            self.batch.finalize()
        self.batch.add(measured_tree(), "01")
        self.batch.finalize()
        self.batch.finalize()
        self.assertEqual(len(self.batch), 1)
        self.batch.mark_exported()
        self.assertFalse(self.batch.dirty)
        self.batch.add(measured_tree(), "02")
        self.assertFalse(self.batch.finalized)
        self.assertTrue(self.batch.dirty)

    def test_multi_tree_csv_keeps_ids_order_units_and_probability_precision(self):
        for i in range(3):
            record = measured_tree()
            record.classification["confidence"] = 0.8123456789012345
            if i == 1:
                record.set_height(None, None)
            self.batch.add(record, f"{i + 1:04d}", "001")
        self.batch.finalize()
        rows = exports.prepare_tree_rows(self.batch.records)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trees.csv"
            exports.write_csv(path, exports.TREE_ECO_FIELDS, rows)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual([r["arvore_id"] for r in saved], ["0001", "0002", "0003"])
        self.assertTrue(all(r["UA"] == "001" and r["area_copa_m2"] == "48,0" for r in saved))
        self.assertEqual(saved[1]["altura_m"], "")
        self.assertEqual(saved[2]["confidence"], "0,8123456789012345")

    def test_rejected_tree_blocks_whole_eco_list_and_complete_report_keeps_all_rows(self):
        self.batch.add(measured_tree(), "01")
        failed = measured_tree()
        failed.classification_failed("synthetic missing RGB")
        self.batch.add(failed, "02")
        with self.assertRaisesRegex(ValueError, "02"):
            exports.prepare_tree_rows(self.batch.records)
        rows = [dict(r.as_csv_row(), arvore_id=r.arvore_id, UA=r.ua) for r in self.batch.records]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            exports.write_csv(path, ("arvore_id", "UA", *tree.TREE_CSV_FIELDS), rows,
                              delimiter=",", decimal_comma=False)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream))
        self.assertEqual([r["arvore_id"] for r in saved], ["01", "02"])
        self.assertEqual(saved[1]["status"], "erro_processamento")
        self.assertEqual(saved[0]["area_copa"], "48.0")

    def test_removal_and_new_list_preserve_other_records_and_reset_export_state(self):
        for key in ("01", "02", "03"):
            self.batch.add(measured_tree(), key)
        self.batch.finalize()
        self.batch.mark_exported()
        self.batch.remove(1)
        self.assertEqual([r.arvore_id for r in self.batch.records], ["01", "03"])
        self.assertTrue(self.batch.dirty)
        self.batch.clear()
        self.assertEqual(len(self.batch), 0)
        self.assertFalse(self.batch.finalized)
        self.assertFalse(self.batch.dirty)

    def test_returned_records_are_independent_copies(self):
        self.batch.add(measured_tree(), "01")
        self.batch.records[0].classification_failed("external edit")
        self.assertEqual(self.batch.records[0].classification_status, "aceita")
