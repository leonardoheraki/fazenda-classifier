"""Optional real inference check. Select your own weights and small RGB patches."""
import math
from pathlib import Path
import unittest

from ..runtime import require_supported_torch, RuntimeCompatibilityError


def run(model_path=None, image_paths=None):
    import torch
    print("PyTorch:", torch.__version__)
    try:
        require_supported_torch(torch.__version__)
    except RuntimeCompatibilityError as error:
        print(str(error))
        return {"status": "bloqueada", "torch": str(torch.__version__)}

    import torchvision
    from ..fazenda_model import FazendaModel
    print("torchvision:", torchvision.__version__)
    if model_path is None or image_paths is None:
        from qgis.PyQt.QtWidgets import QFileDialog
        from qgis.core import QgsSettings
        if model_path is None:
            saved = QgsSettings().value("FazendaClassifier/model_path", "", type=str)
            model_path, _ = QFileDialog.getOpenFileName(
                None, "Selecionar seu modelo Fazenda LeNet", saved, "PyTorch state dict (*.pth)")
        if not model_path:
            return {"status": "cancelada"}
        if image_paths is None:
            image_paths, _ = QFileDialog.getOpenFileNames(
                None, "Selecionar pequenos recortes RGB para teste", "", "Recortes RGB (*.png *.jpg *.jpeg)")
    if not image_paths:
        return {"status": "cancelada"}
    if isinstance(image_paths, (str, Path)):
        image_paths = [image_paths]
    model = FazendaModel(str(model_path))
    case = unittest.TestCase()
    reports = []
    for image_path in image_paths:
        result = model.classify_image(str(image_path))
        probabilities = [result["prob_Araucaria_angustifolia"],
                         result["prob_Cedrela_fissilis"], result["prob_Ocotea_porosa"]]
        case.assertTrue(all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities))
        case.assertAlmostEqual(sum(probabilities), 1, places=5)
        case.assertAlmostEqual(result["confidence"], max(probabilities), places=6)
        expected_status = "abaixo_do_limiar" if result["confidence"] < 0.60 else "aceita"
        case.assertEqual(result["status"], expected_status)
        report = {"recorte": Path(image_path).name, "classe": result["final_class"],
                  "confianca": result["confidence"], "probabilidades": probabilities,
                  "status": result["status"]}
        reports.append(report)
        print(report)
    print(f"CNN real: {len(reports)} recortes processados. Compare com os resultados de referência.")
    return {"status": "concluida", "torch": str(torch.__version__),
            "torchvision": str(torchvision.__version__), "recortes": reports}
