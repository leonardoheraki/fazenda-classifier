"""Native QGIS CSV/UI checks. Synthetic records; no trained CNN is loaded.

Call run(output_directory) in a standalone QGIS Python process for retained
test files. An isolated project is used even when called from the console.
"""
import csv
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from qgis.PyQt.QtCore import QPoint, QRect, QVariant
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import (QgsProject, QgsApplication, QgsCoordinateReferenceSystem, QgsVectorLayer,
                       QgsFeature, QgsField, QgsGeometry, QgsPointXY)
from qgis.gui import QgsMapCanvas

from ..outputs import mark_owned_output, create_species_layer
from ..tree import TreeMeasurement
from .smoke_rc4 import run as run_rc4


def run(output_directory=None):
    import importlib
    plugin = importlib.import_module(__package__.rsplit(".", 1)[0])
    case = unittest.TestCase()
    checks = run_rc4()
    temporary = tempfile.TemporaryDirectory(prefix="fazenda_csv_qgis_") if output_directory is None else None
    destination = Path(temporary.name if temporary else output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    project = QgsProject()
    work = QgsCoordinateReferenceSystem("EPSG:31982")
    project.setCrs(work)
    parent = QMainWindow()
    canvas = QgsMapCanvas(parent)
    canvas.setDestinationCrs(work)
    iface = types.SimpleNamespace(mainWindow=lambda: parent, mapCanvas=lambda: canvas)
    messages = []
    filename = [str(destination / "arvore.CSV")]
    selected_filter = ["Fazenda ECO — Árvore por copa (*.csv)"]

    def read(path, delimiter=";"):
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream, delimiter=delimiter))

    with patch.object(plugin, "QgsProject", types.SimpleNamespace(instance=lambda: project)), \
         patch.object(plugin.QMessageBox, "warning", side_effect=lambda *a: messages.append(("warning", a[-1]))), \
         patch.object(plugin.QMessageBox, "information", side_effect=lambda *a: messages.append(("info", a[-1]))), \
         patch.object(plugin.QMessageBox, "question", return_value=plugin.QMessageBox.Yes), \
         patch.object(plugin.QFileDialog, "getSaveFileName", side_effect=lambda *a: (filename[0], selected_filter[0])):
        window = plugin.MainWindow(None, str(Path(__file__).resolve().parents[1]), iface)
        try:
            window.resize(540, 600)
            window.show()
            QgsApplication.processEvents()
            for index, scroll, target in (
                (0, window.controlsScrollArea, window.exportButton),
                (1, window.conglomerateScrollArea, window.exportM37CsvButton),
                (2, window.speciesScrollArea, window.exportSpeciesCsvButton),
            ):
                window.workflowTabs.setCurrentIndex(index)
                QgsApplication.processEvents()
                scroll.ensureWidgetVisible(target)
                QgsApplication.processEvents()
                bounds = QRect(target.mapTo(scroll.viewport(), QPoint(0, 0)), target.size())
                case.assertTrue(scroll.viewport().rect().contains(bounds))
                case.assertTrue(window.mdsComboBox.isVisible())
            case.assertGreater(window.controlsScrollArea.verticalScrollBar().maximum(), 0)
            case.assertLessEqual(window.height(), 600)
            window.workflowTabs.setCurrentIndex(0)
            checks.append("CSV: each tab's export remains reachable at 540 × 600 with shared rasters visible")

            # Selection updates the UI ID but never infers a UA from another sample.
            window.validate_ortho_layer = lambda: None
            window.select_area(QgsPointXY(542374, 7192083))
            first_id = window.treeIdLineEdit.text()
            case.assertTrue(first_id.startswith("ARV_"))
            window.select_area(QgsPointXY(542375, 7192084))
            case.assertNotEqual(window.treeIdLineEdit.text(), first_id)
            case.assertEqual(window.treeUaLineEdit.text(), "")
            checks.append("CSV: native selection generates a fresh editable tree ID without inventing a UA")

            record = window._tree_record
            record.set_crown([(542370, 7192080), (542378, 7192080),
                              (542378, 7192086), (542370, 7192086)])
            record.set_height(900, 874.29)
            record.set_classification(dict(final_class="Cedrela fissilis", predicted_class="Cedrela fissilis",
                confidence=.9123456789012345, threshold=.6, status="aceita",
                prob_Araucaria_angustifolia=.05, prob_Cedrela_fissilis=.9123456789012345,
                prob_Ocotea_porosa=.0376543210987655))
            window.treeIdLineEdit.setText("0007")
            window.treeUaLineEdit.setText("001")
            window.finalize_tree_list()
            window.export_to_csv()
            rows = read(filename[0])
            case.assertEqual(len(rows), 1)
            case.assertEqual((rows[0]["arvore_id"], rows[0]["UA"]), ("0007", "001"))
            case.assertEqual(float(rows[0]["area_copa_m2"].replace(",", ".")), 48)
            case.assertEqual(float(rows[0]["confidence"].replace(",", ".")), .9123456789012345)
            case.assertNotIn("altura", rows[0])
            case.assertFalse(Path(filename[0] + ".csv").exists())
            checks.append("CSV: actual tree export callback writes canonical units, IDs and full confidence precision")

            record.classification_failed("synthetic failure")
            window.new_tree_list()
            window._tree_record = record
            window._tree_crs = work
            window.treeIdLineEdit.setText("0008")
            window.treeUaLineEdit.setText("001")
            window.finalize_tree_list()
            filename[0] = str(destination / "preservado.csv")
            Path(filename[0]).write_text("previous", encoding="utf-8")
            window.export_to_csv()
            case.assertEqual(Path(filename[0]).read_text(), "previous")
            case.assertEqual(messages[-1][0], "warning")
            checks.append("CSV: rejected/missing accepted classification preserves an existing ECO output")

            filename[0] = str(destination / "relatorio.csv")
            selected_filter[0] = "Relatório completo da árvore (*.csv)"
            window.export_to_csv()
            case.assertEqual(read(filename[0], ",")[0]["status"], "erro_processamento")
            checks.append("CSV: complete report still exports failed classifications for audit")

            points = QgsVectorLayer("Point?crs=EPSG:31982", "pontos_altura_M37", "memory")
            types_by_name = [("UA", QVariant.String), ("subparcela_id", QVariant.String),
                             ("ponto_id", QVariant.Int), ("altura_m", QVariant.Double),
                             ("status", QVariant.String), ("x_utm", QVariant.Double), ("y_utm", QVariant.Double)]
            points.dataProvider().addAttributes([QgsField(name, kind) for name, kind in types_by_name])
            points.updateFields()
            mark_owned_output(points, "pontos_altura_M37")
            for i in range(6):
                feature = QgsFeature(points.fields())
                feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(543000.25, 7192000.125)))
                feature.setAttributes(["001", "P01", i+1, float(10+i) if i < 5 else None,
                                       "valido" if i < 5 else "sem_dados_mds", 543000.25, 7192000.125])
                case.assertTrue(points.dataProvider().addFeature(feature))
            project.addMapLayer(points)
            before = [f.name() for f in points.fields()]
            filename[0] = str(destination / "conglomerados.csv")
            selected_filter[0] = "Fazenda ECO — Conglomerados (*.csv)"
            window.export_m37_points_to_csv()
            rows = read(filename[0])
            case.assertEqual(len(rows), 6)
            case.assertEqual(rows[-1]["altura_m"], "")  # Native QVariant NULL, not text 'NULL'.
            case.assertTrue(all(r["crs_trabalho"] == "EPSG:31982" for r in rows))
            case.assertEqual([f.name() for f in points.fields()], before)
            checks.append("CSV: native QVariant NULL becomes blank and layer CRS is exported without editing fields")

            layer = create_species_layer(work)
            feature = QgsFeature(layer.fields())
            feature.setAttributes(["001" if f.name() == "UA" else 1 if f.name() == "amostra_id" else None
                                   for f in layer.fields()])
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(543000, 7192000)))
            layer.dataProvider().addFeature(feature)
            project.addMapLayer(layer)
            filename[0] = str(destination / "grade_diagnostico.csv")
            window.export_species_points_to_csv()
            rows = read(filename[0])
            case.assertEqual(rows[0]["confidence"], "")
            case.assertEqual(rows[0]["unidade_registro"], "recorte_RGB_grade_nao_e_arvore")
            case.assertNotIn("area_copa_m2", rows[0])
            checks.append("CSV: grid classification remains a diagnostic and cannot manufacture individual crown measurements")

            window.new_tree_list()
            selected_filter[0] = "Fazenda ECO — Árvore por copa (*.csv)"
            classes = ("Araucaria angustifolia", "Cedrela fissilis", "Ocotea porosa")
            for i, species in enumerate(classes):
                x, y = 542374 + 20*i, 7192083
                window.select_area(QgsPointXY(x, y))
                current = window._tree_record
                current.set_height(900, 874.29) if i != 1 else current.set_height(None, None)
                current.set_classification(dict(final_class=species, predicted_class=species,
                    confidence=.8123456789012345, threshold=.6, status="aceita"))
                window.treeIdLineEdit.setText(f"{i+11:04d}")
                window.treeUaLineEdit.setText("001")
                window.delimitTreeButton.click()
                window.capture_points = [QgsPointXY(x-4, y-3), QgsPointXY(x+4, y-3),
                                         QgsPointXY(x+4, y+3), QgsPointXY(x-4, y+3)]
                window.finishDelimitationButton.click()
                case.assertTrue(window.addTreeButton.isEnabled())
                if i < 2:
                    window.addTreeButton.click()
                    case.assertIsNone(window._tree_record)
                else:
                    window.treeIdLineEdit.setText("0011")
                    window.finalizeTreesButton.click()
                    case.assertEqual(len(window._tree_batch), 2)
                    case.assertEqual(window._tree_record.area, 48)
                    case.assertFalse(window._draft_queued)
                    window.treeIdLineEdit.setText("0013")
                    window.finalizeTreesButton.click()
            window.finalize_tree_list()
            case.assertEqual(len(window._tree_batch), 3)
            case.assertEqual(window.treeListTable.rowCount(), 3)
            case.assertTrue(window.exportButton.isEnabled())
            QgsApplication.processEvents()
            window.controlsScrollArea.ensureWidgetVisible(window.exportButton)
            QgsApplication.processEvents()
            bounds = QRect(window.exportButton.mapTo(window.controlsScrollArea.viewport(), QPoint(0, 0)),
                           window.exportButton.size())
            case.assertTrue(window.controlsScrollArea.viewport().rect().contains(bounds))
            checks.append("Trees: conclude/add/finalize keeps three independent crowns without duplication")
            checks.append("Trees: a duplicate ID preserves both the list and draft until the identifier is corrected")

            with patch.object(plugin.QMessageBox, "question", return_value=plugin.QMessageBox.No):
                window.close()
            case.assertFalse(window._closed)
            case.assertEqual(len(window._tree_batch), 3)
            checks.append("Trees: cancelling panel closure preserves an unexported list")

            filename[0] = ""
            window.exportButton.click()
            case.assertTrue(window._tree_batch.dirty)
            case.assertEqual(len(window._tree_batch), 3)
            filename[0] = str(destination / "arvores_lista.csv")
            window.exportButton.click()
            rows = read(filename[0])
            case.assertEqual([r["arvore_id"] for r in rows], ["0011", "0012", "0013"])
            case.assertEqual([r["especie"] for r in rows], list(classes))
            case.assertTrue(all(float(r["area_copa_m2"].replace(",", ".")) == 48 for r in rows))
            case.assertEqual(rows[1]["altura_m"], "")
            case.assertFalse(window._tree_batch.dirty)
            checks.append("Trees: cancelling save retains data; the actual export button writes all IDs and rows")

            window.treeListTable.selectRow(1)
            window.removeTreeButton.click()
            case.assertEqual([r.arvore_id for r in window._tree_batch.records], ["0011", "0013"])
            with patch.object(plugin.QMessageBox, "question", return_value=plugin.QMessageBox.No):
                window.new_tree_list()
            case.assertEqual(len(window._tree_batch), 2)
            window.new_tree_list()
            case.assertEqual(len(window._tree_batch), 0)
            checks.append("Trees: remove affects only the selected tree and a cancelled new list retains the others")

            project.clear()
            project.setCrs(work)
            # A legacy RC7 strip layer must never be mixed with the new windows.
            legacy = QgsVectorLayer("Polygon?crs=EPSG:31982", "subparcelas_M37", "memory")
            mark_owned_output(legacy, "subparcelas_M37")
            old_feature = QgsFeature(legacy.fields())
            old_feature.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0),
                QgsPointXY(10, 100), QgsPointXY(0, 100), QgsPointXY(0, 0)]]))
            legacy.dataProvider().addFeature(old_feature)
            project.addMapLayer(legacy)
            raster = types.SimpleNamespace(crs=lambda: work)
            def sample_window(**kwargs):
                case.assertEqual((kwargs["window_width_m"], kwargs["window_length_m"]), (1, 10))
                p = kwargs["center_point"]
                return dict(status="valido", x_mds_max=p.x(), y_mds_max=p.y(),
                            mds_max=900., mdt_mdsmax=888., altura_m=12., n_pixels_janela=10)
            window.get_max_mds_in_sampling_window = sample_window
            window.create_m37_conglomerate(QgsPointXY(543000, 7192000), raster, raster)
            plots = window.get_vector_layer_by_name("conglomerados_M37")
            subplots = window.get_vector_layer_by_name("subparcelas_1x10_M37")
            points = window.get_vector_layer_by_name("pontos_altura_M37")
            case.assertEqual((plots.featureCount(), subplots.featureCount(), points.featureCount()), (1, 100, 100))
            outer = next(plots.getFeatures()).geometry().boundingBox()
            case.assertEqual((outer.width(), outer.height()), (100, 100))
            shapes = {f["subparcela_id"]: QgsGeometry(f.geometry()) for f in subplots.getFeatures()}
            for feature in points.getFeatures():
                shape = shapes[feature["subparcela_id"]]
                bounds = shape.boundingBox()
                case.assertEqual((bounds.width(), bounds.height(), shape.area()), (1, 10, 10))
                case.assertTrue(shape.intersects(feature.geometry()))
                expected_id = int(feature["ponto_id"])-1
                case.assertEqual((feature["x_utm"], feature["y_utm"]),
                    (542955 + 10*(expected_id//10), 7191955 + 10*(expected_id%10)))
            case.assertEqual(legacy.featureCount(), 1)
            case.assertEqual(next(legacy.getFeatures()).geometry().area(), 1000)
            checks.append("Plots: 100 × 100 m; 100 distinct 1 × 10 m subplots retain the original sample centers and legacy layer")

        finally:
            window.close()
            project.clear()
            parent.close()
            if temporary:
                temporary.cleanup()
    for message in checks[12:]:
        print("OK:", message)
    print(f"Integração QGIS/CSV: {len(checks)} verificações concluídas; CNN real não executada.")
    return checks
