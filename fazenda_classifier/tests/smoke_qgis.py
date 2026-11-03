"""Run inside the QGIS Python console; makes temporary synthetic rasters only."""
import tempfile
from pathlib import Path


def run():
    import numpy as np
    from osgeo import gdal, osr
    from qgis.core import (QgsCoordinateReferenceSystem, QgsProject, QgsPointXY,
                           QgsCoordinateTransform, QgsRectangle, QgsRasterLayer, QgsGeometry)
    from ..spatial import RasterSampler, maximum_height_window, SpatialError, require_metric_crs
    from ..tree import TreeMeasurement
    work = QgsCoordinateReferenceSystem('EPSG:31982')
    project = QgsProject.instance()
    center = QgsPointXY(543000, 7192000)
    checks = []
    with tempfile.TemporaryDirectory(prefix='fazenda_qgis_test_') as directory:
        def raster(name, crs, data, native_box=None):
            path = Path(directory)/(name+'.tif')
            box = native_box or QgsCoordinateTransform(work, crs,
                project.transformContext()).transformBoundingBox(
                    QgsRectangle(center.x()-1, center.y()-10, center.x()+1, center.y()+10))
            dataset = gdal.GetDriverByName('GTiff').Create(str(path), data.shape[1], data.shape[0], 1, gdal.GDT_Float32)
            dataset.SetGeoTransform([box.xMinimum(), box.width()/data.shape[1], 0,
                                     box.yMaximum(), 0, -box.height()/data.shape[0]])
            srs = osr.SpatialReference()
            srs.ImportFromWkt(crs.toWkt())
            dataset.SetProjection(srs.ExportToWkt())
            band = dataset.GetRasterBand(1)
            band.SetNoDataValue(-9999)
            band.WriteArray(data)
            dataset.FlushCache()
            dataset = None
            layer = QgsRasterLayer(str(path), name)
            assert layer.isValid(), name
            return layer
        data = np.array([[120+r+c/10 for c in range(4)] for r in range(40)], dtype='float32')
        dsm = RasterSampler(raster('dsm_metric', work, data), work, project)
        dtm = RasterSampler(raster('dtm_metric', work, np.full((40, 4), 100, dtype='float32')), work, project)
        result = maximum_height_window(dsm, dtm, center)
        assert result['n_pixels_janela'] == 40, result
        assert abs(result['altura_m']-49.2) < 1e-3, result
        checks.append('same CRS: true pixel maximum and 49.2 m height')
        geographic = QgsCoordinateReferenceSystem('EPSG:4326')
        dtm_geo = RasterSampler(raster('dtm_geographic', geographic, np.full((40, 4), 100, dtype='float32')), work, project)
        result = maximum_height_window(dsm, dtm_geo, center)
        assert abs(result['altura_m']-49.2) < 1e-3, result
        checks.append('different CRS: projected DSM and geographic DTM at same location')
        other_utm = QgsCoordinateReferenceSystem('EPSG:32722')
        dsm_utm = RasterSampler(raster('dsm_other_utm', other_utm, np.full((40, 4), 120, dtype='float32')), work, project)
        result = maximum_height_window(dsm_utm, dtm_geo, center)
        assert result['status'] == 'valido' and abs(result['altura_m']-20) < 1e-3, result
        checks.append('three CRS: project 31982, DSM 32722, DTM 4326')
        bad = RasterSampler(raster('dtm_nodata', work, np.full((40, 4), -9999, dtype='float32')), work, project)
        result = maximum_height_window(dsm, bad, center)
        assert result['altura_m'] is None and result['status'] != 'valido', result
        checks.append('NoData cannot become a valid height')
        try:
            require_metric_crs(geographic)
        except SpatialError:
            checks.append('geographic working CRS rejected')
        else:
            raise AssertionError('Expected rejection of a geographic working CRS')
        # Release raster providers before deleting temporary files on Windows.
        dsm = dtm = dtm_geo = dsm_utm = bad = None
    ring = [QgsPointXY(542370, 7192080), QgsPointXY(542378, 7192080),
            QgsPointXY(542378, 7192086), QgsPointXY(542370, 7192086)]
    geometry = QgsGeometry.fromPolygonXY([ring+[ring[0]]])
    assert geometry.isGeosValid() and abs(geometry.area()-48) < 1e-8
    record = TreeMeasurement(542374, 7192083, 'EPSG:31982')
    record.set_crown([(p.x(), p.y()) for p in ring])
    assert record.area == 48 and record.diameter == 10
    assert geometry.intersects(QgsGeometry.fromPointXY(QgsPointXY(record.x, record.y)))
    checks.append('individual crown: valid 48 m2 polygon, 10 m maximum span and point inside')
    crossed = [ring[0], ring[2], ring[1], ring[3], ring[0]]
    assert not QgsGeometry.fromPolygonXY([crossed]).isGeosValid()
    checks.append('self-intersecting crown rejected by GEOS')
    row = record.as_csv_row()
    assert row['status'] == 'nao_executada' and row['final_class'] is None
    assert row['crs_trabalho'] == 'EPSG:31982' and row['area_copa'] == 48
    checks.append('missing tree inference is explicit and CSV retains area and CRS')
    for item in checks:
        print('OK:', item)
    print('Integração QGIS:', len(checks), 'verificações concluídas.')
    return checks
