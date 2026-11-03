"""Exercise actual output functions with failure-injecting memory API adapters."""
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_tree_flow import window_class


class Field:
    def __init__(self, name, field_type=None): self.value = name
    def name(self): return self.value


class Fields(list):
    def indexFromName(self, name):
        return next((i for i, field in enumerate(self) if field.name() == name), -1)


class Feature:
    def __init__(self, fields): self.fields, self.values, self.shape = fields, {}, None
    def __getitem__(self, name): return self.values[name]
    def setAttributes(self, attributes):
        self.values = dict(zip((field.name() for field in self.fields), attributes))
    def setGeometry(self, geometry): self.shape = geometry
    def geometry(self): return self.shape


class MemoryLayer:
    sequence = 0

    def __init__(self, uri, name, provider):
        MemoryLayer.sequence += 1
        self.layer_id = str(MemoryLayer.sequence)
        self.label, self.provider_name = name, provider
        self.props, self.columns, self.features = {}, Fields(), []
        self.coordinate_system = None
        self.editable, self.accept_add, self.partial_add = False, True, False
    def isValid(self): return True
    def providerType(self): return self.provider_name
    def customProperty(self, key, default=""): return self.props.get(key, default)
    def setCustomProperty(self, key, value): self.props[key] = value
    def dataProvider(self): return self
    def addAttributes(self, fields): self.columns.extend(fields); return True
    def updateFields(self): pass
    def fields(self): return self.columns
    def setCrs(self, crs): self.coordinate_system = crs
    def crs(self): return self.coordinate_system
    def isEditable(self): return self.editable
    def featureCount(self): return len(self.features)
    def getFeatures(self): return iter(self.features)
    def addFeatures(self, features):
        selected = features[:1] if self.partial_add or not self.accept_add else features
        self.features.extend(selected)
        return self.accept_add, selected
    def updateExtents(self): pass
    def name(self): return self.label
    def setName(self, value): self.label = value
    def renderer(self): return None
    def id(self): return self.layer_id


class Project:
    def __init__(self):
        self.layers = {}
        self.reject_add, self.reject_take, self.fail_after_take = False, False, False
    def mapLayers(self): return dict(self.layers)
    def mapLayer(self, layer_id): return self.layers.get(layer_id)
    def addMapLayer(self, layer):
        if self.reject_add: return None
        self.layers[layer.id()] = layer
        return layer
    def takeMapLayer(self, layer):
        if self.reject_take: return None
        taken = self.layers.pop(layer.id())
        if self.fail_after_take: raise RuntimeError("Injected project failure")
        return taken
    def removeMapLayer(self, layer_id): del self.layers[layer_id]


class OutputSafetyTests(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        window = window_class(self.project)
        self.window_type = window
        self.api = window.get_vector_layer_by_name.__globals__
        self.functions = self.api["create_species_layer"].__globals__
        replacement = dict(QgsVectorLayer=MemoryLayer, QgsField=Field, QgsFeature=Feature,
                           QVariant=types.SimpleNamespace(String=str, Int=int, Double=float))
        adapter = patch.dict(self.functions, replacement)
        adapter.start()
        self.addCleanup(adapter.stop)
        self.crs = types.SimpleNamespace(authid=lambda: "EPSG:31982")
        self.project.crs = lambda: self.crs
        self.previous = self.create()
        self.previous.features = [self.feature(self.previous, "CG_001", 1),
                                  self.feature(self.previous, "CG_002", 2)]
        self.project.addMapLayer(self.previous)

    def create(self): return self.api["create_species_layer"](self.crs)

    def feature(self, layer, ua, number):
        result = Feature(layer.fields())
        result.setAttributes([ua if field.name() == "UA" else number for field in layer.fields()])
        result.setGeometry((number, number))
        return result

    def prepare(self, staged=None, ua="CG_001", count=2):
        if staged is None: staged = self.create()
        rows = [self.feature(staged, ua, number) for number in range(count)]
        replaced = self.api["prepare_species_replacement"](self.previous, staged, ua, rows)
        return staged, replaced

    def test_same_named_persistent_or_unmarked_layers_are_never_adopted(self):
        foreign = self.create()
        foreign.provider_name = "ogr"
        unmarked = self.create()
        unmarked.props.clear()
        self.project.layers = {foreign.id(): foreign, unmarked.id(): unmarked}
        self.assertIsNone(self.api["find_owned_output"](self.project, "pontos_especies_M37"))

    def test_ambiguous_owned_layers_stop_instead_of_picking_one(self):
        self.project.addMapLayer(self.create())
        with self.assertRaisesRegex(ValueError, "mais de uma"):
            self.api["find_owned_output"](self.project, "pontos_especies_M37")

    def test_replacement_preserves_other_ua_and_previous_until_success(self):
        staged, replaced = self.prepare()
        self.assertEqual(replaced, 1)
        self.assertEqual(self.previous.featureCount(), 2)
        self.assertEqual(staged.featureCount(), 3)
        self.assertEqual(list(self.project.layers), [self.previous.id()])
        self.api["publish_species_replacement"](self.project, self.previous, staged)
        self.assertEqual(list(self.project.layers), [staged.id()])
        self.assertEqual([row["UA"] for row in staged.getFeatures()], ["CG_002", "CG_001", "CG_001"])

    def test_repeated_reclassification_does_not_accumulate_samples(self):
        staged, _ = self.prepare()
        self.api["publish_species_replacement"](self.project, self.previous, staged)
        self.previous = staged
        again, replaced = self.prepare(count=1)
        self.api["publish_species_replacement"](self.project, self.previous, again)
        self.assertEqual(replaced, 2)
        self.assertEqual(again.featureCount(), 2)

    def test_partial_failed_provider_write_cannot_change_previous_layer(self):
        staged = self.create()
        staged.accept_add = False
        with self.assertRaisesRegex(ValueError, "anterior foi preservada"):
            self.prepare(staged)
        self.assertEqual(self.previous.featureCount(), 2)
        self.assertEqual(list(self.project.layers), [self.previous.id()])

    def test_short_write_is_rejected_even_if_provider_reports_success(self):
        staged = self.create()
        staged.partial_add = True
        with self.assertRaises(ValueError): self.prepare(staged)
        self.assertEqual(self.previous.featureCount(), 2)

    def test_missing_ua_field_preserves_previous_samples(self):
        self.previous.columns.pop(0)
        with self.assertRaisesRegex(ValueError, "campo obrigatório UA"):
            self.prepare()
        self.assertEqual(self.previous.featureCount(), 2)

    def test_empty_run_cannot_erase_a_previous_classification(self):
        with self.assertRaisesRegex(ValueError, "vazia"):
            self.prepare(count=0)
        self.assertEqual(self.previous.featureCount(), 2)

    def test_new_rows_must_belong_to_the_selected_ua(self):
        staged = self.create()
        rows = [self.feature(staged, "CG_999", 1)]
        with self.assertRaisesRegex(ValueError, "outra UA"):
            self.api["prepare_species_replacement"](self.previous, staged, "CG_001", rows)
        self.assertEqual(self.previous.featureCount(), 2)

    def test_a_persistent_layer_is_rejected_even_with_a_copied_marker(self):
        self.previous.provider_name = "ogr"
        with self.assertRaisesRegex(ValueError, "saída de memória"):
            self.prepare()
        self.assertEqual(self.previous.featureCount(), 2)

    def test_user_edit_session_is_preserved(self):
        self.previous.editable = True
        with self.assertRaisesRegex(ValueError, "edição"):
            self.prepare()
        self.assertEqual(self.previous.featureCount(), 2)

    def test_different_crs_cannot_replace_previous_samples(self):
        self.previous.coordinate_system = object()
        with self.assertRaisesRegex(ValueError, "outro SRC"):
            self.prepare()
        self.assertEqual(self.previous.featureCount(), 2)

    def test_failed_layer_registration_preserves_previous_layer(self):
        staged, _ = self.prepare()
        self.project.reject_add = True
        with self.assertRaises(ValueError):
            self.api["publish_species_replacement"](self.project, self.previous, staged)
        self.assertEqual(list(self.project.layers), [self.previous.id()])

    def test_failed_detach_removes_only_the_new_layer(self):
        staged, _ = self.prepare()
        self.project.reject_take = True
        with self.assertRaises(ValueError):
            self.api["publish_species_replacement"](self.project, self.previous, staged)
        self.assertEqual(list(self.project.layers), [self.previous.id()])
        self.assertEqual(self.previous.featureCount(), 2)

    def test_failure_after_detach_restores_the_previous_layer(self):
        staged, _ = self.prepare()
        self.project.fail_after_take = True
        with self.assertRaisesRegex(RuntimeError, "Injected"):
            self.api["publish_species_replacement"](self.project, self.previous, staged)
        self.assertEqual(list(self.project.layers), [self.previous.id()])
        self.assertEqual(self.previous.featureCount(), 2)

    def classification_window(self, folder, *, fail_inference=False, fail_crop=False):
        window = self.window_type.__new__(self.window_type)
        window._ensure_model = lambda: True
        window.validate_ortho_layer = lambda: types.SimpleNamespace(crs=lambda: self.crs)
        window._check_existing_output_crs = lambda: None
        bounds = types.SimpleNamespace(xMinimum=lambda: 0, yMinimum=lambda: 0)
        geometry = types.SimpleNamespace(isEmpty=lambda: False, boundingBox=lambda: bounds,
                                         contains=lambda point: True)
        conglomerate = self.feature(self.previous, "CG_001", 1)
        conglomerate.setGeometry(geometry)
        window.get_last_conglomerate_feature = lambda: conglomerate
        window.speciesStatusLabel = types.SimpleNamespace(setText=lambda text: None)
        window.iface = types.SimpleNamespace(mapCanvas=lambda: types.SimpleNamespace(refresh=lambda: None))
        calls = []

        def crop(**kwargs):
            if fail_crop: raise OSError("Injected crop failure")
            Path(kwargs["output_path"]).touch()
            return kwargs["output_path"]

        def classify(path):
            calls.append(path)
            if fail_inference and len(calls) == 3: raise RuntimeError("Injected CNN failure")
            return dict(predicted_class="Cedrela fissilis", final_class="Cedrela fissilis",
                        confidence=0.8, threshold=0.6, status="aceita",
                        prob_Araucaria_angustifolia=0.1, prob_Cedrela_fissilis=0.8,
                        prob_Ocotea_porosa=0.1)

        window.save_species_patch = crop
        window.model = types.SimpleNamespace(classify_image=classify)
        adapter = patch.dict(self.api, {
            "QgsFeature": Feature,
            "QgsGeometry": types.SimpleNamespace(fromPointXY=lambda point: point),
            "create_species_workspace": lambda ua: folder,
            "QgsProject": types.SimpleNamespace(instance=lambda: self.project),
        })
        adapter.start()
        self.addCleanup(adapter.stop)
        return window, calls

    def test_actual_classification_flow_preserves_previous_after_cnn_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            window, calls = self.classification_window(folder, fail_inference=True)
            window.classify_species_in_last_conglomerate()
        self.assertEqual(len(calls), 3)
        self.assertEqual(list(self.project.layers), [self.previous.id()])
        self.assertEqual(self.previous.featureCount(), 2)

    def test_actual_classification_flow_preserves_previous_after_crop_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            window, calls = self.classification_window(folder, fail_crop=True)
            window.classify_species_in_last_conglomerate()
        self.assertEqual(calls, [])
        self.assertEqual(list(self.project.layers), [self.previous.id()])
        self.assertEqual(self.previous.featureCount(), 2)

    def test_actual_625_sample_flow_publishes_only_complete_results_without_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            window, calls = self.classification_window(folder)
            window.classify_species_in_last_conglomerate()
            window.classify_species_in_last_conglomerate()
        self.assertEqual(len(calls), 1250)
        self.assertEqual(len(self.project.layers), 1)
        result = next(iter(self.project.layers.values()))
        self.assertEqual(result.featureCount(), 626)
        self.assertEqual(sum(row["UA"] == "CG_001" for row in result.getFeatures()), 625)
        self.assertEqual(sum(row["UA"] == "CG_002" for row in result.getFeatures()), 1)


if __name__ == "__main__":
    unittest.main()
