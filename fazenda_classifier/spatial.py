"""Horizontal CRS conversion and native DSM pixel sampling (QGIS 3)."""
import math

from qgis.core import (
    QgsCoordinateTransform, QgsCsException, QgsPointXY, QgsRectangle, QgsUnitTypes,
)


class SpatialError(ValueError):
    """Processing must stop instead of treating a CRS error as valid height."""


def require_metric_crs(crs):
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits() != QgsUnitTypes.DistanceMeters:
        raise SpatialError(
            "Escolha um SRC projetado com unidades em metros para o projeto "
            "antes de gerar parcelas, janelas ou medidas de copa."
        )


def crs_label(crs):
    return crs.authid() or crs.toWkt()


def transform_point(point, source_crs, target_crs, project):
    if not source_crs.isValid() or not target_crs.isValid():
        raise SpatialError("SRC ausente ou inválido; confira os metadados das camadas.")
    try:
        p = QgsPointXY(point.x(), point.y())
        if source_crs != target_crs:
            p = QgsCoordinateTransform(source_crs, target_crs, project.transformContext()).transform(p)
        if not math.isfinite(p.x()) or not math.isfinite(p.y()):
            raise SpatialError("A transformação de coordenadas produziu valores inválidos.")
        return p
    except QgsCsException as error:
        raise SpatialError(f"Não foi possível transformar as coordenadas: {error}") from error


class RasterSampler:
    def __init__(self, layer, work_crs, project):
        if layer is None or not layer.isValid() or not layer.crs().isValid():
            raise SpatialError("Raster inválido ou sem SRC conhecido.")
        self.layer = layer
        self.provider = layer.dataProvider()
        self.work_crs = work_crs
        self.native_crs = layer.crs()
        self.forward = self.inverse = None
        if not work_crs.isValid():
            raise SpatialError("O projeto não possui SRC válido.")
        if work_crs != self.native_crs:
            context = project.transformContext()
            self.forward = QgsCoordinateTransform(work_crs, self.native_crs, context)
            self.inverse = QgsCoordinateTransform(self.native_crs, work_crs, context)

    def _convert(self, point, operation):
        try:
            p = operation.transform(point) if operation is not None else QgsPointXY(point)
            if not math.isfinite(p.x()) or not math.isfinite(p.y()):
                raise SpatialError("Coordenada inválida após a transformação.")
            return p
        except QgsCsException as error:
            raise SpatialError(f"Falha de transformação no raster {self.layer.name()}: {error}") from error

    def to_native(self, point):
        return self._convert(point, self.forward)

    def to_work(self, point):
        return self._convert(point, self.inverse)

    def sample_native(self, point):
        if not self.layer.extent().contains(point):
            return None
        value, ok = self.provider.sample(point, 1)
        if not ok or value is None:
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        if (self.provider.sourceHasNoDataValue(1) and self.provider.useSourceNoDataValue(1)
                and value == self.provider.sourceNoDataValue(1)):
            return None
        return value

    def sample(self, point):
        return self.sample_native(self.to_native(point))


def maximum_height_window(dsm, dtm, center, width=1.0, length=10.0, max_pixels=100000):
    """Select real DSM pixel centers inside the metric window, then sample DTM.

    The DSM maximum and its exported XY are in the working CRS. DTM is sampled
    at that same physical location, converted to the DTM's own horizontal CRS.
    Vertical coordinates must already use the same units and reference.
    """
    require_metric_crs(dsm.work_crs)
    if width <= 0 or length <= 0:
        raise SpatialError("As dimensões da janela devem ser positivas.")
    window = QgsRectangle(center.x()-width/2, center.y()-length/2,
                          center.x()+width/2, center.y()+length/2)
    try:
        bbox = dsm.forward.transformBoundingBox(window) if dsm.forward is not None else window
    except QgsCsException as error:
        raise SpatialError(f"Não foi possível transformar a janela do MDS: {error}") from error
    extent = dsm.layer.extent()
    nx, ny = dsm.layer.width(), dsm.layer.height()
    if nx <= 0 or ny <= 0:
        raise SpatialError("O MDS possui dimensões inválidas.")
    px, py = extent.width()/nx, extent.height()/ny
    if px <= 0 or py <= 0:
        raise SpatialError("O MDS possui resolução inválida.")
    c0 = max(0, math.floor((bbox.xMinimum()-extent.xMinimum())/px))
    c1 = min(nx-1, math.floor((bbox.xMaximum()-extent.xMinimum())/px))
    r0 = max(0, math.floor((extent.yMaximum()-bbox.yMaximum())/py))
    r1 = min(ny-1, math.floor((extent.yMaximum()-bbox.yMinimum())/py))
    if max(0, c1-c0+1)*max(0, r1-r0+1) > max_pixels:
        raise SpatialError("Janela com mais de 100.000 pixels; confira SRC e resolução do MDS.")
    max_value, max_point, count = None, None, 0
    for row in range(r0, r1+1):
        for col in range(c0, c1+1):
            native = QgsPointXY(extent.xMinimum()+(col+0.5)*px,
                                extent.yMaximum()-(row+0.5)*py)
            work = dsm.to_work(native)
            if not window.contains(work):
                continue
            value = dsm.sample_native(native)
            if value is None:
                continue
            count += 1
            if max_value is None or value > max_value:
                max_value, max_point = value, work
    result = dict(x_mds_max=None, y_mds_max=None, mds_max=max_value,
                  mdt_mdsmax=None, altura_m=None, n_pixels_janela=count,
                  status="sem_valor_mds_janela")
    if max_point is None:
        return result
    result.update(x_mds_max=max_point.x(), y_mds_max=max_point.y())
    terrain = dtm.sample(max_point)
    if terrain is None:
        result["status"] = "sem_valor_mdt_no_mdsmax"
        return result
    height = max_value-terrain
    result.update(mdt_mdsmax=terrain, altura_m=height,
                  status="valido" if height > 0 else "altura_invalida")
    return result
