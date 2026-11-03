import os
import csv
import traceback
import tempfile
import shutil
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QLabel,
    QComboBox,
    QFrame,
)
from qgis.PyQt.QtGui import QIcon, QColor, QImage, QPainter
from qgis.PyQt.QtCore import Qt, QVariant, QObject, pyqtSignal

from qgis.PyQt.QtWidgets import QAction
from qgis.core import (
    QgsProject,
    QgsSettings,
    QgsMessageLog,
    Qgis,
    QgsRectangle,
    QgsRasterLayer,
    QgsRaster,
    QgsRasterPipe,
    QgsRasterFileWriter,
    QgsPointXY,
    QgsWkbTypes,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsMapSettings,
    QgsMapRendererCustomPainterJob,
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand

try:
    from PIL import Image
except ImportError:
    Image = None

from .spatial import (
    SpatialError, RasterSampler, maximum_height_window,
    require_metric_crs, crs_label, transform_point,
)

from .tree import TreeMeasurement, write_tree_csv


class ClassificationSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)



class FazendaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.model = None
        self.action = None

    def initGui(self):
        self.action = QAction("Classificar Imagem", self.iface.mainWindow())
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

    def load_fazenda_model(self):
        if self.model is not None:
            return self.model
        settings = QgsSettings()
        local = os.path.join(self.plugin_dir, "fazenda_lenet_3classes_best.pth")
        model_path = settings.value("FazendaClassifier/model_path", local, type=str)
        if not os.path.isfile(model_path):
            model_path, _ = QFileDialog.getOpenFileName(
                self.iface.mainWindow(), "Selecionar modelo Fazenda LeNet (.pth)",
                os.path.expanduser("~"), "PyTorch state dict (*.pth)")
            if not model_path:
                return None
        try:
            from .fazenda_model import FazendaModel
            model = FazendaModel(model_path=model_path, confidence_threshold=0.60)
        except (ImportError, ModuleNotFoundError) as error:
            QMessageBox.warning(self.iface.mainWindow(), "Classificação indisponível",
                "A classificação requer PyTorch, torchvision e Pillow no Python do QGIS. "
                "Consulte o README. A geração de parcelas e alturas pode ser usada sem a CNN."
                f"\n\nDetalhe: {error}")
            return None
        except Exception as error:
            QgsMessageLog.logMessage(traceback.format_exc(), "Fazenda Classifier", Qgis.Critical)
            QMessageBox.warning(self.iface.mainWindow(), "Modelo não carregado", str(error))
            return None
        settings.setValue("FazendaClassifier/model_path", model_path)
        self.model = model
        return model

    def run(self):
        if not hasattr(self, "window") or self.window is None or self.window._closed:
            self.window = MainWindow(self.model, self.plugin_dir, self.iface,
                                     model_loader=self.load_fazenda_model)
            self.window.setWindowFlags(self.window.windowFlags() | Qt.WindowStaysOnTopHint)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()


class MainWindow(QMainWindow):
    def __init__(self, model, plugin_dir, iface, model_loader=None):
        super(MainWindow, self).__init__()

        self.iface = iface
        self.plugin_dir = plugin_dir
        self.model = model
        self._model_loader = model_loader
        self._closed = False
        self._sampler_cache = {}
        self._classification_pending = False
        self._classification_signals = ClassificationSignals(self)
        self._classification_signals.finished.connect(self._show_classification)
        self._classification_signals.failed.connect(self._show_classification_error)

        self.classified_species = None
        self._tree_record = None
        self._tree_crs = None
        self._tree_request = 0
        self._capture_active = False
        self.last_classification_result = None
        self.last_ua_id = None

        uic.loadUi(os.path.join(self.plugin_dir, "main_interface.ui"), self)

        # =====================================================
        # Fluxo antigo: árvore individual
        # =====================================================

        self.selectAreaButton.clicked.connect(self.activate_selection_tool_for_area)
        self.delimitTreeButton.clicked.connect(self.start_polygon_capture)
        self.finishDelimitationButton.clicked.connect(self.finish_polygon_capture)

        if hasattr(self, "exportButton"):
            self.exportButton.clicked.connect(self.export_to_csv)
            self.exportButton.setEnabled(False)

        self.executor = ThreadPoolExecutor(max_workers=1)

        self.area_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.area_tool.canvasClicked.connect(self.select_area)

        self.polygon_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.polygon_tool.canvasClicked.connect(self.add_point_to_polygon)

        self.rubber_band = QgsRubberBand(
            self.iface.mapCanvas(),
            QgsWkbTypes.PolygonGeometry,
        )
        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(2)
        self.capture_points = []

        # =====================================================
        # Fluxo M-37 + espécies por conglomerado
        # =====================================================

        self.setup_m37_controls()

        self.m37_tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.m37_tool.canvasClicked.connect(self.handle_m37_click)

        self.m37_last_layers = {
            "conglomerados": None,
            "subparcelas": None,
            "pontos": None,
            "pontos_especies": None,
        }

    # =========================================================
    # INTERFACE — M-37 E ESPÉCIES
    # =========================================================

    def setup_m37_controls(self):
        """
        Adiciona à interface os controles:
        - MDS;
        - MDT;
        - ortofoto RGB;
        - geração de conglomerado;
        - classificação de espécies por conglomerado.
        """

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.verticalLayout.addWidget(separator)

        self.m37TitleLabel = QLabel(
            "<h3>Conglomerados de Parcelas para o Fazenda ECO</h3>"
        )
        self.m37TitleLabel.setAlignment(Qt.AlignCenter)
        self.verticalLayout.addWidget(self.m37TitleLabel)

        self.mdsLabel = QLabel("Camada MDS:")
        self.verticalLayout.addWidget(self.mdsLabel)

        self.mdsComboBox = QComboBox()
        self.verticalLayout.addWidget(self.mdsComboBox)

        self.mdtLabel = QLabel("Camada MDT:")
        self.verticalLayout.addWidget(self.mdtLabel)

        self.mdtComboBox = QComboBox()
        self.verticalLayout.addWidget(self.mdtComboBox)

        self.orthoLabel = QLabel("Camada de ortofoto RGB:")
        self.verticalLayout.addWidget(self.orthoLabel)

        self.orthoComboBox = QComboBox()
        self.verticalLayout.addWidget(self.orthoComboBox)

        self.refreshRasterButton = QPushButton("Atualizar lista de rasters")
        self.refreshRasterButton.clicked.connect(self.refresh_raster_combos)
        self.verticalLayout.addWidget(self.refreshRasterButton)

        self.generateM37Button = QPushButton("Gerar Conglomerado de Parcelas")
        self.generateM37Button.clicked.connect(self.activate_m37_tool)
        self.verticalLayout.addWidget(self.generateM37Button)

        self.exportM37CsvButton = QPushButton("Exportar dados dos Conglomerados CSV")
        self.exportM37CsvButton.clicked.connect(self.export_m37_points_to_csv)
        self.verticalLayout.addWidget(self.exportM37CsvButton)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        self.verticalLayout.addWidget(separator2)

        self.speciesTitleLabel = QLabel(
            "<h3>Classificação de Espécies por Conglomerado</h3>"
        )
        self.speciesTitleLabel.setAlignment(Qt.AlignCenter)
        self.verticalLayout.addWidget(self.speciesTitleLabel)

        self.classifySpeciesCongButton = QPushButton(
            "Classificar espécies no conglomerado"
        )
        self.classifySpeciesCongButton.clicked.connect(
            self.classify_species_in_last_conglomerate
        )
        self.verticalLayout.addWidget(self.classifySpeciesCongButton)

        self.exportSpeciesCsvButton = QPushButton(
            "Exportar classificação de espécies CSV"
        )
        self.exportSpeciesCsvButton.clicked.connect(
            self.export_species_points_to_csv
        )
        self.verticalLayout.addWidget(self.exportSpeciesCsvButton)

        self.m37StatusLabel = QLabel("Conglomerados: nenhum conglomerado gerado.")
        self.m37StatusLabel.setAlignment(Qt.AlignCenter)
        self.verticalLayout.addWidget(self.m37StatusLabel)

        self.speciesStatusLabel = QLabel(
            "Espécies: nenhuma classificação executada."
        )
        self.speciesStatusLabel.setAlignment(Qt.AlignCenter)
        self.verticalLayout.addWidget(self.speciesStatusLabel)

        self.refresh_raster_combos()

    def refresh_raster_combos(self):
        """
        Lista as camadas raster carregadas no projeto para seleção de MDS, MDT e ortofoto.

        Correção aplicada:
        - prioriza automaticamente rasters RGB com 3 ou mais bandas;
        - evita selecionar por padrão camadas cinza como "Ortofoto — Banda 1 (Gray)";
        - prioriza nomes com "RGB" e "Processamento RGB" para a classificação de espécies.
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
                    "Fazenda Classifier", Qgis.Info)
        return mds, mdt

    def validate_ortho_layer(self):
        """
        Valida a ortofoto RGB selecionada.

        Correção aplicada:
        - se a camada selecionada tiver menos de 3 bandas, tenta trocar automaticamente
          para a melhor camada RGB disponível;
        - se não houver camada RGB, interrompe a classificação com aviso claro.
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

        self.iface.mapCanvas().setMapTool(self.m37_tool)

        self.m37StatusLabel.setText(
            "Conglomerados: clique no mapa para criar o centro do conglomerado."
        )

        QMessageBox.information(
            self,
            "Gerar Conglomerado de Parcelas",
            "Clique no mapa para definir o centro do conglomerado de 1 hectare.",
        )

    def handle_m37_click(self, point, button):
        if button != Qt.LeftButton:
            return
        mds, mdt = self.validate_mds_mdt_layers()
        if mds is None or mdt is None:
            return
        names = ("conglomerados_M37", "subparcelas_M37", "pontos_altura_M37")
        before = {name: {f.id() for f in layer.getFeatures()} if layer else set()
                  for name in names for layer in [self.get_vector_layer_by_name(name)]}
        previous_ua = self.last_ua_id
        try:
            project = QgsProject.instance()
            point = transform_point(point, self.iface.mapCanvas().mapSettings().destinationCrs(),
                                    project.crs(), project)
            self.create_m37_conglomerate(point, mds, mdt)
        except Exception as error:
            for name in names:
                layer = self.get_vector_layer_by_name(name)
                if layer is not None:
                    added = [f.id() for f in layer.getFeatures() if f.id() not in before[name]]
                    if added:
                        layer.dataProvider().deleteFeatures(added)
                        layer.updateExtents()
            self.last_ua_id = previous_ua
            self.m37StatusLabel.setText("Conglomerados: operação interrompida; confira o SRC e os rasters.")
            QgsMessageLog.logMessage(traceback.format_exc(), "Fazenda Classifier", Qgis.Critical)
            QMessageBox.warning(self, "Conglomerado não gerado", str(error))

    # =========================================================
    # CAMADAS VETORIAIS
    # =========================================================

    def get_vector_layer_by_name(self, name):
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == name and isinstance(layer, QgsVectorLayer):
                return layer
        return None

    def get_or_create_m37_layers(self):
        self._check_existing_output_crs()
        crs_authid = QgsProject.instance().crs().authid()

        conglomerados = self.get_vector_layer_by_name("conglomerados_M37")
        subparcelas = self.get_vector_layer_by_name("subparcelas_M37")
        pontos = self.get_vector_layer_by_name("pontos_altura_M37")

        if conglomerados is None:
            conglomerados = QgsVectorLayer(
                f"Polygon?crs={crs_authid}",
                "conglomerados_M37",
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
            QgsProject.instance().addMapLayer(conglomerados)

        if subparcelas is None:
            subparcelas = QgsVectorLayer(
                f"Polygon?crs={crs_authid}",
                "subparcelas_M37",
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
            QgsProject.instance().addMapLayer(pontos)

        for output in (conglomerados, subparcelas, pontos):
            output.setCrs(QgsProject.instance().crs())
        self._ensure_spatial_fields(pontos)
        return conglomerados, subparcelas, pontos

    def get_or_create_species_layer(self):
        self._check_existing_output_crs()
        crs_authid = QgsProject.instance().crs().authid()

        layer = self.get_vector_layer_by_name("pontos_especies_M37")

        if layer is None:
            layer = QgsVectorLayer(
                f"Point?crs={crs_authid}",
                "pontos_especies_M37",
                "memory",
            )

            pr = layer.dataProvider()

            pr.addAttributes([
                QgsField("UA", QVariant.String),
                QgsField("amostra_id", QVariant.Int),
                QgsField("linha", QVariant.Int),
                QgsField("coluna", QVariant.Int),
                QgsField("x_utm", QVariant.Double),
                QgsField("y_utm", QVariant.Double),
                QgsField("grid_size_m", QVariant.Double),
                QgsField("patch_size_m", QVariant.Double),
                QgsField("pred_class", QVariant.String),
                QgsField("final_class", QVariant.String),
                QgsField("confidence", QVariant.Double),
                QgsField("threshold", QVariant.Double),
                QgsField("status", QVariant.String),
                QgsField("prob_AA", QVariant.Double),
                QgsField("prob_CF", QVariant.Double),
                QgsField("prob_OP", QVariant.Double),
                QgsField("patch_path", QVariant.String),
                QgsField("crs_trabalho", QVariant.String),
                QgsField("crs_rgb", QVariant.String),
            ])

            layer.updateFields()
            QgsProject.instance().addMapLayer(layer)

        missing = [QgsField(name, QVariant.String) for name in ("crs_trabalho", "crs_rgb")
                   if layer.fields().indexFromName(name) < 0]
        if missing:
            layer.dataProvider().addAttributes(missing)
            layer.updateFields()
        layer.setCrs(QgsProject.instance().crs())
        return layer

    def clear_species_results_for_ua(self, species_layer, ua_id):
        """
        Remove da camada pontos_especies_M37 os registros existentes do mesmo UA.

        Evita duplicação quando a classificação do mesmo conglomerado é executada
        mais de uma vez antes da exportação do CSV.
        """

        if species_layer.fields().indexFromName("UA") < 0:
            raise SpatialError("A camada de espécies não possui o campo obrigatório UA.")

        # Validate the layer before changing records; malformed features must not
        # be silently ignored and leave duplicate samples after reclassification.
        ids_para_remover = [feat.id() for feat in species_layer.getFeatures()
                            if feat["UA"] == ua_id]

        if ids_para_remover:
            provider = species_layer.dataProvider()
            if not provider.deleteFeatures(ids_para_remover):
                raise SpatialError("Não foi possível remover os resultados anteriores desta UA. "
                                   "A reclassificação foi interrompida para evitar duplicação.")
            species_layer.updateExtents()
            species_layer.triggerRepaint()

        return len(ids_para_remover)

    def clear_species_layer_all(self):
        """Remove todos os registros da camada pontos_especies_M37, se existir."""

        species_layer = self.get_vector_layer_by_name("pontos_especies_M37")

        if species_layer is None:
            return 0

        ids_para_remover = [feat.id() for feat in species_layer.getFeatures()]

        if ids_para_remover:
            provider = species_layer.dataProvider()
            provider.deleteFeatures(ids_para_remover)
            species_layer.updateExtents()
            species_layer.triggerRepaint()

        return len(ids_para_remover)

    def generate_next_ua_id(self, conglomerados_layer):
        count = conglomerados_layer.featureCount() + 1
        return f"CG_{count:03d}"

    # =========================================================
    # ALTURA M-37
    # =========================================================

    def get_max_mds_in_sampling_window(self, mds_layer, mdt_layer, center_point,
                                       window_width_m=1.0, window_length_m=10.0):
        return maximum_height_window(self._raster_sampler(mds_layer),
            self._raster_sampler(mdt_layer), center_point, window_width_m, window_length_m)

    def create_m37_conglomerate(self, center_point, mds_layer, mdt_layer):
        conglomerados, subparcelas, pontos = self.get_or_create_m37_layers()

        ua_id = self.generate_next_ua_id(conglomerados)
        self.last_ua_id = ua_id

        x_c = center_point.x()
        y_c = center_point.y()

        half_size = 50.0
        x_min = x_c - half_size
        x_max = x_c + half_size
        y_min = y_c - half_size
        y_max = y_c + half_size

        data_criacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        square_points = [
            QgsPointXY(x_min, y_min),
            QgsPointXY(x_max, y_min),
            QgsPointXY(x_max, y_max),
            QgsPointXY(x_min, y_max),
            QgsPointXY(x_min, y_min),
        ]

        feat_cong = QgsFeature(conglomerados.fields())
        feat_cong.setGeometry(QgsGeometry.fromPolygonXY([square_points]))
        feat_cong.setAttributes([
            ua_id,
            x_c,
            y_c,
            10000.0,
            1.0,
            data_criacao,
        ])

        conglomerados.dataProvider().addFeature(feat_cong)
        conglomerados.updateExtents()

        total_points = 0
        valid_points = 0
        invalid_points = 0
        ponto_global_id = 1

        for i in range(10):
            sub_id = f"P{i + 1:02d}"

            sub_x_min = x_min + i * 10.0
            sub_x_max = sub_x_min + 10.0

            sub_points = [
                QgsPointXY(sub_x_min, y_min),
                QgsPointXY(sub_x_max, y_min),
                QgsPointXY(sub_x_max, y_max),
                QgsPointXY(sub_x_min, y_max),
                QgsPointXY(sub_x_min, y_min),
            ]

            feat_sub = QgsFeature(subparcelas.fields())
            feat_sub.setGeometry(QgsGeometry.fromPolygonXY([sub_points]))
            feat_sub.setAttributes([
                ua_id,
                sub_id,
                10.0,
                100.0,
                1000.0,
            ])
            subparcelas.dataProvider().addFeature(feat_sub)

            x_ponto = sub_x_min + 5.0

            for j in range(10):
                y_ponto = y_min + 5.0 + j * 10.0
                point_xy = QgsPointXY(x_ponto, y_ponto)

                resultado_janela = self.get_max_mds_in_sampling_window(
                    mds_layer=mds_layer,
                    mdt_layer=mdt_layer,
                    center_point=point_xy,
                    window_width_m=1.0,
                    window_length_m=10.0,
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
                    x_ponto,
                    y_ponto,
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
                pontos.dataProvider().addFeature(feat_ponto)

                ponto_global_id += 1
                total_points += 1

        subparcelas.updateExtents()
        pontos.updateExtents()

        self.iface.mapCanvas().refresh()

        self.m37StatusLabel.setText(
            f"Conglomerados: {ua_id} criado | pontos: {total_points} | "
            f"válidos: {valid_points} | inválidos: {invalid_points}"
        )

        QMessageBox.information(
            self,
            "Conglomerado de Parcelas criado",
            (
                f"Conglomerado {ua_id} criado com sucesso.\n\n"
                f"Área: 100 m × 100 m = 1 ha\n"
                f"Subparcelas: 10\n"
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

    def save_species_patch(
        self,
        ortho_layer,
        center_point,
        output_path,
        patch_size_m=8.0,
        output_pixels=128,
    ):
        """
        Recorta um patch da ortofoto usando a renderização do QGIS.

        Correção aplicada:
        - salva PNG, não GeoTIFF;
        - usa o CRS do projeto/canvas, pois os pontos do conglomerado estão nesse CRS;
        - renderiza somente a camada RGB selecionada;
        - evita selecionar camada cinza ao validar previamente a ortofoto.
        """

        output_path = os.path.splitext(output_path)[0] + ".png"

        half = patch_size_m / 2.0

        extent = QgsRectangle(
            center_point.x() - half,
            center_point.y() - half,
            center_point.x() + half,
            center_point.y() + half,
        )

        image = QImage(
            int(output_pixels),
            int(output_pixels),
            QImage.Format_RGB32,
        )
        image.fill(QColor(255, 255, 255))

        settings = QgsMapSettings()
        settings.setLayers([ortho_layer])
        settings.setExtent(extent)
        settings.setOutputSize(image.size())
        settings.setBackgroundColor(QColor(255, 255, 255))

        # Ponto crítico: usa o CRS do projeto/canvas, não apenas o CRS isolado da camada.
        settings.setDestinationCrs(QgsProject.instance().crs())
        settings.setTransformContext(QgsProject.instance().transformContext())

        painter = QPainter(image)

        try:
            job = QgsMapRendererCustomPainterJob(settings, painter)
            job.start()
            job.waitForFinished()
        finally:
            painter.end()

        saved = image.save(output_path, "PNG")

        if not saved or not os.path.exists(output_path):
            raise RuntimeError(
                f"Patch PNG não foi criado corretamente: {output_path}"
            )

        pil_img = Image.open(output_path).convert("RGB")
        arr = np.array(pil_img)

        # Evita aceitar patch completamente branco/preto/transparente.
        if arr.max() == arr.min():
            raise RuntimeError(
                "Patch gerado sem variação visual. "
                "Verifique se a camada selecionada em 'Camada de ortofoto RGB' "
                "é uma ortofoto RGB com 3 bandas e se o conglomerado está sobre ela. "
                f"Camada selecionada: {ortho_layer.name()} | Arquivo: {output_path}"
            )

        return output_path

    def classify_species_in_last_conglomerate(self):
        """
        Cria uma grade 4 m × 4 m dentro do último conglomerado M-37,
        gera 625 patches de ortofoto, aplica a CNN Fazenda_LeNet
        e grava os pontos classificados em pontos_especies_M37.

        Versão com diagnóstico do primeiro erro real.
        """

        if not self._ensure_model():
            return
        ortho_layer = self.validate_ortho_layer()

        if ortho_layer is None:
            return

        cong_feat = self.get_last_conglomerate_feature()

        if cong_feat is None:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhum conglomerado_M37 foi encontrado. "
                "Gere primeiro o conglomerado de parcelas."
            )
            return

        ua_id = cong_feat["UA"]
        geom = cong_feat.geometry()

        if geom is None or geom.isEmpty():
            QMessageBox.warning(
                self,
                "Erro",
                "O conglomerado selecionado não possui geometria válida."
            )
            return

        bbox = geom.boundingBox()

        x_min = bbox.xMinimum()
        y_min = bbox.yMinimum()

        grid_size_m = 4.0
        patch_size_m = 8.0
        n_linhas = 25
        n_colunas = 25

        species_layer = self.get_or_create_species_layer()
        provider = species_layer.dataProvider()

        # Remove resultados anteriores do mesmo conglomerado antes de nova execução.
        # Isso evita duplicação no CSV quando o usuário reprocessa o mesmo UA.
        try:
            registros_removidos = self.clear_species_results_for_ua(
                species_layer=species_layer,
                ua_id=ua_id,
            )
        except SpatialError as error:
            QMessageBox.warning(self, "Reclassificação interrompida", str(error))
            return

        temp_dir = os.path.join(
            tempfile.gettempdir(),
            "fazenda_species_patches",
            ua_id
        )

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        os.makedirs(temp_dir, exist_ok=True)

        total = 0
        processadas = 0
        rejeitadas = 0
        erro_processamento = 0
        primeiro_erro = None

        contagem_classes = {
            "Araucaria angustifolia": 0,
            "Cedrela fissilis": 0,
            "Ocotea porosa": 0,
            "espécie não identificada": 0,
        }

        QMessageBox.information(
            self,
            "Classificação de espécies",
            (
                f"Iniciando classificação de espécies no conglomerado {ua_id}.\n\n"
                f"Grade: 4 m × 4 m\n"
                f"Amostras esperadas: 625\n"
                f"Patch: {patch_size_m} m × {patch_size_m} m\n"
                f"Limiar: 0.60\n"
                f"Registros anteriores removidos deste UA: {registros_removidos}\n\n"
                f"O processamento pode levar alguns minutos."
            )
        )

        amostra_id = 1

        for linha in range(n_linhas):
            for coluna in range(n_colunas):

                x = x_min + (grid_size_m / 2.0) + coluna * grid_size_m
                y = y_min + (grid_size_m / 2.0) + linha * grid_size_m

                point_xy = QgsPointXY(float(x), float(y))
                point_geom = QgsGeometry.fromPointXY(point_xy)

                if not geom.contains(point_geom):
                    continue

                patch_name = f"{ua_id}_L{linha + 1:02d}_C{coluna + 1:02d}.png"
                patch_path = os.path.join(temp_dir, patch_name)

                try:
                    patch_path = self.save_species_patch(
                        ortho_layer=ortho_layer,
                        center_point=point_xy,
                        output_path=patch_path,
                        patch_size_m=patch_size_m,
                        output_pixels=128,
                    )

                    if not os.path.exists(patch_path):
                        raise RuntimeError(f"Patch não foi criado: {patch_path}")

                    resultado = self.model.classify_image(patch_path)

                    predicted_class = resultado.get("predicted_class")
                    final_class = resultado.get("final_class")
                    confidence = resultado.get("confidence")
                    threshold = resultado.get("threshold")
                    status = resultado.get("status")
                    prob_aa = resultado.get("prob_Araucaria_angustifolia")
                    prob_cf = resultado.get("prob_Cedrela_fissilis")
                    prob_op = resultado.get("prob_Ocotea_porosa")

                    if final_class == "espécie não identificada":
                        rejeitadas += 1

                    if final_class in contagem_classes:
                        contagem_classes[final_class] += 1

                    processadas += 1

                except Exception as e:
                    erro_processamento += 1

                    if primeiro_erro is None:
                        primeiro_erro = str(e)

                    predicted_class = None
                    final_class = "erro_processamento"
                    confidence = None
                    threshold = 0.60
                    status = f"erro_processamento: {str(e)}"
                    prob_aa = None
                    prob_cf = None
                    prob_op = None

                    print("\nERRO NA CLASSIFICAÇÃO DE ESPÉCIES")
                    print(f"UA: {ua_id}")
                    print(f"Amostra: {amostra_id}")
                    print(f"Linha: {linha + 1}")
                    print(f"Coluna: {coluna + 1}")
                    print(f"Patch: {patch_path}")
                    print(f"Erro: {e}")

                feat = QgsFeature(species_layer.fields())
                feat.setGeometry(point_geom)
                feat.setAttributes([
                    ua_id,
                    amostra_id,
                    linha + 1,
                    coluna + 1,
                    float(x),
                    float(y),
                    grid_size_m,
                    patch_size_m,
                    predicted_class,
                    final_class,
                    confidence,
                    threshold,
                    status,
                    prob_aa,
                    prob_cf,
                    prob_op,
                    patch_path,
                    crs_label(species_layer.crs()),
                    crs_label(ortho_layer.crs()),
                ])

                provider.addFeature(feat)

                amostra_id += 1
                total += 1

        species_layer.updateExtents()
        self.iface.mapCanvas().refresh()

        self.speciesStatusLabel.setText(
            f"Espécies: {ua_id} | amostras: {total} | "
            f"processadas: {processadas} | "
            f"rejeitadas: {rejeitadas} | erros: {erro_processamento}"
        )

        mensagem = (
            f"Classificação de espécies concluída para {ua_id}.\n\n"
            f"Amostras classificadas: {total}\n"
            f"Processadas: {processadas}\n"
            f"Rejeitadas como espécie não identificada: {rejeitadas}\n"
            f"Erros de processamento: {erro_processamento}\n"
            f"Registros anteriores removidos deste UA: {registros_removidos}\n\n"
            f"Resumo por classe final:\n"
            f"Araucaria angustifolia: {contagem_classes['Araucaria angustifolia']}\n"
            f"Cedrela fissilis: {contagem_classes['Cedrela fissilis']}\n"
            f"Ocotea porosa: {contagem_classes['Ocotea porosa']}\n"
            f"Espécie não identificada: {contagem_classes['espécie não identificada']}\n\n"
            f"Os patches temporários foram salvos em:\n{temp_dir}"
        )

        if primeiro_erro is not None:
            mensagem += (
                "\n\nPrimeiro erro encontrado:\n"
                f"{primeiro_erro}"
            )

        QMessageBox.information(
            self,
            "Classificação concluída",
            mensagem
        )

    # =========================================================
    # EXPORTAÇÃO CSV — ALTURA
    # =========================================================

    def export_m37_points_to_csv(self):
        pontos = self.get_vector_layer_by_name("pontos_altura_M37")

        if pontos is None or pontos.featureCount() == 0:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhuma camada pontos_altura_M37 com dados foi encontrada.",
            )
            return

        default_path = os.path.join(
            os.path.expanduser("~"),
            "Desktop",
            "pontos_altura_M37.csv",
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar dados dos Conglomerados CSV",
            default_path,
            "CSV Files (*.csv)",
        )

        if not filename:
            return

        if not filename.endswith(".csv"):
            filename += ".csv"

        try:
            self._ensure_spatial_fields(pontos)
            field_names = [
                "UA",
                "subparcela_id",
                "ponto_id",
                "x_utm",
                "y_utm",
                "x_mds_max",
                "y_mds_max",
                "mds_max",
                "mdt_mdsmax",
                "altura_m",
                "largura_janela_m",
                "comprimento_janela_m",
                "n_pixels_janela",
                "status", "crs_trabalho", "crs_mds", "crs_mdt", "metodo_altura",
            ]

            with open(filename, mode="w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(field_names)

                for feat in pontos.getFeatures():
                    writer.writerow([
                        feat["UA"],
                        feat["subparcela_id"],
                        feat["ponto_id"],
                        feat["x_utm"],
                        feat["y_utm"],
                        feat["x_mds_max"],
                        feat["y_mds_max"],
                        feat["mds_max"],
                        feat["mdt_mdsmax"],
                        feat["altura_m"],
                        feat["largura_janela_m"],
                        feat["comprimento_janela_m"],
                        feat["n_pixels_janela"],
                        feat["status"], feat["crs_trabalho"], feat["crs_mds"],
                        feat["crs_mdt"], feat["metodo_altura"],
                    ])

            QMessageBox.information(
                self,
                "Sucesso",
                f"Dados dos conglomerados exportados com sucesso:\n{filename}",
            )

        except Exception as e:
            QMessageBox.warning(
                self,
                "Erro",
                f"Erro ao exportar dados dos conglomerados: {e}",
            )

    # =========================================================
    # EXPORTAÇÃO CSV — ESPÉCIES
    # =========================================================

    def export_species_points_to_csv(self):
        species_layer = self.get_vector_layer_by_name("pontos_especies_M37")

        if species_layer is None or species_layer.featureCount() == 0:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhuma camada pontos_especies_M37 com dados foi encontrada.",
            )
            return

        default_path = os.path.join(
            os.path.expanduser("~"),
            "Desktop",
            "pontos_especies_M37.csv",
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar classificação de espécies CSV",
            default_path,
            "CSV Files (*.csv)",
        )

        if not filename:
            return

        if not filename.endswith(".csv"):
            filename += ".csv"

        try:
            field_names = [
                "UA",
                "amostra_id",
                "linha",
                "coluna",
                "x_utm",
                "y_utm",
                "grid_size_m",
                "patch_size_m",
                "predicted_class",
                "final_class",
                "confidence",
                "threshold",
                "status",
                "prob_Araucaria_angustifolia",
                "prob_Cedrela_fissilis",
                "prob_Ocotea_porosa",
                "patch_path",
                "crs_trabalho",
                "crs_rgb",
            ]

            with open(filename, mode="w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(field_names)

                for feat in species_layer.getFeatures():
                    rgb_crs = (feat["crs_rgb"]
                               if species_layer.fields().indexFromName("crs_rgb") >= 0 else None)
                    if rgb_crs is None or str(rgb_crs) in ("NULL", "None"):
                        rgb_crs = ""
                    writer.writerow([
                        feat["UA"],
                        feat["amostra_id"],
                        feat["linha"],
                        feat["coluna"],
                        feat["x_utm"],
                        feat["y_utm"],
                        feat["grid_size_m"],
                        feat["patch_size_m"],
                        feat["pred_class"],
                        feat["final_class"],
                        feat["confidence"],
                        feat["threshold"],
                        feat["status"],
                        feat["prob_AA"],
                        feat["prob_CF"],
                        feat["prob_OP"],
                        feat["patch_path"],
                        crs_label(species_layer.crs()),
                        rgb_crs,
                    ])

            QMessageBox.information(
                self,
                "Sucesso",
                f"Classificação de espécies exportada com sucesso:\n{filename}",
            )

        except Exception as e:
            QMessageBox.warning(
                self,
                "Erro",
                f"Erro ao exportar classificação de espécies: {e}",
            )

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
        self.iface.mapCanvas().setMapTool(self.area_tool)

    def select_area(self, point, button=None):
        if button is not None and button != Qt.LeftButton:
            return
        if self._classification_pending:
            QMessageBox.information(self, "Classificação em andamento",
                "Aguarde a classificação atual antes de selecionar outra árvore.")
            return
        project = QgsProject.instance()
        try:
            require_metric_crs(project.crs())
            point = transform_point(point, self.iface.mapCanvas().mapSettings().destinationCrs(),
                                    project.crs(), project)
        except SpatialError as error:
            QMessageBox.warning(self, "Seleção interrompida", str(error))
            return

        # Every valid new selection gets fresh measurements and classification state.
        self._tree_request += 1
        self._tree_crs = project.crs()
        self._tree_record = TreeMeasurement(point.x(), point.y(), crs_label(self._tree_crs))
        self.classified_species = None
        self.last_classification_result = None
        self._capture_active = False
        self.capture_points = []
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.crownDiameterLabel.setText("Diâmetro máximo da Copa: -")
        self.crownAreaLabel.setText("Área da Copa: -")
        self.exportButton.setEnabled(False)
        self.heightLabel.setText("Altura: -")
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
        self.heightLabel.setText(f"Altura: {height:.2f} m" if height is not None else "Altura: -")
        self._update_tree_classification_label()

        # Use the chosen RGB even when a vector output is the active QGIS layer.
        layer = self.validate_ortho_layer()
        if layer is None:
            self._tree_record.classification_detail = "Ortofoto RGB indisponível."
            return
        self._tree_record.crs_rgb = crs_label(layer.crs())
        if not self._ensure_model():
            self._tree_record.classification_detail = "Modelo não selecionado ou indisponível."
            return
        try:
            image_path = os.path.join(self.get_temp_folder(), f"arvore_{self._tree_request}.tif")
            if not self.save_raster_subset(layer, point, image_path):
                raise RuntimeError("Não foi possível gerar o recorte RGB.")
            self._tree_record.patch_path = os.path.splitext(image_path)[0] + ".png"
            self._tree_record.begin_classification()
            self._classification_pending = True
            self._update_tree_classification_label()
            self.executor.submit(self.auto_convert_and_classify, image_path,
                                 self._tree_request, self.model)
        except Exception as error:
            self._show_classification_error((self._tree_request, str(error)))


    def save_raster_subset(self, layer, point, output_path):
        project = QgsProject.instance()
        native = transform_point(point, self._tree_crs, layer.crs(), project)
        if not layer.extent().contains(native):
            raise SpatialError("O ponto selecionado está fora da ortofoto RGB.")
        # Preserve the original crop: 256 native pixels, output at 128 x 128.
        radius_x = 128 * abs(layer.rasterUnitsPerPixelX())
        radius_y = 128 * abs(layer.rasterUnitsPerPixelY())
        extent = QgsRectangle(native.x()-radius_x, native.y()-radius_y,
                              native.x()+radius_x, native.y()+radius_y)
        pipe = QgsRasterPipe()
        if not pipe.set(layer.dataProvider().clone()):
            raise RuntimeError("Não foi possível clonar o raster RGB.")
        writer = QgsRasterFileWriter(output_path)
        writer.setOutputFormat("GTiff")
        result = writer.writeRaster(pipe, 128, 128, extent, layer.crs(), project.transformContext())
        if result != QgsRasterFileWriter.NoError:
            raise RuntimeError(f"Erro de gravação do recorte RGB: {result}")
        return True


    def get_layer_by_name(self, name):
        for layer in QgsProject.instance().mapLayers().values():
            if layer.name() == name and isinstance(layer, QgsRasterLayer):
                return layer
        return None

    def get_raster_value_at_point(self, layer, point):
        return self._raster_sampler(layer).sample(point)

    def start_polygon_capture(self):
        try:
            self._require_tree_crs()
        except SpatialError as error:
            QMessageBox.warning(self, "Selecione a árvore", str(error))
            return
        self.tool = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.tool.canvasClicked.connect(self.handle_point_click)
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setStrokeColor(QColor(255, 0, 0))
        self.rubber_band.setFillColor(QColor(0, 0, 0, 0))
        self.rubber_band.setLineStyle(Qt.SolidLine)
        self.rubber_band.setWidth(2)
        self.capture_points = []
        self._tree_record.clear_crown()
        self._capture_active = True
        self.crownDiameterLabel.setText("Diâmetro máximo da Copa: -")
        self.crownAreaLabel.setText("Área da Copa: -")
        self.exportButton.setEnabled(False)
        self.iface.mapCanvas().setMapTool(self.tool)


    def handle_point_click(self, point, button):
        if button == Qt.LeftButton:
            self.add_point_to_polygon(point)
        elif button == Qt.RightButton:
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
        self._capture_active = False
        self.crownDiameterLabel.setText(f"Diâmetro máximo da Copa: {self._tree_record.diameter:.2f} m")
        self.crownAreaLabel.setText(f"Área da Copa: {self._tree_record.area:.2f} m²")
        self.exportButton.setEnabled(not self._classification_pending)
        self._update_tree_classification_label()
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.tool:
            canvas.unsetMapTool(self.tool)
        QMessageBox.information(self, "Delimitação concluída",
            "Copa medida. Use 'Exportar dados da árvore CSV' para salvar. "
            "Se houver classificação em andamento, aguarde sua conclusão.")
        self.raise_()
        self.activateWindow()


    def save_results_to_csv(self, species=None, height=None, crown_diameter=None,
                            crown_area=None, tree_coord=None):
        # Compatibility entry point: export only the current structured record.
        return self.export_to_csv()


    def export_to_csv(self):
        try:
            self._require_tree_crs()
            self._tree_record.as_csv_row()
            default_path = os.path.join(os.path.expanduser("~"), "resultados_classificacao.csv")
            filename, _ = QFileDialog.getSaveFileName(self, "Salvar dados da árvore CSV",
                                                       default_path, "CSV Files (*.csv)")
            if not filename:
                return
            if not filename.lower().endswith(".csv"):
                filename += ".csv"
            write_tree_csv(filename, self._tree_record)
            QMessageBox.information(self, "Sucesso", f"Dados da árvore exportados:\n{filename}")
        except Exception as error:
            QMessageBox.warning(self, "Exportação não concluída", str(error))


    def auto_convert_and_classify(self, tif_path, request_id, model):
        try:
            png_path = os.path.splitext(tif_path)[0] + ".png"
            with Image.open(tif_path) as image:
                image = image.convert("RGB").resize((128, 128))
                values = np.asarray(image)
                if values.max() == values.min():
                    raise RuntimeError("Recorte RGB sem variação visual; confira a cobertura da ortofoto.")
                image.save(png_path, "PNG")
            result = model.classify_image(png_path)
            if not self._closed:
                self._classification_signals.finished.emit((request_id, result))
        except Exception as error:
            if not self._closed:
                try:
                    self._classification_signals.failed.emit((request_id, str(error)))
                except RuntimeError:
                    pass


    def _require_tree_crs(self):
        if self._tree_record is None:
            raise SpatialError("Clique primeiro em 'Selecionar árvore' e marque seu centro no mapa.")
        project_crs = QgsProject.instance().crs()
        require_metric_crs(project_crs)
        if self._tree_crs != project_crs:
            raise SpatialError("O SRC do projeto mudou. Selecione a árvore novamente antes de continuar.")

    def _update_tree_classification_label(self):
        record = self._tree_record
        if record is None or record.classification_status == "nao_executada":
            label = "Classificação: não executada"
        elif record.classification_status == "em_processamento":
            label = "Classificação: em andamento"
        elif record.classification is None:
            label = "Classificação: erro de processamento"
        else:
            result = record.classification
            label = (f"Classe final: {result['final_class']} | "
                     f"Confiança: {result['confidence']:.2f}")
        self.resultLabel.setText(label)

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
        for name in ("conglomerados_M37", "subparcelas_M37", "pontos_altura_M37", "pontos_especies_M37"):
            layer = self.get_vector_layer_by_name(name)
            if layer is not None and layer.crs() != project_crs:
                raise SpatialError(f"A camada {name} foi criada em outro SRC. "
                    "Use o SRC em que ela foi criada ou salve e renomeie as camadas antigas "
                    "antes de gerar um novo conjunto. Os dados existentes não foram alterados.")

    def _ensure_spatial_fields(self, layer):
        fields = [QgsField(name, QVariant.String) for name in
            ("crs_trabalho", "crs_mds", "crs_mdt", "metodo_altura") if layer.fields().indexFromName(name) < 0]
        if fields:
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()

    def _ensure_model(self):
        if self.model is None and self._model_loader is not None:
            self.model = self._model_loader()
        return self.model is not None

    def _show_classification(self, payload):
        request_id, result = payload
        if self._closed or request_id != self._tree_request or self._tree_record is None:
            return
        self._classification_pending = False
        self._tree_record.set_classification(result)
        self.classified_species = result["final_class"]
        self.last_classification_result = dict(result)
        self._update_tree_classification_label()
        self.exportButton.setEnabled(self._tree_record.area is not None)


    def _show_classification_error(self, payload):
        request_id, message = payload
        if self._closed or request_id != self._tree_request or self._tree_record is None:
            return
        self._classification_pending = False
        self.classified_species = None
        self.last_classification_result = None
        self._tree_record.classification_failed(message)
        self._update_tree_classification_label()
        self.exportButton.setEnabled(self._tree_record.area is not None)
        QMessageBox.warning(self, "Classificação não executada", message)


    def closeEvent(self, event):
        self._closed = True
        canvas = self.iface.mapCanvas()
        tools = [getattr(self, name, None) for name in
                 ("area_tool", "polygon_tool", "m37_tool", "tool")]
        if canvas.mapTool() in tools:
            canvas.unsetMapTool(canvas.mapTool())
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def classFactory(iface):
    return FazendaPlugin(iface)
