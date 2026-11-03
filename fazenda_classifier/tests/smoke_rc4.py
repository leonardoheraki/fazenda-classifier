"""Run in the QGIS console. Uses an isolated project and no trained model."""
import unittest

from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY

from .smoke_qgis import run as run_spatial
from ..outputs import (
    SPECIES_ROLE, create_species_layer, find_owned_output,
    prepare_species_replacement, publish_species_replacement,
)
from ..runtime import require_supported_torch, RuntimeCompatibilityError


def _feature(layer, ua_id, number):
    feature = QgsFeature(layer.fields())
    feature.setAttributes([ua_id if field.name() == "UA" else
                           number if field.name() == "amostra_id" else None
                           for field in layer.fields()])
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000 + number, 7200000)))
    return feature


def run():
    checks = run_spatial()
    case = unittest.TestCase()
    project = QgsProject()  # Never add/remove layers in QgsProject.instance().
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:31982"))
    previous = create_species_layer(project.crs())
    success, _ = previous.dataProvider().addFeatures([
        _feature(previous, "CG_001", 1), _feature(previous, "CG_002", 2)])
    case.assertTrue(success)
    project.addMapLayer(previous)

    staged = create_species_layer(project.crs())
    replaced = prepare_species_replacement(previous, staged, "CG_001", [
        _feature(staged, "CG_001", 3), _feature(staged, "CG_001", 4)])
    case.assertEqual(previous.featureCount(), 2)
    case.assertEqual(replaced, 1)
    case.assertEqual(staged.featureCount(), 3)
    old_id = previous.id()
    publish_species_replacement(project, previous, staged)
    case.assertIsNone(project.mapLayer(old_id))
    case.assertEqual(find_owned_output(project, SPECIES_ROLE).id(), staged.id())
    checks.append("RC4: complete replacement preserves other UA in an isolated QGIS project")

    staged.startEditing()
    pending = create_species_layer(project.crs())
    with case.assertRaises(ValueError):
        prepare_species_replacement(staged, pending, "CG_001", [_feature(pending, "CG_001", 5)])
    case.assertEqual(staged.featureCount(), 3)
    staged.rollBack()
    checks.append("RC4: an active edit session blocks replacement without changing samples")

    foreign = create_species_layer(project.crs())
    foreign.removeCustomProperty("FazendaClassifier/rc4_output_role")
    project.addMapLayer(foreign)
    case.assertEqual(find_owned_output(project, SPECIES_ROLE).id(), staged.id())
    checks.append("RC4: an unmarked layer with the same name is not adopted")

    with case.assertRaises(RuntimeCompatibilityError):
        require_supported_torch("2.5.0+cpu")
    checks.append("RC4: affected PyTorch version is explicitly blocked")
    for message in checks[8:]:
        print("OK:", message)
    print(f"Integração RC4: {len(checks)} verificações concluídas; CNN real não executada.")
    project.clear()
    return checks
