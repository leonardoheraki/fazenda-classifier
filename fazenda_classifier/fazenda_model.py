import os
import torch

from .runtime import require_supported_torch

# Check before importing torchvision or opening any external model weights.
require_supported_torch(torch.__version__)

import torch.nn as nn
from torchvision import transforms
from PIL import Image

import numpy as np


# ============================================================
# ARQUITETURA FAZENDA_LENET — 3 CLASSES
# ============================================================

class LeNet(nn.Module):
    def __init__(self, num_classes=3, dropout_rate=0.30):
        super(LeNet, self).__init__()

        self.conv1 = nn.Conv2d(
            in_channels=3,
            out_channels=64,
            kernel_size=5,
            stride=1,
            padding=2
        )
        self.bn1 = nn.BatchNorm2d(64)

        self.conv2 = nn.Conv2d(
            in_channels=64,
            out_channels=128,
            kernel_size=5,
            stride=1,
            padding=2
        )
        self.bn2 = nn.BatchNorm2d(128)

        self.conv3 = nn.Conv2d(
            in_channels=128,
            out_channels=256,
            kernel_size=5,
            stride=1,
            padding=2
        )
        self.bn3 = nn.BatchNorm2d(256)

        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.dropout = nn.Dropout(dropout_rate)

        # Entrada 128 × 128:
        # 128 → 64 → 32 → 16 após três MaxPool2d
        self.fc1 = nn.Linear(256 * 16 * 16, 512)
        self.fc2 = nn.Linear(512, 128)
        self.fc3 = nn.Linear(128, num_classes)

    def forward(self, x):
        x = self.pool(torch.relu(self.bn1(self.conv1(x))))
        x = self.pool(torch.relu(self.bn2(self.conv2(x))))
        x = self.pool(torch.relu(self.bn3(self.conv3(x))))

        x = x.view(x.size(0), -1)

        x = torch.relu(self.fc1(x))
        x = self.dropout(x)

        x = torch.relu(self.fc2(x))
        x = self.fc3(x)

        return x


# ============================================================
# MODELO FAZENDA CLASSIFIER
# ============================================================

class FazendaModel:
    def __init__(self, model_path, confidence_threshold=0.60):
        """
        Modelo Fazenda_LeNet para classificação de espécies florestais.

        Classes treinadas pela CNN:
        - Araucaria angustifolia
        - Cedrela fissilis
        - Ocotea porosa

        Regra operacional:
        - se confiança < 0.60: espécie não identificada
        - se confiança >= 0.60: aceita a classe prevista pela CNN
        """

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self.confidence_threshold = confidence_threshold

        self.class_labels = [
            "Araucaria angustifolia",
            "Cedrela fissilis",
            "Ocotea porosa"
        ]

        self.unknown_label = "espécie não identificada"

        self.model = self.load_model(model_path)

        self.transform = transforms.Compose([
            transforms.Resize((128, 128)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)
            )
        ])

    # ========================================================
    # CARREGAR MODELO
    # ========================================================

    def load_model(self, model_path):
        """
        Carrega o modelo .pth treinado com 3 classes.
        """

        require_supported_torch(torch.__version__)
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Modelo não encontrado: {model_path}"
            )

        model = LeNet(
            num_classes=len(self.class_labels),
            dropout_rate=0.30
        )

        state_dict = torch.load(
            model_path,
            map_location=self.device,
            weights_only=True
        )

        model.load_state_dict(state_dict)
        model.to(self.device)
        model.eval()

        return model

    # ========================================================
    # CLASSIFICAR IMAGEM
    # ========================================================

    def classify_image(self, image_path):
        """
        Classifica uma imagem individual.

        Retorna um dicionário com:
        - predicted_class: classe prevista originalmente pela CNN;
        - final_class: classe final após aplicação do limiar;
        - confidence: maior probabilidade;
        - threshold: limiar usado;
        - status: aceita ou abaixo_do_limiar;
        - probabilidades por classe.
        """

        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"Imagem não encontrada: {image_path}"
            )

        image = Image.open(image_path).convert("RGB")
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)

        softmax = nn.Softmax(dim=1)

        with torch.no_grad():
            output = self.model(image_tensor)
            probabilities = softmax(output)

        probabilities = probabilities.cpu().numpy()[0]

        predicted_idx = int(np.argmax(probabilities))
        predicted_class = self.class_labels[predicted_idx]
        confidence = float(probabilities[predicted_idx])

        prob_araucaria = float(probabilities[0])
        prob_cedrela = float(probabilities[1])
        prob_ocotea = float(probabilities[2])

        if confidence < self.confidence_threshold:
            final_class = self.unknown_label
            status = "abaixo_do_limiar"
        else:
            final_class = predicted_class
            status = "aceita"

        result = {
            "image_path": image_path,
            "image_name": os.path.basename(image_path),

            "predicted_class": predicted_class,
            "final_class": final_class,

            "confidence": confidence,
            "threshold": self.confidence_threshold,
            "status": status,

            "prob_Araucaria_angustifolia": prob_araucaria,
            "prob_Cedrela_fissilis": prob_cedrela,
            "prob_Ocotea_porosa": prob_ocotea,
        }

        return result

    # ========================================================
    # CLASSIFICAÇÃO SIMPLES
    # ========================================================

    def classify_image_label(self, image_path):
        """
        Retorna apenas a classe final.

        Útil para partes antigas do plugin que esperam apenas uma string.
        """

        result = self.classify_image(image_path)
        return result["final_class"]

    # ========================================================
    # CLASSIFICAÇÃO EM LOTE
    # ========================================================

    def classify_images_batch(self, image_paths):
        """
        Classifica uma lista de imagens.

        Retorna uma lista de dicionários com os resultados completos.
        """

        results = []

        for image_path in image_paths:
            try:
                result = self.classify_image(image_path)
                result["processing_status"] = "processado"
            except Exception as e:
                result = {
                    "image_path": image_path,
                    "image_name": os.path.basename(image_path),

                    "predicted_class": None,
                    "final_class": None,

                    "confidence": None,
                    "threshold": self.confidence_threshold,
                    "status": "erro_processamento",
                    "processing_status": "erro",
                    "error_message": str(e),

                    "prob_Araucaria_angustifolia": None,
                    "prob_Cedrela_fissilis": None,
                    "prob_Ocotea_porosa": None,
                }

            results.append(result)

        return results

    # ========================================================
    # FUNÇÕES ANTIGAS DO PLUGIN — MDS / COPA
    # Mantidas para compatibilidade.
    # ========================================================

    def preprocess_mds(self, mds_array):
        from scipy.ndimage import gaussian_filter
        mds_array = np.nan_to_num(mds_array)
        mds_array = gaussian_filter(mds_array, sigma=1)
        return mds_array

    def detect_local_maxima(self, mds_array, neighborhood_size=3):
        from scipy.ndimage import maximum_filter, label
        local_max = maximum_filter(mds_array, size=neighborhood_size) == mds_array
        labeled_array, num_features = label(local_max)
        return labeled_array, num_features

    def segment_crowns(self, mds_array):
        import cv2
        mds_normalized = cv2.normalize(
            mds_array,
            None,
            0,
            255,
            cv2.NORM_MINMAX
        ).astype(np.uint8)

        _, binary_mask = cv2.threshold(
            mds_normalized,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        kernel = np.ones((3, 3), np.uint8)

        opening = cv2.morphologyEx(
            binary_mask,
            cv2.MORPH_OPEN,
            kernel,
            iterations=2
        )

        sure_bg = cv2.dilate(
            opening,
            kernel,
            iterations=3
        )

        dist_transform = cv2.distanceTransform(
            opening,
            cv2.DIST_L2,
            5
        )

        _, sure_fg = cv2.threshold(
            dist_transform,
            0.7 * dist_transform.max(),
            255,
            0
        )

        sure_fg = np.uint8(sure_fg)
        unknown = cv2.subtract(sure_bg, sure_fg)

        _, markers = cv2.connectedComponents(sure_fg)

        markers = markers + 1
        markers[unknown == 255] = 0

        mds_color = cv2.cvtColor(
            mds_normalized,
            cv2.COLOR_GRAY2BGR
        )

        cv2.watershed(mds_color, markers)

        mds_color[markers == -1] = [0, 0, 255]

        return markers

    def calculate_diameter(self, segment):
        points = np.argwhere(segment > 0)

        if len(points) == 0:
            return 0, 0

        x_coords = points[:, 1]
        y_coords = points[:, 0]

        diameter_x = np.max(x_coords) - np.min(x_coords)
        diameter_y = np.max(y_coords) - np.min(y_coords)

        return diameter_x, diameter_y

    def load_mds_as_array(self, file_path):
        import rasterio
        with rasterio.open(file_path) as src:
            mds_array = src.read(1)

        return mds_array
