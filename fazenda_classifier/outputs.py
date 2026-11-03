"""Own memory outputs and prepare species results before replacing a layer."""
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, QgsFeature

from .spatial import SpatialError
from .runtime import require_ua_id


OUTPUT_ROLE_KEY = "FazendaClassifier/rc4_output_role"
SPECIES_ROLE = "pontos_especies_M37"
SPECIES_FIELDS = (
    ("UA", "String"), ("amostra_id", "Int"), ("linha", "Int"), ("coluna", "Int"),
    ("x_utm", "Double"), ("y_utm", "Double"), ("grid_size_m", "Double"),
    ("patch_size_m", "Double"), ("pred_class", "String"), ("final_class", "String"),
    ("confidence", "Double"), ("threshold", "Double"), ("status", "String"),
    ("prob_AA", "Double"), ("prob_CF", "Double"), ("prob_OP", "Double"),
    ("patch_path", "String"), ("crs_trabalho", "String"), ("crs_rgb", "String"),
)


def is_owned_output(layer, role):
    return (isinstance(layer, QgsVectorLayer) and layer.isValid()
            and layer.providerType() == "memory"
            and layer.customProperty(OUTPUT_ROLE_KEY, "") == role)


def mark_owned_output(layer, role):
    if not layer.isValid() or layer.providerType() != "memory":
        raise SpatialError("A RC4 grava resultados apenas em camadas próprias de memória.")
    layer.setCustomProperty(OUTPUT_ROLE_KEY, role)


def find_owned_output(project, role):
    matches = [layer for layer in project.mapLayers().values() if is_owned_output(layer, role)]
    if len(matches) > 1:
        raise SpatialError(f"Há mais de uma saída RC4 para {role}. Confira as camadas antes de continuar.")
    return matches[0] if matches else None


def create_species_layer(crs):
    layer = QgsVectorLayer(f"Point?crs={crs.authid()}", SPECIES_ROLE, "memory")
    mark_owned_output(layer, SPECIES_ROLE)
    if not layer.dataProvider().addAttributes([
        QgsField(name, getattr(QVariant, field_type)) for name, field_type in SPECIES_FIELDS
    ]):
        raise SpatialError("Não foi possível criar os campos da nova classificação.")
    layer.updateFields()
    layer.setCrs(crs)
    return layer


def validate_previous_species(previous, crs):
    if previous is None:
        return
    if not is_owned_output(previous, SPECIES_ROLE):
        raise SpatialError("A camada anterior não é uma saída de memória da RC4.")
    if previous.isEditable():
        raise SpatialError("Finalize ou descarte a edição da camada de espécies antes de reclassificar.")
    if previous.crs() != crs:
        raise SpatialError("A classificação anterior usa outro SRC; os dados foram preservados.")
    for name, _ in SPECIES_FIELDS:
        if previous.fields().indexFromName(name) < 0:
            raise SpatialError(f"A camada de espécies não possui o campo obrigatório {name}.")


def prepare_species_replacement(previous, staged, ua_id, new_features):
    """Fill an unpublished layer; never delete or update previous features."""
    require_ua_id(ua_id)
    validate_previous_species(previous, staged.crs())
    if not is_owned_output(staged, SPECIES_ROLE) or staged.featureCount() != 0:
        raise SpatialError("A nova classificação precisa de uma camada de memória vazia da RC4.")
    if not new_features or any(feature["UA"] != ua_id for feature in new_features):
        raise SpatialError("A nova classificação está vazia ou contém amostras de outra UA.")

    records = []
    replaced = 0
    if previous is not None:
        for feature in previous.getFeatures():
            if feature["UA"] == ua_id:
                replaced += 1
            else:
                records.append(feature)
    records.extend(new_features)
    copies = []
    for feature in records:
        copy = QgsFeature(staged.fields())
        copy.setGeometry(feature.geometry())
        copy.setAttributes([feature[name] for name, _ in SPECIES_FIELDS])
        copies.append(copy)
    success, _ = staged.dataProvider().addFeatures(copies)
    if not success or staged.featureCount() != len(copies):
        raise SpatialError("A gravação das novas amostras falhou. A classificação anterior foi preservada.")
    staged.updateExtents()
    if previous is not None:
        staged.setName(previous.name())
        renderer = previous.renderer()
        if renderer is not None:
            staged.setRenderer(renderer.clone())
    return replaced


def publish_species_replacement(project, previous, staged):
    """Register the complete new layer before detaching the old memory layer."""
    validate_previous_species(previous, staged.crs())
    if not is_owned_output(staged, SPECIES_ROLE) or staged.featureCount() == 0:
        raise SpatialError("A classificação preparada não possui amostras válidas.")
    old_id = previous.id() if previous is not None else None
    if old_id is not None and project.mapLayer(old_id) is None:
        raise SpatialError("A camada anterior foi removida durante o processamento. Nenhum resultado foi substituído.")
    try:
        if project.addMapLayer(staged) is None or project.mapLayer(staged.id()) is None:
            raise SpatialError("Não foi possível adicionar a nova classificação ao projeto.")
        # takeMapLayer transfers ownership without destroying the old object, so
        # it can be put back if the project operation fails. Providers are never
        # asked to delete existing samples or write a persistent dataset.
        if previous is not None and project.takeMapLayer(previous) is None:
            raise SpatialError("Não foi possível substituir a camada anterior.")
    except Exception:
        if old_id is not None and project.mapLayer(old_id) is None:
            project.addMapLayer(previous)
        if project.mapLayer(staged.id()) is not None:
            project.removeMapLayer(staged.id())
        raise
