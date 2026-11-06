"""Numerical unit tests with a minimal QGIS adapter; no desktop QGIS needed.

These tests check coordinate routing and pixel logic. They do not certify the
real PROJ/QGIS runtime; use smoke_qgis.py inside QGIS for that integration.
"""
import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path


class Point:
    def __init__(self, x, y=None):
        self._x, self._y = (x.x(), x.y()) if y is None else (x, y)
    def x(self): return self._x
    def y(self): return self._y


class Rectangle:
    def __init__(self, xmin, ymin, xmax, ymax):
        self.values = xmin, ymin, xmax, ymax
    def xMinimum(self): return self.values[0]
    def yMinimum(self): return self.values[1]
    def xMaximum(self): return self.values[2]
    def yMaximum(self): return self.values[3]
    def width(self): return self.xMaximum()-self.xMinimum()
    def height(self): return self.yMaximum()-self.yMinimum()
    def contains(self, p):
        return self.xMinimum() <= p.x() <= self.xMaximum() and self.yMinimum() <= p.y() <= self.yMaximum()


class CRS:
    def __init__(self, dx=0, dy=0, valid=True, geographic=False, units=0):
        self.dx, self.dy, self.valid, self.geographic, self.units = dx, dy, valid, geographic, units
    def isValid(self): return self.valid
    def isGeographic(self): return self.geographic
    def mapUnits(self): return self.units
    def authid(self): return f"TEST:{self.dx}:{self.dy}"
    def toWkt(self): return self.authid()
    def __eq__(self, other): return vars(self) == vars(other)


class CsException(Exception): pass


class Transform:
    fail = False
    def __init__(self, source, target, context):
        self.dx, self.dy = target.dx-source.dx, target.dy-source.dy
    def transform(self, point):
        if self.fail: raise CsException("synthetic conversion failure")
        return Point(point.x()+self.dx, point.y()+self.dy)
    def transformBoundingBox(self, box):
        a = self.transform(Point(box.xMinimum(), box.yMinimum()))
        b = self.transform(Point(box.xMaximum(), box.yMaximum()))
        return Rectangle(a.x(), a.y(), b.x(), b.y())


class Project:
    def transformContext(self): return None


class Layer:
    def __init__(self, crs=None, data=None):
        self._crs = crs or CRS()
        self.data = data if data is not None else [[120.0]*4 for _ in range(40)]
        self.reads = []
    def isValid(self): return True
    def crs(self): return self._crs
    def name(self): return "synthetic"
    def dataProvider(self): return self
    def width(self): return len(self.data[0])
    def height(self): return len(self.data)
    def extent(self): return Rectangle(-1+self._crs.dx, -10+self._crs.dy, 1+self._crs.dx, 10+self._crs.dy)
    def sample(self, p, band):
        self.reads.append(p)
        e = self.extent()
        c = math.floor((p.x()-e.xMinimum())/e.width()*self.width())
        r = math.floor((e.yMaximum()-p.y())/e.height()*self.height())
        return (self.data[r][c], True) if 0 <= r < self.height() and 0 <= c < self.width() else (float('nan'), False)
    def sourceHasNoDataValue(self, band): return True
    def useSourceNoDataValue(self, band): return True
    def sourceNoDataValue(self, band): return -9999


def load_spatial():
    core = types.ModuleType("qgis.core")
    for name, value in dict(QgsCoordinateTransform=Transform, QgsCsException=CsException,
        QgsPointXY=Point, QgsRectangle=Rectangle,
        QgsUnitTypes=types.SimpleNamespace(DistanceMeters=0)).items():
        setattr(core, name, value)
    old = {name: sys.modules.get(name) for name in ("qgis", "qgis.core")}
    sys.modules['qgis'] = types.ModuleType('qgis')
    sys.modules['qgis.core'] = core
    path = Path(__file__).parents[1]/'spatial.py'
    spec = importlib.util.spec_from_file_location('tested_spatial', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in old.items():
        if value is None: sys.modules.pop(name, None)
        else: sys.modules[name] = value
    return module


spatial = load_spatial()


class TestSpatial(unittest.TestCase):
    def setUp(self): Transform.fail = False
    def sampler(self, layer): return spatial.RasterSampler(layer, CRS(), Project())

    def test_each_raster_receives_its_own_coordinates(self):
        a, b = Layer(CRS(100, 200)), Layer(CRS(1000, 2000))
        self.assertEqual(self.sampler(a).sample(Point(0.25, 0.25)), 120)
        self.assertEqual(self.sampler(b).sample(Point(0.25, 0.25)), 120)
        self.assertEqual((a.reads[-1].x(), a.reads[-1].y()), (100.25, 200.25))
        self.assertEqual((b.reads[-1].x(), b.reads[-1].y()), (1000.25, 2000.25))

    def test_maximum_real_pixel_center_and_colocated_dtm(self):
        data = [[120+r+c/10 for c in range(4)] for r in range(40)]
        a = Layer(CRS(100, 200), data)
        b = Layer(CRS(1000, 2000), [[100.0]*4 for _ in range(40)])
        result = spatial.maximum_height_window(self.sampler(a), self.sampler(b), Point(0, 0))
        self.assertEqual(result['n_pixels_janela'], 40)
        self.assertAlmostEqual(result['mds_max'], 149.2)
        self.assertAlmostEqual(result['altura_m'], 49.2)
        self.assertAlmostEqual(result['x_mds_max'], 0.25)
        self.assertAlmostEqual(result['y_mds_max'], -4.75)
        self.assertAlmostEqual(b.reads[-1].x(), 1000.25)
        self.assertAlmostEqual(b.reads[-1].y(), 1995.25)

    def test_same_crs_constant_height(self):
        result = spatial.maximum_height_window(self.sampler(Layer()),
            self.sampler(Layer(data=[[100.0]*4 for _ in range(40)])), Point(0, 0))
        self.assertEqual(result['altura_m'], 20)
        self.assertEqual(result['status'], 'valido')

    def test_nodata_and_nonfinite_cannot_become_valid(self):
        for bad in (-9999, float('nan'), float('inf')):
            result = spatial.maximum_height_window(self.sampler(Layer(data=[[bad]*4 for _ in range(40)])),
                self.sampler(Layer()), Point(0, 0))
            self.assertIsNone(result['altura_m'])
            self.assertEqual(result['status'], 'sem_valor_mds_janela')

    def test_missing_dtm_retains_dsm_but_invalidates_height(self):
        result = spatial.maximum_height_window(self.sampler(Layer()),
            self.sampler(Layer(data=[[-9999]*4 for _ in range(40)])), Point(0, 0))
        self.assertEqual(result['mds_max'], 120)
        self.assertIsNone(result['altura_m'])
        self.assertEqual(result['status'], 'sem_valor_mdt_no_mdsmax')

    def test_negative_height_is_flagged(self):
        result = spatial.maximum_height_window(self.sampler(Layer()),
            self.sampler(Layer(data=[[130.0]*4 for _ in range(40)])), Point(0, 0))
        self.assertEqual(result['altura_m'], -10)
        self.assertEqual(result['status'], 'altura_invalida')

    def test_transform_failure_stops_processing(self):
        sampler = self.sampler(Layer(CRS(100, 200)))
        Transform.fail = True
        with self.assertRaises(spatial.SpatialError): sampler.sample(Point(0, 0))
        with self.assertRaises(spatial.SpatialError):
            spatial.maximum_height_window(sampler, self.sampler(Layer()), Point(0, 0))

    def test_metric_project_is_required(self):
        for crs in (CRS(valid=False), CRS(geographic=True), CRS(units=1)):
            with self.assertRaises(spatial.SpatialError): spatial.require_metric_crs(crs)

    def test_outside_raster_is_not_sampled(self):
        layer = Layer()
        self.assertIsNone(self.sampler(layer).sample(Point(500, 500)))
        self.assertEqual(layer.reads, [])

    def test_window_pixel_budget(self):
        with self.assertRaises(spatial.SpatialError):
            spatial.maximum_height_window(self.sampler(Layer()), self.sampler(Layer()),
                                            Point(0, 0), max_pixels=1)


if __name__ == '__main__': unittest.main(verbosity=2)
