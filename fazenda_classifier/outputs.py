"""Identify the plugin's own in-memory inventory output layers."""
from qgis.core import QgsVectorLayer
from .spatial import SpatialError

# Preserve the existing property key so prior inventory layers remain identifiable.
OUTPUT_ROLE_KEY = "FazendaClassifier/rc4_output_role"


def is_owned_output(layer, role):
    return (isinstance(layer, QgsVectorLayer) and layer.isValid()
            and layer.providerType() == "memory"
            and layer.customProperty(OUTPUT_ROLE_KEY, "") == role)


def mark_owned_output(layer, role):
    if not layer.isValid() or layer.providerType() != "memory":
        raise SpatialError("O plugin grava resultados apenas em camadas próprias de memória.")
    layer.setCustomProperty(OUTPUT_ROLE_KEY, role)


def find_owned_output(project, role):
    matches = [layer for layer in project.mapLayers().values() if is_owned_output(layer, role)]
    if len(matches) > 1:
        raise SpatialError(f"Há mais de uma saída do plugin para {role}. Confira as camadas antes de continuar.")
    return matches[0] if matches else None

