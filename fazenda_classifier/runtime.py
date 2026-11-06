"""Temporary workspaces independent of UA identifiers."""
import re
import tempfile


def require_ua_id(ua_id):
    if not isinstance(ua_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ua_id) is None:
        raise ValueError("Identificador UA inválido; use até 64 letras, números, '_' ou '-'.")
    return ua_id


def create_species_workspace(ua_id):
    require_ua_id(ua_id)
    # The identifier never contributes to a filesystem path. Keep successful
    # patches for CSV references; no previous directory is recursively removed.
    return tempfile.mkdtemp(prefix="fazenda_species_")
