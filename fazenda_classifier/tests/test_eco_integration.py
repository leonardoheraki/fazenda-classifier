"""Serializer -> CSV bytes -> actual Fazenda ECO HTTP routes, using synthetic data.

Set FAZENDA_ECO_ROOT to the local app directory. No network, field data or
trained model is used. Tests skip when the separate app is not supplied.
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from test_csv_exports import exports, measured_tree, raster_points


APP_ROOT = os.environ.get("FAZENDA_ECO_ROOT")


@unittest.skipUnless(APP_ROOT, "Informe FAZENDA_ECO_ROOT para testar a integração com o app rev7")
class EcoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, APP_ROOT)
        import app
        cls.eco = app

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = self.eco.RESULTS_DIR
        self.eco.RESULTS_DIR = self.temp.name
        self.eco.app.config.update(TESTING=True)
        self.client = self.eco.app.test_client()

    def tearDown(self):
        self.eco.RESULTS_DIR = self.original
        self.temp.cleanup()

    def send(self, fields, rows, endpoint):
        path = Path(self.temp.name) / "entrada.csv"
        exports.write_csv(path, fields, rows)
        response = self.client.post(endpoint, data={"file": (io.BytesIO(path.read_bytes()), "entrada.CSV")},
                                    content_type="multipart/form-data")
        status, body = response.status_code, response.data
        response.close()
        response.request.close()
        return status, body

    def test_tree_export_predicts_dap_and_agc_without_renaming_any_column(self):
        import pandas as pd
        record = measured_tree()
        status, body = self.send(exports.TREE_ECO_FIELDS, exports.prepare_tree_rows([record]), "/calculate_dap_copa")
        self.assertEqual(status, 200, body)
        row = pd.read_csv(io.BytesIO(body), sep=";", decimal=",", dtype={"arvore_id": str, "ua": str}).iloc[0]
        self.assertEqual(row.arvore_id, "0007")
        self.assertEqual(row.ua, "001")
        self.assertEqual(row.especie_modelo, "Cedrela fissilis")
        self.assertGreater(row.dap_cm, 0)
        self.assertGreater(row.AGC_kg, 0)
        self.assertAlmostEqual(row.AGC_kg, row.biomassa_acima_kg * .47)

    def test_tree_without_height_produces_dap_only(self):
        import pandas as pd
        record = measured_tree()
        record.set_height(None, None)
        status, body = self.send(exports.TREE_ECO_FIELDS, exports.prepare_tree_rows([record]), "/calculate_dap_copa")
        self.assertEqual(status, 200, body)
        row = pd.read_csv(io.BytesIO(body), sep=";", decimal=",").iloc[0]
        self.assertGreater(row.dap_cm, 0)
        self.assertTrue(pd.isna(row.AGC_kg))

    def test_raster_points_compute_h5_and_fetch_included_climate_bases(self):
        import pandas as pd
        points = raster_points()
        points.append(dict(points[0], ponto_id=6, altura_m=None, status="sem_dados_mds"))
        rows = exports.prepare_conglomerate_rows(points, "EPSG:31982")
        status, body = self.send(exports.CONGLOMERATE_FIELDS, rows, "/calculate_agc_conglomerado")
        self.assertEqual(status, 200, body)
        row = pd.read_csv(io.BytesIO(body), sep=";", decimal=",").iloc[0]
        self.assertEqual(row.H5_m, 12)
        self.assertTrue(pd.notna(row.AGC_MgC_ha))


    def test_species_grid_diagnostic_cannot_be_used_as_individual_tree(self):
        rows = exports.prepare_species_diagnostic_rows([dict(UA="001", amostra_id=1,
            pred_class="Cedrela fissilis", final_class="Cedrela fissilis", status="aceita", confidence=.8)], "EPSG:31982")
        status, body = self.send(exports.SPECIES_DIAGNOSTIC_FIELDS, rows, "/calculate_dap_copa")
        self.assertEqual(status, 400, body)

    def test_many_tree_rows_keep_their_ids_and_match_individual_predictions(self):
        import pandas as pd
        records = []
        for index, species in enumerate(("Araucaria angustifolia", "Cedrela fissilis", "Ocotea porosa")):
            record = measured_tree()
            record.arvore_id = f"{index+1:04d}"
            record.classification.update(final_class=species, predicted_class=species)
            if index == 1:
                record.set_height(None, None)
            records.append(record)
        rows = exports.prepare_tree_rows(records)
        status, body = self.send(exports.TREE_ECO_FIELDS, rows, "/calculate_dap_copa")
        self.assertEqual(status, 200, body)
        batch = pd.read_csv(io.BytesIO(body), sep=";", decimal=",", dtype={"arvore_id":str})
        self.assertEqual(batch.arvore_id.tolist(), ["0001", "0002", "0003"])
        for index, row in batch.iterrows():
            status, single_body = self.send(exports.TREE_ECO_FIELDS, [rows[index]], "/calculate_dap_copa")
            self.assertEqual(status, 200, single_body)
            single = pd.read_csv(io.BytesIO(single_body), sep=";", decimal=",").iloc[0]
            self.assertAlmostEqual(row.dap_cm, single.dap_cm)
            if index == 1:
                self.assertTrue(pd.isna(row.AGC_kg))
            else:
                self.assertAlmostEqual(row.AGC_kg, single.AGC_kg)

    def test_one_failed_classification_prevents_partial_batch_prediction(self):
        rows = exports.prepare_tree_rows([measured_tree()])
        second = dict(rows[0], arvore_id="0008", status="erro_processamento")
        status, body = self.send(exports.TREE_ECO_FIELDS, [rows[0], second], "/calculate_dap_copa")
        self.assertEqual(status, 400, body)


if __name__ == "__main__":
    unittest.main()
