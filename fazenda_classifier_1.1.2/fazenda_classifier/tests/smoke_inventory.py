"""Native QGIS acceptance checks using synthetic rasters, with ML imports blocked.
Run: QT_QPA_PLATFORM=offscreen /usr/bin/python3 tests/smoke_inventory.py
"""
import csv
import importlib
import importlib.abc
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

class BlockMachineLearning(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','torchvision','PIL','tensorflow','onnxruntime'}:
            raise AssertionError('Forbidden dependency requested: '+fullname)

sys.meta_path.insert(0, BlockMachineLearning())
import numpy as np
from osgeo import gdal
from qgis.core import QgsApplication, QgsProject, QgsCoordinateReferenceSystem, QgsRasterLayer, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.gui import QgsMapCanvas
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
app=QgsApplication([],False)
app.initQgis()
plugin=importlib.import_module(ROOT.name)
from fazenda_classifier.outputs import mark_owned_output, find_owned_output

class NativeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.folder=Path(self.tmp.name)
        self.project=QgsProject.instance(); self.project.clear()
        self.crs=QgsCoordinateReferenceSystem('EPSG:31982'); self.project.setCrs(self.crs)
        self.parent=QMainWindow(); self.canvas=QgsMapCanvas(self.parent); self.canvas.setDestinationCrs(self.crs)
        self.iface=types.SimpleNamespace(mainWindow=lambda:self.parent,mapCanvas=lambda:self.canvas)
        self.messages=[]
        self.patchers=[patch.object(plugin.QMessageBox,'warning',side_effect=lambda *a:self.messages.append(a[-1])),
            patch.object(plugin.QMessageBox,'information',return_value=None),
            patch.object(plugin.QMessageBox,'question',return_value=plugin.QMessageBox.StandardButton.Yes)]
        for p in self.patchers:p.start()
        self.mds=self.raster('MDS',120);self.mdt=self.raster('MDT',100);self.rgb=self.raster('RGB',50,bands=3)
        self.window=plugin.MainWindow(str(ROOT),self.iface)
        self.window.get_temp_folder=lambda:str(self.folder)
        for combo,layer in ((self.window.mdsComboBox,self.mds),(self.window.mdtComboBox,self.mdt),(self.window.orthoComboBox,self.rgb)):
            combo.setCurrentIndex(combo.findData(layer.id()))

    def tearDown(self):
        self.window._tree_batch.clear();self.window._tree_record=None;self.window.capture_points=[]
        self.window.close();self.window.deleteLater();self.parent.close();self.canvas.deleteLater()
        app.processEvents();self.project.clear()
        for p in reversed(self.patchers):p.stop()
        self.tmp.cleanup()

    def raster(self,name,value,bands=1):
        path=self.folder/(name+'.tif')
        ds=gdal.GetDriverByName('GTiff').Create(str(path),400,400,bands,gdal.GDT_Float32 if bands==1 else gdal.GDT_Byte)
        ds.SetGeoTransform((542000,.5,0,7192200,0,-.5));ds.SetProjection(self.crs.toWkt())
        for band in range(1,bands+1):
            ds.GetRasterBand(band).WriteArray(np.full((400,400),value+band-1))
        ds=None
        layer=QgsRasterLayer(str(path),name,'gdal');self.assertTrue(layer.isValid());self.project.addMapLayer(layer)
        return layer

    def test_real_ui_tree_measurement_native_tiff_finalize_export_without_ml(self):
        w=self.window
        self.assertEqual(w.workflowTabs.count(),2)
        self.assertEqual(w.treeListTable.columnCount(),4)
        self.assertFalse(hasattr(w,'classifyAllSpeciesButton'))
        w.select_area(QgsPointXY(542100,7192100))
        self.assertEqual(w._tree_record.height,20)
        w.treeIdLineEdit.setText('0001');w.treeUaLineEdit.setText('001')
        w.start_polygon_capture()
        for x,y in [(542096,7192097),(542104,7192097),(542104,7192103),(542096,7192103)]:
            w.add_point_to_polygon(QgsPointXY(x,y))
        w.finish_polygon_capture()
        self.assertEqual(w._tree_record.area,48)
        self.assertEqual(w._tree_record.diameter,10)
        output=Path(w._tree_record.crown_tiff_path);self.assertTrue(output.is_file(),self.messages)
        native=gdal.Open(str(output));self.assertEqual(native.GetGeoTransform()[1],.5);native=None
        w.select_area(QgsPointXY(542120,7192120))
        self.assertEqual(w._tree_record.x,542100) # cannot discard completed crown
        w.finalize_tree_list();self.assertEqual(len(w._tree_batch),1)
        self.assertEqual(w.treeListTable.item(0,0).text(),'0001')
        path=self.folder/'tree.csv'
        with patch.object(plugin.QFileDialog,'getSaveFileName',return_value=(str(path),'Relatório completo das árvores (*.csv)')):
            w.export_to_csv()
        self.assertTrue(path.is_file(),self.messages)
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        self.assertEqual(rows[0]['arvore_id'],'0001');self.assertEqual(float(rows[0]['altura']),20)
        self.assertEqual(float(rows[0]['area_copa']),48);self.assertNotIn('confidence',rows[0])
        self.assertFalse(self.messages,self.messages)

    def test_rotated_parcel_100_windows_colocated_heights_csv(self):
        w=self.window
        w.create_m37_conglomerate(QgsPointXY(542100,7192100),self.mds,self.mdt,azimuth=30)
        parcels=w.get_vector_layer_by_name('conglomerados_M37');subs=w.get_vector_layer_by_name('subparcelas_1x10_M37');points=w.get_vector_layer_by_name('pontos_altura_M37')
        self.assertEqual(parcels.featureCount(),1);self.assertEqual(subs.featureCount(),100);self.assertEqual(points.featureCount(),100)
        self.assertAlmostEqual(next(parcels.getFeatures()).geometry().area(),10000,places=5)
        for p in points.getFeatures():self.assertEqual(p['status'],'valido');self.assertEqual(p['altura_m'],20)
        path=self.folder/'parcels.csv'
        with patch.object(plugin.QFileDialog,'getSaveFileName',return_value=(str(path),'Fazenda ECO — Parcelas (*.csv)')):
            w.export_m37_points_to_csv()
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f,delimiter=';'))
        self.assertEqual(len(rows),100);self.assertEqual(rows[0]['unidade_registro'],'ponto_amostral_raster')
        self.assertFalse(self.messages,self.messages)

    def test_placement_move_rotate_fix_and_cancel(self):
        w=self.window
        w.activate_m37_tool()
        w.handle_m37_click(QgsPointXY(542095,7192095),plugin.Qt.MouseButton.LeftButton)
        w._set_m37_mode('move');w.handle_m37_move(QgsPointXY(542100,7192100))
        self.assertEqual(w._m37_center.x(),542100)
        w._set_m37_mode('rotate');w.handle_m37_move(QgsPointXY(542110,7192110))
        self.assertAlmostEqual(w.m37AzimuthSpin.value(),45)
        self.assertIsNone(w.get_vector_layer_by_name('conglomerados_M37'))
        w.confirm_m37_placement()
        parcels=w.get_vector_layer_by_name('conglomerados_M37')
        self.assertEqual(parcels.featureCount(),1)
        self.assertEqual(next(parcels.getFeatures())['azimute_graus'],45)
        w.activate_m37_tool();w.handle_m37_click(QgsPointXY(542100,7192100),plugin.Qt.MouseButton.LeftButton)
        w.cancel_m37_placement()
        self.assertEqual(parcels.featureCount(),1)
        self.assertFalse(self.messages,self.messages)

    def test_no_rgb_or_height_keeps_crown_and_allows_report(self):
        w=self.window
        for combo in (w.orthoComboBox,w.mdsComboBox,w.mdtComboBox):combo.setCurrentIndex(-1)
        w.select_area(QgsPointXY(542100,7192100))
        self.assertIsNone(w._tree_record.height)
        w.start_polygon_capture()
        for x,y in [(542096,7192097),(542104,7192097),(542104,7192103),(542096,7192103)]:
            w.add_point_to_polygon(QgsPointXY(x,y))
        w.finish_polygon_capture()
        self.assertEqual(w._tree_record.area,48)
        self.assertEqual(w._tree_record.crown_tiff_path,'')
        self.assertEqual(len(self.messages),1)
        w.finalize_tree_list()
        self.assertTrue(w.exportButton.isEnabled())
        self.assertIsNone(w._tree_batch.records[0].as_csv_row()['altura'])

    def test_output_ownership_does_not_adopt_unmarked_layers(self):
        layer=QgsVectorLayer('Point?crs=EPSG:31982','pontos_altura_M37','memory');self.project.addMapLayer(layer)
        self.assertIsNone(find_owned_output(self.project,'pontos_altura_M37'))
        mark_owned_output(layer,'pontos_altura_M37')
        self.assertEqual(find_owned_output(self.project,'pontos_altura_M37'),layer)
        second=QgsVectorLayer('Point?crs=EPSG:31982','another','memory');self.project.addMapLayer(second);mark_owned_output(second,'pontos_altura_M37')
        with self.assertRaisesRegex(ValueError,'mais de uma'):find_owned_output(self.project,'pontos_altura_M37')

if __name__=='__main__':unittest.main()
