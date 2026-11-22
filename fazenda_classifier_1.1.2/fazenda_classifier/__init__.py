import os
import configparser
import math
import traceback
import tempfile
from datetime import datetime

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QMainWindow,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import Qt, QVariant, pyqtSignal

from qgis.PyQt.QtGui import QAction
from qgis.core import (
    QgsProject,
    QgsMessageLog,
    Qgis,
    QgsRasterLayer,
    QgsPointXY,
    QgsWkbTypes,
    QgsVectorLayer,
    QgsVariantUtils,
    QgsCoordinateReferenceSystem,
    QgsField,
    QgsFeature,
    QgsGeometry,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand


from .spatial import (
    MetricFrame, SpatialError, RasterSampler, maximum_height_window,
    require_metric_crs, crs_label, transform_point,
)

from .tree import TreeMeasurement, TREE_CSV_FIELDS
from .tree_batch import TreeBatch
from .crown_patches import write_native_crown_tiff
from .csv_exports import CONGLOMERATE_FIELDS, prepare_conglomerate_rows, write_csv
from .outputs import find_owned_output, mark_owned_output

SAMPLING_SPACING_M = 10.0
SAMPLING_POINTS_PER_SIDE = 10
PARCEL_SIDE_M = SAMPLING_SPACING_M * SAMPLING_POINTS_PER_SIDE


class ParcelPlacementTool(QgsMapToolEmitPoint):
    moved = pyqtSignal(object)
    cancelled = pyqtSignal()

    def canvasMoveEvent(self, event):
        self.moved.emit(event.mapPoint())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class FazendaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None

    def initGui(self):
        self.action = QAction("Fazenda Classifier — Inventário", self.iface.mainWindow())
        self.action.setIcon(QIcon(os.path.join(self.plugin_dir, "icon.svg")))
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu("&Fazenda Classifier", self.action)

    def unload(self):
        if getattr(self, "window", None) is not None:
            self.window.close()
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginRasterMenu("&Fazenda Classifier", self.action)
    def run(self):
        if not hasattr(self, "window") or self.window is None or self.window._closed:
            self.window = MainWindow(self.plugin_dir, self.iface)
            self.window.setWindowFlags(self.window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()


class MainWindow(QMainWindow):
    def __init__(self, plugin_dir, iface):
        super(MainWindow, self).__init__()

        self.iface = iface
        self.plugin_dir = plugin_dir
        self._closed = False
        self._sampler_cache = {}

        self._tree_record = None
        self._tree_batch = TreeBatch()
        self._draft_queued = False
        self._queued_draft_key = None
        self._tree_crs = None
        self._tree_rgb_layer = None
        self._tree_request = 0
        self._capture_active = False
        self.last_ua_id = None

        uic.loadUi(os.path.join(self.plugin_dir, "main_interface.ui"), self)
        self._configure_panel()

        # =====================================================
        # Fluxo antigo: árvore individual
        # =====================================================

        self.selectAreaButton.clicked.connect(self.activate_selection_tool_for_area)
        self.delimitTreeButton.clicked.connect(self.start_polygon_capture)
        self.finishDelimitationButton.clicked.connect(self.finish_polygon_capture)
        self.addTreeButton.clicked.connect(self.add_another_tree)
        self.finalizeTreesButton.clicked.connect(self.finalize_tree_list)
        self.removeTreeButton.clicked.connect(self.remove_tree_from_list)
        self.newTreeListButton.clicked.connect(self.new_tree_list)
        self.treeListTable.itemSelectionChanged.connect(self._refresh_tree_batch_buttons)
        self.treeListTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((160, 100, 100, 100)):
            self.treeListTable.setColumnWidth(column, width)

        if hasattr(self, "exportButton"):
            self.exportButton.clicked.connect(self.export_to_csv)
            self.exportButton.setEnabled(False)

        self._refresh_tree_batch_ui()


        self.area_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.area_tool.canvasClicked.connect(self.select_area)

        self.polygon_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.polygon_tool.canvasClicked.connect(self.add_point_to_polygon)

        self.rubber_band = QgsRubberBand(
            self.iface.mapCanvas(),
            QgsWkbTypes.GeometryType.PolygonGeometry,
        )
        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(2)
        self.capture_points = []

        # =====================================================
        # Fluxo de parcelas e alturas
        # =====================================================

        canvas = self.iface.mapCanvas()
        self._m37_center = None
        self._m37_mode = None
        self._m37_crs = None
        self._m37_previous_tool = None
        self._m37_preview = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self._m37_preview.setStrokeColor(QColor("#ffc336"))
        self._m37_preview.setFillColor(QColor(255, 195, 54, 46))
        self._m37_preview.setWidth(2)
        self.m37_tool = ParcelPlacementTool(canvas)
        self.m37_tool.canvasClicked.connect(self.handle_m37_click)
        self.m37_tool.moved.connect(self.handle_m37_move)
        self.m37_tool.cancelled.connect(self.cancel_m37_placement)
        self.m37_tool.deactivated.connect(self._clear_m37_preview)
        self.setup_m37_controls()

        self.m37_last_layers = {
            "conglomerados": None,
            "subparcelas": None,
            "pontos": None,
        }

    # =========================================================
    # INTERFACE — PARCELAS
    # =========================================================

    def _configure_panel(self):
        """Visual setup only; the same controls retain their data and callbacks."""
        with open(os.path.join(self.plugin_dir, "panel.qss"), encoding="utf-8") as stylesheet:
            self.setStyleSheet(stylesheet.read().replace("__PLUGIN_DIR__", self.plugin_dir.replace("\\", "/")))
        icon = QIcon(os.path.join(self.plugin_dir, "icon.svg"))
        self.setWindowIcon(icon)
        self.brandIcon.setPixmap(icon.pixmap(38, 38))
        config = configparser.ConfigParser(interpolation=None)
        config.read(os.path.join(self.plugin_dir, "metadata.txt"), encoding="utf-8")
        self.versionBadge.setText(config.get("general", "version", fallback="experimental"))
        self.workflowTabs.tabBar().setExpanding(True)
        # Let long raster names elide inside the combo instead of widening the panel.
        for combo in (self.mdsComboBox, self.mdtComboBox, self.orthoComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        self.mdsComboBox.setToolTip("Modelo digital de superfície (MDS).")
        self.mdtComboBox.setToolTip("Modelo digital de terreno (MDT).")
        self.orthoComboBox.setToolTip("Ortofoto RGB usada para arquivar as copas delimitadas.")
        self.exportButton.setToolTip("Exporte as medições das árvores em CSV.")
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(660, max(540, available.width() - 40)),
                        min(800, max(560, available.height() - 60)))

    def setup_m37_controls(self):
        """Connect controls already grouped in the native tabbed interface."""
        self.refreshRasterButton.clicked.connect(self.refresh_raster_combos)
        self.generateM37Button.clicked.connect(self.activate_m37_tool)
        self.moveM37Button.clicked.connect(lambda checked: self._set_m37_mode("move" if checked else None))
        self.rotateM37Button.clicked.connect(lambda checked: self._set_m37_mode("rotate" if checked else None))
        self.m37AzimuthSpin.valueChanged.connect(self._draw_m37_preview)
        self.fixM37Button.clicked.connect(self.confirm_m37_placement)
        self.cancelM37Button.clicked.connect(self.cancel_m37_placement)
        self._m37_idle_help = self.conglomerateHelp.text()
        self.m37PlacementControls.hide()
        self.exportM37CsvButton.clicked.connect(self.export_m37_points_to_csv)
        self.refresh_raster_combos()

    def refresh_raster_combos(self):
        """
        Lista as camadas raster carregadas no projeto para seleção de MDS, MDT e ortofoto.

        Correção aplicada:
        - prioriza automaticamente rasters RGB com 3 ou mais bandas;
        - evita selecionar por padrão camadas cinza como "Ortofoto — Banda 1 (Gray)";
        - prioriza nomes com "RGB" e "Processamento RGB" para o recorte das copas.
        """

        self.mdsComboBox.clear()
        self.mdtComboBox.clear()
        self.orthoComboBox.clear()

        raster_layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                raster_layers.append(layer)

        for layer in raster_layers:
            self.mdsComboBox.addItem(layer.name(), layer.id())
            self.mdtComboBox.addItem(layer.name(), layer.id())
            self.orthoComboBox.addItem(layer.name(), layer.id())

        for i in range(self.mdsComboBox.count()):
            if self.mdsComboBox.itemText(i).strip().lower() == "mds":
                self.mdsComboBox.setCurrentIndex(i)
                break

        for i in range(self.mdtComboBox.count()):
            if self.mdtComboBox.itemText(i).strip().lower() == "mdt":
                self.mdtComboBox.setCurrentIndex(i)
                break

        best_rgb_index = self.find_best_rgb_ortho_index()
        if best_rgb_index is not None:
            self.orthoComboBox.setCurrentIndex(best_rgb_index)

    def find_best_rgb_ortho_index(self):
        """
        Encontra a melhor camada de ortofoto RGB no QComboBox.

        Critério:
        1. precisa ser raster com pelo menos 3 bandas;
        2. prioriza nomes com "processamento rgb";
        3. depois nomes com "rgb";
        4. depois nomes com "foto" ou "orto" desde que tenham 3 bandas.
        """

        candidates = []

        for i in range(self.orthoComboBox.count()):
            layer_id = self.orthoComboBox.itemData(i)
            layer = QgsProject.instance().mapLayer(layer_id)

            if not isinstance(layer, QgsRasterLayer):
                continue

            try:
                band_count = layer.dataProvider().bandCount()
            except Exception:
                band_count = 0

            if band_count < 3:
                continue

            name = layer.name().strip().lower()
            score = 0

            if "processamento rgb" in name:
                score += 100
            if "rgb" in name:
                score += 50
            if "foto" in name:
                score += 20
            if "orto" in name:
                score += 10
            if "gray" in name or "banda 1" in name:
                score -= 100

            candidates.append((score, i))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        return candidates[0][1]

    def get_selected_raster_layer(self, combo):
        layer_id = combo.currentData()

        if not layer_id:
            return None

        layer = QgsProject.instance().mapLayer(layer_id)

        if isinstance(layer, QgsRasterLayer):
            return layer

        return None

    def validate_mds_mdt_layers(self):
        mds = self.get_selected_raster_layer(self.mdsComboBox)
        mdt = self.get_selected_raster_layer(self.mdtComboBox)
        try:
            project = QgsProject.instance()
            require_metric_crs(project.crs())
            for layer, name in ((mds, "MDS"), (mdt, "MDT")):
                if layer is None or not layer.isValid() or not layer.crs().isValid():
                    raise SpatialError(f"Selecione um {name} válido, com SRC conhecido.")
            self._sampler_cache = {}
            self._raster_sampler(mds)
            self._raster_sampler(mdt)
            self._check_existing_output_crs()
        except Exception as error:
            QMessageBox.warning(self, "Não foi possível iniciar", str(error))
            return None, None
        key = (project.crs().toWkt(), mds.crs().toWkt(), mdt.crs().toWkt())
        if key != getattr(self, "_last_crs_notice", None):
            self._last_crs_notice = key
            if mds.crs() != project.crs() or mdt.crs() != project.crs():
                QgsMessageLog.logMessage(
                    "Leitura com transformação horizontal de coordenadas: "
                    f"projeto={crs_label(project.crs())}; MDS={crs_label(mds.crs())}; "
                    f"MDT={crs_label(mdt.crs())}. Os rasters não foram reamostrados.",
                    "Fazenda Classifier", Qgis.MessageLevel.Info)
        return mds, mdt

    def validate_ortho_layer(self):
        """
        Valida a ortofoto RGB selecionada.

        Correção aplicada:
        - se a camada selecionada tiver menos de 3 bandas, tenta trocar automaticamente
          para a melhor camada RGB disponível;
        - se não houver camada RGB, informa a ausência de RGB para o recorte da copa.
        """

        ortho_layer = self.get_selected_raster_layer(self.orthoComboBox)

        if ortho_layer is None:
            QMessageBox.warning(
                self,
                "Erro",
                "Selecione uma camada de ortofoto RGB.",
            )
            return None

        try:
            band_count = ortho_layer.dataProvider().bandCount()
        except Exception:
            band_count = 0

        if band_count < 3:
            best_rgb_index = self.find_best_rgb_ortho_index()

            if best_rgb_index is not None:
                self.orthoComboBox.setCurrentIndex(best_rgb_index)
                ortho_layer = self.get_selected_raster_layer(self.orthoComboBox)

                QMessageBox.information(
                    self,
                    "Ortofoto RGB ajustada",
                    (
                        "A camada selecionada originalmente não era RGB, pois possui "
                        f"apenas {band_count} banda(s).\n\n"
                        "O plugin selecionou automaticamente a melhor camada RGB disponível:\n\n"
                        f"{ortho_layer.name()}"
                    )
                )
            else:
                QMessageBox.warning(
                    self,
                    "Camada RGB não encontrada",
                    (
                        "A camada selecionada para 'Camada de ortofoto RGB' não possui 3 bandas.\n\n"
                        f"Camada atual: {ortho_layer.name()}\n"
                        f"Número de bandas: {band_count}\n\n"
                        "Selecione uma camada RGB, por exemplo 'Processamento RGB_A2', "
                        "com Banda 1 (Red), Banda 2 (Green) e Banda 3 (Blue)."
                    )
                )
                return None

        if not ortho_layer.isValid() or not ortho_layer.crs().isValid():
            QMessageBox.warning(self, "Ortofoto inválida", "Confira o SRC da ortofoto RGB.")
            return None
        try:
            require_metric_crs(QgsProject.instance().crs())
            self._check_existing_output_crs()
        except SpatialError as error:
            QMessageBox.warning(self, "SRC incompatível", str(error))
            return None

        return ortho_layer

    # =========================================================
    # ATIVAÇÃO E CLIQUE DO CONGLOMERADO
    # =========================================================

    def activate_m37_tool(self):
        mds_layer, mdt_layer = self.validate_mds_mdt_layers()

        if mds_layer is None or mdt_layer is None:
            return

        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is not self.m37_tool:
            self._m37_previous_tool = canvas.mapTool()
            canvas.setMapTool(self.m37_tool)
        self._m37_crs = QgsProject.instance().crs()
        self._m37_center = None
        self._m37_preview.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.m37AzimuthSpin.setValue(0.0)
        self._set_m37_mode(None)
        self.generateM37Button.hide()
        self.m37PlacementControls.show()
        self.conglomerateHelp.setText("Clique no mapa para marcar o centro da parcela de 1 ha.")
        canvas.setFocus()

    def handle_m37_click(self, point, button):
        if button == Qt.MouseButton.RightButton:
            self.cancel_m37_placement()
            return
        if button != Qt.MouseButton.LeftButton or self._m37_crs is None:
            return
        if self._m37_center is not None:
            if self._m37_mode is not None:
                self.handle_m37_move(point)
                self._set_m37_mode(None)
            return
        try:
            self._m37_center = self._m37_work_point(point)
        except SpatialError as error:
            self._leave_m37_placement()
            self.m37StatusLabel.setText(str(error))
            return
        self._set_m37_mode("rotate")
        self._draw_m37_preview()

    def _set_m37_mode(self, mode):
        self._m37_mode = mode
        has_center = self._m37_center is not None
        for control in (self.moveM37Button, self.rotateM37Button, self.m37AzimuthSpin, self.fixM37Button):
            control.setEnabled(has_center)
        self.moveM37Button.setChecked(mode == "move")
        self.rotateM37Button.setChecked(mode == "rotate")
        if has_center:
            if mode == "move":
                self.m37AzimuthSpin.interpretText()
            instructions = {
                "move": "Mova o cursor e clique no novo centro da parcela.",
                "rotate": "Mova o cursor para girar e clique no mapa para definir o azimute.",
                None: "Use Mover ou Girar para ajustar a prévia. Clique em Fixar parcela para gravar.",
            }
            self.conglomerateHelp.setText(instructions[mode])

    def _m37_work_point(self, point):
        project = QgsProject.instance()
        if project.crs() != self._m37_crs:
            raise SpatialError("O SRC do projeto mudou. Inicie novamente o posicionamento da parcela.")
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        return transform_point(point, canvas_crs, self._m37_crs, project)

    def handle_m37_move(self, point):
        center = self._m37_center
        if center is None or self._m37_mode is None:
            return
        try:
            target = self._m37_work_point(point)
        except SpatialError as error:
            self._leave_m37_placement()
            self.m37StatusLabel.setText(str(error))
            return
        if self._m37_mode == "move":
            self._m37_center = target
            self._draw_m37_preview()
            return
        east, north = target.x() - center.x(), target.y() - center.y()
        if east or north:
            self.m37AzimuthSpin.setValue(math.degrees(math.atan2(east, north)) % 360.0)

    def _draw_m37_preview(self):
        if self._m37_center is not None:
            frame = MetricFrame(self._m37_center, self.m37AzimuthSpin.value())
            geometry = QgsGeometry.fromPolygonXY([frame.ring(PARCEL_SIDE_M, PARCEL_SIDE_M)])
            self._m37_preview.setToGeometry(geometry, self._m37_crs)

    def _clear_m37_preview(self):
        self._m37_center = None
        self._set_m37_mode(None)
        self._m37_crs = None
        self._m37_previous_tool = None
        self._m37_preview.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.m37PlacementControls.hide()
        self.generateM37Button.show()
        self.conglomerateHelp.setText(self._m37_idle_help)
        self.m37StatusLabel.setText("Posicionamento encerrado.")

    def _leave_m37_placement(self):
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.m37_tool:
            if self._m37_previous_tool is None:
                canvas.unsetMapTool(self.m37_tool)
            else:
                canvas.setMapTool(self._m37_previous_tool)

    def cancel_m37_placement(self):
        self._leave_m37_placement()
        self.m37StatusLabel.setText("Posicionamento cancelado.")

    def confirm_m37_placement(self):
        center = self._m37_center
        if center is None:
            return
        if QgsProject.instance().crs() != self._m37_crs:
            self._leave_m37_placement()
            self.m37StatusLabel.setText("O SRC do projeto mudou. Inicie novamente o posicionamento.")
            return
        mds, mdt = self.validate_mds_mdt_layers()
        if mds is None or mdt is None:
            return
        self.m37AzimuthSpin.interpretText()
        azimuth = self.m37AzimuthSpin.value()
        self._leave_m37_placement()
        names = ("conglomerados_M37", "subparcelas_1x10_M37", "pontos_altura_M37")
        before = {name: {f.id() for f in layer.getFeatures()} if layer else set()
                  for name in names for layer in [self.get_vector_layer_by_name(name)]}
        previous_ua = self.last_ua_id
        try:
            self.create_m37_conglomerate(center, mds, mdt, azimuth=azimuth)
        except Exception as error:
            for name in names:
                layer = self.get_vector_layer_by_name(name)
                if layer is not None:
                    added = [f.id() for f in layer.getFeatures() if f.id() not in before[name]]
                    if added:
                        layer.dataProvider().deleteFeatures(added)
                        layer.updateExtents()
            self.last_ua_id = previous_ua
            self.m37StatusLabel.setText("Operação interrompida. Confira o SRC e os rasters.")
            QgsMessageLog.logMessage(traceback.format_exc(), "Fazenda Classifier", Qgis.MessageLevel.Critical)
            QMessageBox.warning(self, "Parcela não gerada", str(error))

    # =========================================================
    # CAMADAS VETORIAIS
    # =========================================================

    def get_vector_layer_by_name(self, name):
        # A matching display name alone never grants permission to edit a layer.
        return find_owned_output(QgsProject.instance(), name)

    def get_or_create_m37_layers(self):
        self._check_existing_output_crs()
        crs_authid = QgsProject.instance().crs().authid()

        conglomerados = self.get_vector_layer_by_name("conglomerados_M37")
        subparcelas = self.get_vector_layer_by_name("subparcelas_1x10_M37")
        pontos = self.get_vector_layer_by_name("pontos_altura_M37")

        if conglomerados is None:
            conglomerados = QgsVectorLayer(
                f"Polygon?crs={crs_authid}",
                "parcelas_M37",
                "memory",
            )

            pr = conglomerados.dataProvider()
            pr.addAttributes([
                QgsField("UA", QVariant.String),
                QgsField("x_centro", QVariant.Double),
                QgsField("y_centro", QVariant.Double),
                QgsField("area_m2", QVariant.Double),
                QgsField("area_ha", QVariant.Double),
                QgsField("data_criacao", QVariant.String),
            ])
            conglomerados.updateFields()
            mark_owned_output(conglomerados, "conglomerados_M37")
            QgsProject.instance().addMapLayer(conglomerados)

        if subparcelas is None:
            subparcelas = QgsVectorLayer(
                f"Polygon?crs={crs_authid}",
                "subparcelas_1x10_M37",
                "memory",
            )

            pr = subparcelas.dataProvider()
            pr.addAttributes([
                QgsField("UA", QVariant.String),
                QgsField("subparcela_id", QVariant.String),
                QgsField("largura_m", QVariant.Double),
                QgsField("comprimento_m", QVariant.Double),
                QgsField("area_m2", QVariant.Double),
            ])
            subparcelas.updateFields()
            mark_owned_output(subparcelas, "subparcelas_1x10_M37")
            QgsProject.instance().addMapLayer(subparcelas)

        if pontos is None:
            pontos = QgsVectorLayer(
                f"Point?crs={crs_authid}",
                "pontos_altura_M37",
                "memory",
            )

            pr = pontos.dataProvider()
            pr.addAttributes([
                QgsField("UA", QVariant.String),
                QgsField("subparcela_id", QVariant.String),
                QgsField("ponto_id", QVariant.Int),
                QgsField("x_utm", QVariant.Double),
                QgsField("y_utm", QVariant.Double),
                QgsField("x_mds_max", QVariant.Double),
                QgsField("y_mds_max", QVariant.Double),
                QgsField("mds_max", QVariant.Double),
                QgsField("mdt_mdsmax", QVariant.Double),
                QgsField("altura_m", QVariant.Double),
                QgsField("largura_janela_m", QVariant.Double),
                QgsField("comprimento_janela_m", QVariant.Double),
                QgsField("n_pixels_janela", QVariant.Int),
                QgsField("status", QVariant.String),
            ])
            pontos.updateFields()
            mark_owned_output(pontos, "pontos_altura_M37")
            QgsProject.instance().addMapLayer(pontos)

        for output in (conglomerados, subparcelas, pontos):
            output.setCrs(QgsProject.instance().crs())
        if conglomerados.fields().indexFromName("azimute_graus") < 0:
            if not conglomerados.dataProvider().addAttributes([QgsField("azimute_graus", QVariant.Double)]):
                raise SpatialError("Não foi possível registrar o azimute na camada de parcelas.")
            conglomerados.updateFields()
        self._ensure_spatial_fields(pontos)
        return conglomerados, subparcelas, pontos

    def generate_next_ua_id(self, conglomerados_layer):
        count = conglomerados_layer.featureCount() + 1
        return f"CG_{count:03d}"

    # =========================================================
    # ALTURA M-37
    # =========================================================

    def get_max_mds_in_sampling_window(self, mds_layer, mdt_layer, center_point,
                                       window_width_m=1.0, window_length_m=10.0, *, azimuth=0.0):
        return maximum_height_window(self._raster_sampler(mds_layer),
            self._raster_sampler(mdt_layer), center_point, window_width_m, window_length_m,
            azimuth=azimuth)

    def create_m37_conglomerate(self, center_point, mds_layer, mdt_layer, *, azimuth=0.0):
        frame = MetricFrame(center_point, azimuth)
        conglomerados, subparcelas, pontos = self.get_or_create_m37_layers()

        ua_id = self.generate_next_ua_id(conglomerados)
        half_side = PARCEL_SIDE_M / 2
        data_criacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        feat_cong = QgsFeature(conglomerados.fields())
        feat_cong.setGeometry(QgsGeometry.fromPolygonXY([frame.ring(PARCEL_SIDE_M, PARCEL_SIDE_M)]))
        for field, value in (
            ("UA", ua_id), ("x_centro", frame.x), ("y_centro", frame.y),
            ("area_m2", PARCEL_SIDE_M ** 2), ("area_ha", PARCEL_SIDE_M ** 2 / 10000),
            ("data_criacao", data_criacao), ("azimute_graus", frame.azimuth),
        ):
            feat_cong[field] = value

        valid_points = 0
        invalid_points = 0
        ponto_global_id = 1
        sub_features, point_features = [], []
        for i in range(SAMPLING_POINTS_PER_SIDE):
            east = (i + 0.5) * SAMPLING_SPACING_M - half_side
            for j in range(SAMPLING_POINTS_PER_SIDE):
                north = (j + 0.5) * SAMPLING_SPACING_M - half_side
                point_xy = frame.point(east, north)
                sub_id = f"SP_{ponto_global_id:03d}"
                sub_points = frame.ring(1.0, 10.0, east, north)
                feat_sub = QgsFeature(subparcelas.fields())
                feat_sub.setGeometry(QgsGeometry.fromPolygonXY([sub_points]))
                feat_sub.setAttributes([ua_id, sub_id, 1.0, 10.0, 10.0])
                sub_features.append(feat_sub)

                resultado_janela = self.get_max_mds_in_sampling_window(
                    mds_layer=mds_layer,
                    mdt_layer=mdt_layer,
                    center_point=point_xy,
                    window_width_m=1.0,
                    window_length_m=10.0,
                    azimuth=frame.azimuth,
                )

                status = resultado_janela["status"]

                if status == "valido":
                    valid_points += 1
                else:
                    invalid_points += 1

                feat_ponto = QgsFeature(pontos.fields())
                feat_ponto.setGeometry(QgsGeometry.fromPointXY(point_xy))
                feat_ponto.setAttributes([
                    ua_id,
                    sub_id,
                    ponto_global_id,
                    point_xy.x(),
                    point_xy.y(),
                    resultado_janela["x_mds_max"],
                    resultado_janela["y_mds_max"],
                    resultado_janela["mds_max"],
                    resultado_janela["mdt_mdsmax"],
                    resultado_janela["altura_m"],
                    1.0,
                    10.0,
                    resultado_janela["n_pixels_janela"],
                    status,
                    crs_label(QgsProject.instance().crs()),
                    crs_label(mds_layer.crs()),
                    crs_label(mdt_layer.crs()),
                    "maximo_centros_pixels_MDS_janela_metrica",
                ])
                point_features.append(feat_ponto)

                ponto_global_id += 1

        for layer, features in (
            (conglomerados, [feat_cong]), (subparcelas, sub_features), (pontos, point_features),
        ):
            success, written = layer.dataProvider().addFeatures(features)
            if not success or len(written) != len(features):
                raise SpatialError(f"Falha ao gravar a parcela na camada {layer.name()}.")
            layer.updateExtents()

        self.last_ua_id = ua_id
        total_points = len(point_features)
        self.iface.mapCanvas().refresh()

        angle_label = f"{frame.azimuth:.2f}".replace(".", ",")
        self.m37StatusLabel.setText(
            f"Parcela {ua_id} | azimute: {angle_label}° | pontos: {total_points} | "
            f"válidos: {valid_points} | inválidos: {invalid_points}"
        )

        QMessageBox.information(
            self,
            "Parcela criada",
            (
                f"Parcela {ua_id} criada com sucesso.\n\n"
                f"Área: 100 m × 100 m = 1 ha\n"
                f"Azimute: {angle_label}°\n"
                f"Subparcelas: 100, com 1 m × 10 m cada\n"
                f"Pontos totais: {total_points}\n"
                f"Pontos válidos: {valid_points}\n"
                f"Pontos inválidos: {invalid_points}\n\n"
                f"SRC de trabalho: {crs_label(QgsProject.instance().crs())}\n"
                "Coordenadas convertidas para cada raster durante a leitura.\n\n"
                f"Regra de altura aplicada:\n"
                f"maior valor entre centros de pixels do MDS na janela 1 m × 10 m, "
                f"com MDT extraído no pixel do MDS máximo."
            ),
        )

    # =========================================================
    # CLASSIFICAÇÃO DE ESPÉCIES POR CONGLOMERADO
    # =========================================================

    def get_last_conglomerate_feature(self):
        conglomerados = self.get_vector_layer_by_name("conglomerados_M37")

        if conglomerados is None or conglomerados.featureCount() == 0:
            return None

        selected = None

        if self.last_ua_id is not None:
            for feat in conglomerados.getFeatures():
                if feat["UA"] == self.last_ua_id:
                    selected = feat
                    break

        if selected is None:
            max_id = -1
            for feat in conglomerados.getFeatures():
                if feat.id() > max_id:
                    max_id = feat.id()
                    selected = feat

        return selected


    # =========================================================
    # EXPORTAÇÃO CSV — ALTURA
    # =========================================================

    @staticmethod
    def _rows_from_vector_layer(layer):
        """Read attributes only; exports never add fields or edit the source layer."""
        fields = [field.name() for field in layer.fields()]
        for feature in layer.getFeatures():
            yield {name: None if QgsVariantUtils.isNull(feature[name]) else feature[name]
                   for name in fields}

    def export_m37_points_to_csv(self):
        try:
            points = self.get_vector_layer_by_name("pontos_altura_M37")
            if points is None or points.featureCount() == 0:
                raise ValueError("Nenhuma camada pontos_altura_M37 com dados foi encontrada.")
            require_metric_crs(points.crs())
            source = list(self._rows_from_vector_layer(points))
            for row in source:
                declared = row.get("crs_trabalho")
                if declared and QgsCoordinateReferenceSystem(str(declared)) != points.crs():
                    raise ValueError("O crs_trabalho informado difere do SRC da camada de pontos.")
            filename, selected_filter = QFileDialog.getSaveFileName(
                self, "Salvar parcelas para o Fazenda ECO",
                os.path.join(os.path.expanduser("~"), "parcelas_alturas_fazenda_eco.csv"),
                "Fazenda ECO — Parcelas (*.csv);;Relatório completo dos pontos (*.csv)")
            if not filename:
                return
            if not filename.lower().endswith(".csv"):
                filename += ".csv"
            diagnostic = selected_filter.startswith("Relatório completo")
            rows = prepare_conglomerate_rows(source, crs_label(points.crs()), require_h5=not diagnostic)
            count = write_csv(filename, CONGLOMERATE_FIELDS, rows)
            message = ("Relatório completo de pontos para diagnóstico." if diagnostic else
                       "No Fazenda ECO, use o cálculo por parcela (modo Conglomerados).")
            QMessageBox.information(self, "CSV exportado",
                f"{count} pontos exportados. {message}\n{filename}")
        except Exception as error:
            QMessageBox.warning(self, "Exportação não concluída", str(error))


    # =========================================================
    # FLUXO ANTIGO — ÁRVORE INDIVIDUAL
    # =========================================================

    def get_temp_folder(self):
        folder = getattr(self, "_temp_folder", None)
        if folder is None:
            folder = tempfile.mkdtemp(prefix="fazenda_classifier_")
            self._temp_folder = folder
        return folder

    def activate_selection_tool_for_area(self):
        if self._has_unqueued_crown():
            QMessageBox.information(self, "Copa concluída",
                "Escolha 'Adicionar outra árvore' ou 'Finalizar lista' para guardar esta copa.")
            return
        self.iface.mapCanvas().setMapTool(self.area_tool)

    def _has_unqueued_crown(self):
        return (self._tree_record is not None and self._tree_record.area is not None
                and not self._draft_queued)

    def _queue_current_tree(self):
        if self._draft_queued:
            return
        self._require_tree_crs()
        if self._capture_active:
            raise ValueError("Clique em 'Concluir copa' antes de adicionar a árvore à lista.")
        key = self._tree_batch.add(self._tree_record, self.treeIdLineEdit.text(),
                                   self.treeUaLineEdit.text())
        self._queued_draft_key = key
        self._draft_queued = True

    def _reset_tree_draft(self):
        self._tree_request += 1
        self._tree_record = None
        self._tree_crs = None
        self._draft_queued = False
        self._queued_draft_key = None
        self._capture_active = False
        self.capture_points = []
        self.rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.treeIdLineEdit.clear()
        for label in (self.heightLabel, self.crownAreaLabel, self.crownDiameterLabel):
            label.setText("—")

    def add_another_tree(self):
        try:
            if self._tree_record is not None:
                self._queue_current_tree()
            elif not len(self._tree_batch):
                raise ValueError("Selecione e conclua a copa da primeira árvore.")
            self._tree_batch.resume()
            self._reset_tree_draft()
            self._refresh_tree_batch_ui()
            self.activate_selection_tool_for_area()
        except (ValueError, SpatialError) as error:
            QMessageBox.warning(self, "Árvore não adicionada", str(error))

    def finalize_tree_list(self):
        try:
            if self._tree_record is not None:
                self._queue_current_tree()
            self._tree_batch.finalize()
            self._refresh_tree_batch_ui()
            self.controlsScrollArea.ensureWidgetVisible(self.exportButton)
        except (ValueError, SpatialError) as error:
            QMessageBox.warning(self, "Lista não finalizada", str(error))

    def remove_tree_from_list(self):
        selected = self.treeListTable.selectionModel().selectedRows()
        if not selected:
            return
        removed = self._tree_batch.remove(selected[0].row())
        if self._queued_draft_key == (removed.ua, removed.arvore_id):
            self._reset_tree_draft()
        self._refresh_tree_batch_ui()

    def new_tree_list(self):
        if len(self._tree_batch) or self._has_unqueued_crown() or self.capture_points:
            answer = QMessageBox.question(self, "Iniciar nova lista?",
                "A lista atual será retirada do painel. Exporte o CSV antes de continuar se quiser guardá-la. "
                "Os arquivos já exportados serão preservados. Iniciar uma nova lista?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._tree_batch.clear()
        self._reset_tree_draft()
        self._refresh_tree_batch_ui()

    def _refresh_tree_batch_buttons(self):
        record = self._tree_record
        complete = record is not None and record.area is not None and not self._capture_active
        ready = complete or (record is None and bool(len(self._tree_batch)))
        self.selectAreaButton.setEnabled(not self._has_unqueued_crown() and not self._capture_active)
        self.delimitTreeButton.setEnabled(record is not None and not self._draft_queued)
        self.finishDelimitationButton.setEnabled(self._capture_active)
        self.addTreeButton.setEnabled(ready)
        self.finalizeTreesButton.setEnabled(ready and not self._tree_batch.finalized)
        self.removeTreeButton.setEnabled(bool(self.treeListTable.selectionModel().selectedRows()))
        self.exportButton.setEnabled(self._tree_batch.finalized
                                     and (record is None or self._draft_queued))
        self.treeIdLineEdit.setReadOnly(self._draft_queued)
        self.treeUaLineEdit.setReadOnly(self._draft_queued)

    def _refresh_tree_batch_ui(self):
        records = self._tree_batch.records
        self.treeListTable.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (record.arvore_id, record.ua,
                      "—" if record.height is None else f"{record.height:.2f}".replace(".", ","),
                      f"{record.area:.2f}".replace(".", ","))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.treeListTable.setItem(row, column, item)
        count = len(records)
        noun = "árvore" if count == 1 else "árvores"
        self.treeBatchCountLabel.setText(f"{count} {noun} na lista")
        if self._tree_batch.finalized:
            hint = "Lista finalizada. Exporte o CSV ou adicione outra árvore."
        elif self._has_unqueued_crown():
            hint = "Copa concluída. Adicione outra árvore ou finalize a lista para exportar."
        else:
            hint = "Marque a próxima árvore no mapa ou finalize a lista com as árvores já adicionadas."
        self.treeBatchHelpLabel.setText(hint)
        self.treeBatchCard.setVisible(bool(count) or self._has_unqueued_crown())
        self._refresh_tree_batch_buttons()

    def select_area(self, point, button=None):
        if button is not None and button != Qt.MouseButton.LeftButton:
            return
        if self._has_unqueued_crown():
            QMessageBox.information(self, "Copa concluída",
                "Use 'Adicionar outra árvore' ou 'Finalizar lista' para guardar a copa atual.")
            return
        project = QgsProject.instance()
        try:
            require_metric_crs(project.crs())
            point = transform_point(point, self.iface.mapCanvas().mapSettings().destinationCrs(),
                                    project.crs(), project)
        except SpatialError as error:
            QMessageBox.warning(self, "Seleção interrompida", str(error))
            return

        # Every valid new selection gets fresh measurements.
        self._tree_request += 1
        self._tree_crs = project.crs()
        self._tree_record = TreeMeasurement(point.x(), point.y(), crs_label(self._tree_crs))
        self._tree_rgb_layer = None
        self._draft_queued = False
        self._queued_draft_key = None
        self._tree_batch.resume()
        if hasattr(self, "treeIdLineEdit"):
            self.treeIdLineEdit.setText(self._tree_record.arvore_id)
        if hasattr(self, "treeUaLineEdit"):
            self._tree_record.ua = self.treeUaLineEdit.text().strip()
        self._capture_active = False
        self.capture_points = []
        self.rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.crownDiameterLabel.setText("—")
        self.crownAreaLabel.setText("—")
        self.exportButton.setEnabled(False)
        self.heightLabel.setText("—")
        self._sampler_cache = {}
        mds = self.get_selected_raster_layer(self.mdsComboBox)
        mdt = self.get_selected_raster_layer(self.mdtComboBox)
        if mds is not None and mdt is not None:
            self._tree_record.crs_mds = crs_label(mds.crs())
            self._tree_record.crs_mdt = crs_label(mdt.crs())
            try:
                self._tree_record.set_height(self.get_raster_value_at_point(mds, point),
                                             self.get_raster_value_at_point(mdt, point))
            except SpatialError as error:
                self._tree_record.height_status = "erro_leitura"
                QMessageBox.warning(self, "Altura não calculada", str(error))
        height = self._tree_record.height
        self.heightLabel.setText(f"{height:.2f} m".replace(".", ",") if height is not None else "—")
        self._refresh_tree_batch_ui()

        # RGB is optional for measurements; keep it for native crown TIFF export.
        layer = self.get_selected_raster_layer(self.orthoComboBox)
        if layer is not None:
            layer = self.validate_ortho_layer()
        if layer is not None and layer.isValid() and layer.crs().isValid():
            self._tree_record.crs_rgb = crs_label(layer.crs())
            self._tree_rgb_layer = layer

    def save_crown_subset(self, geometry):
        """Archive the delimited crown at the original raster resolution."""
        from qgis.core import QgsCoordinateTransform, QgsProviderRegistry

        layer = self._tree_rgb_layer
        if layer is None or not layer.isValid():
            raise ValueError("A ortofoto RGB da árvore não está disponível. Selecione a árvore novamente.")
        native = QgsGeometry(geometry)
        if self._tree_crs != layer.crs():
            result = native.transform(QgsCoordinateTransform(
                self._tree_crs, layer.crs(), QgsProject.instance()))
            if result != 0:
                raise ValueError("Não foi possível transformar a copa para o SRC da ortofoto.")
        if native.isEmpty() or not native.isGeosValid():
            raise ValueError("O polígono da copa é inválido no SRC da ortofoto.")
        uri = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())
        source = uri.get("path") or layer.source()
        # A new name for every completed delineation also preserves earlier
        # files if the same tree's crown is redrawn in this temporary workspace.
        descriptor, filename = tempfile.mkstemp(
            prefix=f"arvore_{self._tree_request}_copa_", suffix=".tif", dir=self.get_temp_folder())
        os.close(descriptor)
        try:
            result = write_native_crown_tiff(source, native.asWkb(), filename,
                raster_crs_wkt=layer.crs().toWkt(), tree_id=self._tree_record.arvore_id)
        except Exception:
            if os.path.isfile(filename):
                os.unlink(filename)
            raise
        return result["path"]


    def get_layer_by_name(self, name):
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == name and isinstance(layer, QgsRasterLayer):
                return layer
        return None

    def get_raster_value_at_point(self, layer, point):
        return self._raster_sampler(layer).sample(point)

    def start_polygon_capture(self):
        if self._draft_queued:
            QMessageBox.information(self, "Árvore já adicionada",
                "Use 'Adicionar outra árvore' para medir uma nova copa.")
            return
        try:
            self._require_tree_crs()
        except SpatialError as error:
            QMessageBox.warning(self, "Selecione a árvore", str(error))
            return
        self.tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool.canvasClicked.connect(self.handle_point_click)
        self.rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.rubber_band.setStrokeColor(QColor(255, 0, 0))
        self.rubber_band.setFillColor(QColor(0, 0, 0, 0))
        self.rubber_band.setLineStyle(Qt.PenStyle.SolidLine)
        self.rubber_band.setWidth(2)
        self.capture_points = []
        self._tree_record.clear_crown()
        self._capture_active = True
        self.crownDiameterLabel.setText("—")
        self.crownAreaLabel.setText("—")
        self.exportButton.setEnabled(False)
        self.iface.mapCanvas().setMapTool(self.tool)
        self._refresh_tree_batch_ui()


    def handle_point_click(self, point, button):
        if button == Qt.MouseButton.LeftButton:
            self.add_point_to_polygon(point)
        elif button == Qt.MouseButton.RightButton:
            self.remove_last_point()

    def add_point_to_polygon(self, point):
        if not self._capture_active:
            return
        try:
            self._require_tree_crs()
            work_point = transform_point(point,
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                self._tree_crs, QgsProject.instance())
        except SpatialError as error:
            QMessageBox.warning(self, "Captura interrompida", str(error))
            return
        self.capture_points.append(work_point)
        self.rubber_band.addPoint(point, True)


    def remove_last_point(self):
        if self.capture_points:
            self.capture_points.pop()
            self.rubber_band.removeLastPoint()
        else:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhum ponto para remover."
            )

    def finish_polygon_capture(self):
        try:
            self._require_tree_crs()
            if not self._capture_active or len(self.capture_points) < 3:
                raise SpatialError("Delimite a copa com pelo menos três vértices distintos.")
            ring = self.capture_points + [self.capture_points[0]]
            geometry = QgsGeometry.fromPolygonXY([ring])
            if geometry.isEmpty() or not geometry.isGeosValid():
                raise SpatialError("O polígono da copa é inválido. Confira os vértices e cruzamentos.")
            center = QgsGeometry.fromPointXY(QgsPointXY(self._tree_record.x, self._tree_record.y))
            if not geometry.intersects(center):
                raise SpatialError("O ponto da árvore está fora da copa delimitada. "
                                   "Confira a copa ou selecione novamente o centro da árvore.")
            self._tree_record.set_crown([(p.x(), p.y()) for p in self.capture_points])
        except (SpatialError, ValueError) as error:
            QMessageBox.warning(self, "Delimitação não concluída", str(error))
            return
        # A disk/RGB failure must not erase valid measurements.
        try:
            self._tree_record.crown_tiff_path = self.save_crown_subset(geometry)
            self._tree_record.crown_tiff_detail = ""
        except Exception as error:
            self._tree_record.crown_tiff_path = ""
            self._tree_record.crown_tiff_detail = str(error)
            QgsMessageLog.logMessage(traceback.format_exc(), "Fazenda Classifier", Qgis.MessageLevel.Warning)
            QMessageBox.warning(self, "Copa concluída — TIFF não salvo",
                "As medidas da copa foram mantidas, mas a imagem temporária não foi salva.\n\n"
                + str(error))
        self._capture_active = False
        self.crownDiameterLabel.setText(f"{self._tree_record.diameter:.2f} m".replace(".", ","))
        self.crownAreaLabel.setText(f"{self._tree_record.area:.2f} m²".replace(".", ","))
        self._refresh_tree_batch_ui()
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.tool:
            canvas.unsetMapTool(self.tool)
        self.controlsScrollArea.ensureWidgetVisible(self.treeDecisionFrame)
        self.raise_()
        self.activateWindow()


    def save_results_to_csv(self):
        # Compatibility entry point for the finalized list.
        return self.export_to_csv()


    def export_to_csv(self):
        try:
            if not self._tree_batch.finalized:
                raise ValueError("Clique em 'Finalizar lista' antes de exportar o CSV das árvores.")
            records = self._tree_batch.records
            default_path = os.path.join(os.path.expanduser("~"), "inventario_arvores_copas.csv")
            filename, selected_filter = QFileDialog.getSaveFileName(
                self, "Salvar inventário de árvores", default_path,
                "Relatório completo da árvore (*.csv)")
            if not filename:
                return
            if not filename.lower().endswith(".csv"):
                filename += ".csv"
            rows = [dict(record.as_csv_row(), arvore_id=record.arvore_id, UA=record.ua)
                    for record in records]
            count = write_csv(filename, ("arvore_id", "UA", *TREE_CSV_FIELDS), rows,
                              delimiter=",", decimal_comma=False)
            message = "Relatório das medições de árvores exportado."
            self._tree_batch.mark_exported()
            self._refresh_tree_batch_ui()
            QMessageBox.information(self, "CSV exportado", f"{count} árvore(s). {message}\n{filename}")
        except Exception as error:
            QMessageBox.warning(self, "Exportação não concluída", str(error))


    def _require_tree_crs(self):
        if self._tree_record is None:
            raise SpatialError("Clique primeiro em 'Selecionar árvore' e marque seu centro no mapa.")
        project_crs = QgsProject.instance().crs()
        require_metric_crs(project_crs)
        if self._tree_crs != project_crs:
            raise SpatialError("O SRC do projeto mudou. Selecione a árvore novamente antes de continuar.")


    def _raster_sampler(self, layer):
        project = QgsProject.instance()
        if layer is None:
            raise SpatialError("Selecione um raster válido.")
        key = (layer.id(), project.crs().toWkt(), layer.crs().toWkt())
        if key not in self._sampler_cache:
            self._sampler_cache[key] = RasterSampler(layer, project.crs(), project)
        return self._sampler_cache[key]

    def _check_existing_output_crs(self):
        project_crs = QgsProject.instance().crs()
        for name in ("conglomerados_M37", "subparcelas_1x10_M37", "pontos_altura_M37"):
            layer = self.get_vector_layer_by_name(name)
            if layer is not None and layer.crs() != project_crs:
                raise SpatialError(f"A saída RC4 {name} foi criada em outro SRC. "
                    "Retorne ao SRC original ou salve e remova as saídas RC4 do projeto "
                    "antes de gerar outro conjunto. Os dados existentes não foram alterados.")

    def _ensure_spatial_fields(self, layer):
        fields = [QgsField(name, QVariant.String) for name in
            ("crs_trabalho", "crs_mds", "crs_mdt", "metodo_altura") if layer.fields().indexFromName(name) < 0]
        if fields:
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()


    def closeEvent(self, event):
        if self._tree_batch.dirty or self._has_unqueued_crown():
            answer = QMessageBox.question(self, "Árvores ainda não exportadas",
                "Há árvores que ainda não foram exportadas. Fechar o painel e descartar essa lista?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._closed = True
        canvas = self.iface.mapCanvas()
        tools = [getattr(self, name, None) for name in
                 ("area_tool", "polygon_tool", "m37_tool", "tool")]
        if canvas.mapTool() in tools:
            canvas.unsetMapTool(canvas.mapTool())
        canvas.scene().removeItem(self._m37_preview)
        self.rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        super().closeEvent(event)


def classFactory(iface):
    return FazendaPlugin(iface)
