"""Checks which do not import PyTorch or open a model file."""
import re
import tempfile


MINIMUM_TORCH = (2, 10, 0)


class RuntimeCompatibilityError(ValueError):
    """The optional CNN must not load weights in this environment."""


def require_supported_torch(version):
    text = str(version)
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.post\d+)?(?:\+[A-Za-z0-9._-]+)?", text)
    if match is None or tuple(map(int, match.groups())) < MINIMUM_TORCH:
        raise RuntimeCompatibilityError(
            f"Classificação bloqueada: PyTorch instalado {text}; requer versão estável "
            "2.10.0 ou posterior para carregar pesos .pth. A RC4 não atualiza bibliotecas. "
            "Teste PyTorch e torchvision compatíveis em uma instalação separada do QGIS. "
            "Parcelas, alturas e medidas de copa continuam disponíveis sem a CNN."
        )


def require_ua_id(ua_id):
    if not isinstance(ua_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ua_id) is None:
        raise ValueError("Identificador UA inválido; use até 64 letras, números, '_' ou '-'.")
    return ua_id


def create_species_workspace(ua_id):
    require_ua_id(ua_id)
    # The identifier never contributes to a filesystem path. Keep successful
    # patches for CSV references; no previous directory is recursively removed.
    return tempfile.mkdtemp(prefix="fazenda_species_")
