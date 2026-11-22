"""Public inventory schema and package boundaries, independent of trained models."""
import ast
import csv
import tempfile
import unittest
from defusedxml import ElementTree as ET
from pathlib import Path
from test_tree import tree, crown
from test_csv_exports import exports, measured_tree

ROOT = Path(__file__).resolve().parents[1]

class PublicInventoryTests(unittest.TestCase):
    def test_no_trained_model_or_executable_classification_module(self):
        self.assertFalse((ROOT / 'fazenda_model.py').exists())
        forbidden = {'torch', 'torchvision', 'PIL', 'tensorflow', 'onnxruntime'}
        for path in ROOT.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint(a.name.split('.')[0] for a in node.names), path.name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden, path.name)
                elif isinstance(node, ast.FunctionDef):
                    self.assertNotIn(node.name, {'classify_image', 'load_fazenda_model', '_ensure_model',
                        'auto_convert_and_classify', '_classify_species_grids'}, path.name)
        self.assertFalse([p for p in ROOT.rglob('*') if p.suffix.lower() in {'.pth','.pt','.onnx','.h5','.ckpt'}])

    def test_ui_has_only_inventory_workflows(self):
        ui = ET.parse(ROOT / 'main_interface.ui', forbid_dtd=True,
                      forbid_entities=True, forbid_external=True)
        names = {w.attrib.get('name') for w in ui.iter('widget')}
        self.assertTrue({'generateM37Button', 'moveM37Button', 'rotateM37Button',
            'fixM37Button', 'selectAreaButton', 'finishDelimitationButton', 'exportButton'}.issubset(names))
        self.assertTrue(names.isdisjoint({'speciesPage', 'classifyAllSpeciesButton',
            'classifySpeciesCongButton', 'exportSpeciesCsvButton', 'resultLabel'}))
        table = next(w for w in ui.iter('widget') if w.get('name') == 'treeListTable')
        self.assertEqual(len(table.findall('column')), 4)

    def test_full_tree_report_needs_only_measurements_and_preserves_no_data(self):
        records = [measured_tree(), measured_tree()]
        records[1].arvore_id = '0008'
        records[1].set_height(None, None)
        fields = ('arvore_id', 'UA', *tree.TREE_CSV_FIELDS)
        rows = [dict(r.as_csv_row(), arvore_id=r.arvore_id, UA=r.ua) for r in records]
        self.assertTrue(set(fields).isdisjoint({'especie','predicted_class','final_class','confidence','threshold'}))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'inventory.csv'
            exports.write_csv(path, fields, rows, delimiter=',', decimal_comma=False)
            with path.open(encoding='utf-8-sig', newline='') as stream:
                actual = list(csv.DictReader(stream))
        self.assertEqual([r['arvore_id'] for r in actual], ['0007','0008'])
        self.assertEqual(actual[1]['altura'], '')
        self.assertEqual(actual[0]['area_copa'], '48.0')
        self.assertEqual(actual[0]['diametro_copa'], '10.0')
        self.assertEqual(actual[0]['crs_trabalho'], 'EPSG:31982')

    def test_serializer_retains_bom_decimal_and_full_precision(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'height.csv'
            exports.write_csv(path, ['UA','altura_m'], [{'UA':'001','altura_m':21.123456789012345}])
            self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                row = next(csv.DictReader(stream, delimiter=';'))
            self.assertEqual(row['UA'],'001')
            self.assertEqual(float(row['altura_m'].replace(',','.')),21.123456789012345)

    def test_incomplete_crown_does_not_truncate_existing_report(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'old.csv'; path.write_text('previous bytes')
            with self.assertRaises(ValueError): tree.write_tree_csv(path, tree.TreeMeasurement(0,0,'EPSG:31982'))
            self.assertEqual(path.read_text(),'previous bytes')
