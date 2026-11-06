"""One selected tree and one CSV schema, independent of the QGIS interface."""
import csv
import json
import math
import uuid
from pathlib import Path


PROBABILITY_FIELDS = (
    "prob_Araucaria_angustifolia", "prob_Cedrela_fissilis", "prob_Ocotea_porosa",
)
TREE_CSV_FIELDS = (
    "especie", "predicted_class", "final_class", "confidence", "threshold", "status",
    *PROBABILITY_FIELDS, "altura", "diametro_copa", "area_copa", "coord_tree",
    "crown_coords", "x_arvore", "y_arvore", "crs_trabalho", "crs_mds", "crs_mdt",
    "crs_rgb", "mds_no_ponto", "mdt_no_ponto", "status_altura", "metodo_altura",
    "metodo_diametro", "metodo_area", "metodo_classificacao", "patch_path",
    "detalhe_classificacao",
)


def crown_metrics(coordinates):
    """Planar polygon area and maximum vertex distance, in metric work units.

    GEOS topology validation is performed by the QGIS caller before this function.
    Translate the ring before the area sum to avoid cancellation at large UTM XY.
    """
    points = [(float(x), float(y)) for x, y in coordinates]
    if points and points[-1] == points[0]:
        points.pop()
    if len(set(points)) < 3 or not all(math.isfinite(v) for p in points for v in p):
        raise ValueError("A copa precisa de pelo menos três vértices distintos e válidos.")
    x0, y0 = points[0]
    local = [(x-x0, y-y0) for x, y in points]
    area = abs(math.fsum(x*local[(i+1) % len(local)][1]
                        - local[(i+1) % len(local)][0]*y
                        for i, (x, y) in enumerate(local))) / 2
    if area <= 0:
        raise ValueError("O polígono da copa precisa ter área maior que zero.")
    diameter = max(math.hypot(x2-x1, y2-y1)
                   for i, (x1, y1) in enumerate(local) for x2, y2 in local[i+1:])
    return diameter, area


class TreeMeasurement:
    def __init__(self, x, y, crs_work):
        self.arvore_id = "ARV_" + uuid.uuid4().hex
        self.ua = ""
        self.x, self.y = float(x), float(y)
        self.crs_work = crs_work
        self.crs_mds = self.crs_mdt = self.crs_rgb = ""
        self.mds = self.mdt = self.height = None
        self.height_status = "nao_executada"
        self.classification = None
        self.classification_status = "nao_executada"
        self.classification_detail = ""
        self.patch_path = ""
        self.clear_crown()

    def clear_crown(self):
        self.coordinates = []
        self.diameter = self.area = None

    def set_height(self, mds, mdt):
        self.mds, self.mdt = mds, mdt
        self.height = None
        if mds is None or mdt is None or not all(math.isfinite(v) for v in (mds, mdt)):
            self.height_status = "sem_dados_mds_ou_mdt"
        elif mds <= mdt:
            self.height_status = "altura_invalida"
        else:
            self.height = float(mds-mdt)
            self.height_status = "valido"

    def set_crown(self, coordinates):
        diameter, area = crown_metrics(coordinates)
        self.coordinates = [(float(x), float(y)) for x, y in coordinates]
        self.diameter, self.area = diameter, area

    def begin_classification(self):
        self.classification = None
        self.classification_status = "em_processamento"
        self.classification_detail = ""

    def set_classification(self, result):
        self.classification = dict(result)
        self.classification_status = result["status"]
        self.classification_detail = ""

    def classification_failed(self, detail):
        self.classification = None
        self.classification_status = "erro_processamento"
        self.classification_detail = str(detail)

    def as_csv_row(self):
        if self.area is None:
            raise ValueError("Finalize a delimitação da copa antes de exportar.")
        if self.classification_status == "em_processamento":
            raise ValueError("Aguarde a conclusão da classificação antes de exportar.")
        result = self.classification or {}
        row = dict.fromkeys(TREE_CSV_FIELDS)
        for name in ("predicted_class", "final_class", "confidence", "threshold", *PROBABILITY_FIELDS):
            row[name] = result.get(name)
        row.update(
            especie=result.get("final_class"), status=self.classification_status,
            altura=self.height, diametro_copa=self.diameter, area_copa=self.area,
            coord_tree=repr((self.x, self.y)), crown_coords=json.dumps(self.coordinates),
            x_arvore=self.x, y_arvore=self.y, crs_trabalho=self.crs_work,
            crs_mds=self.crs_mds, crs_mdt=self.crs_mdt, crs_rgb=self.crs_rgb,
            mds_no_ponto=self.mds, mdt_no_ponto=self.mdt, status_altura=self.height_status,
            metodo_altura="mds_menos_mdt_no_ponto_selecionado",
            metodo_diametro="maior_distancia_entre_vertices",
            metodo_area="area_plana_poligono_src_trabalho",
            metodo_classificacao=("recorte_rgb_nativo_256px_reduzido_128px"
                                  if self.patch_path else "nao_executada"),
            patch_path=self.patch_path, detalhe_classificacao=self.classification_detail,
        )
        return row


def write_tree_csv(path, record):
    # Validate before opening/truncating an existing file.
    row = record.as_csv_row()
    with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=TREE_CSV_FIELDS)
        writer.writeheader()
        writer.writerow(row)
