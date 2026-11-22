"""Height CSV contracts and atomic exports for inventory measurements.

Raster sampling points must not be interpreted as individual trees.
"""
import csv
import math
import os
import tempfile
import unicodedata
from collections import defaultdict
from numbers import Integral, Real
from pathlib import Path


CSV_SCHEMA_VERSION = "1.0"
CSV_METADATA_FIELDS = ("perfil_csv", "versao_csv", "origem_dados", "unidade_registro")
CONGLOMERATE_FIELDS = (
    "UA", "subparcela_id", "ponto_id", "altura_m", "status", "x_utm", "y_utm",
    "crs_trabalho", "x_mds_max", "y_mds_max", "mds_max", "mdt_mdsmax",
    "largura_janela_m", "comprimento_janela_m", "n_pixels_janela",
    "crs_mds", "crs_mdt", "metodo_altura", *CSV_METADATA_FIELDS,
)


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value).strip())
    return " ".join("".join(c for c in text if not unicodedata.combining(c))
                    .casefold().replace("_", " ").split())


def number(value, name, *, positive=False):
    try:
        result = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name}: informe um número válido.") from error
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name}: o valor deve ser finito" + (" e positivo." if positive else "."))
    return result


def metadata(profile, observation):
    return dict(perfil_csv=profile, versao_csv=CSV_SCHEMA_VERSION,
                origem_dados="FazendaClassifier_QGIS", unidade_registro=observation)


def prepare_conglomerate_rows(records, crs_work, *, require_h5=True):
    """Keep invalid samples for audit, but require five valid heights per UA."""
    if not str(crs_work).strip():
        raise ValueError("A camada de pontos precisa de um SRC de trabalho definido.")
    rows, seen, valid = [], set(), defaultdict(int)
    required = {"UA", "subparcela_id", "ponto_id", "altura_m", "status", "x_utm", "y_utm"}
    for index, source in enumerate(records, 1):
        if not required.issubset(source):
            raise ValueError("Parcelas: faltam campos de pontos de altura da RC4.")
        row = {key: source.get(key) for key in CONGLOMERATE_FIELDS}
        for key in ("UA", "subparcela_id", "ponto_id", "status"):
            row[key] = str(row[key]).strip() if row[key] is not None else ""
            if not row[key]:
                raise ValueError(f"Registro {index}: {key} vazio.")
        identity = tuple(row[key] for key in ("UA", "subparcela_id", "ponto_id"))
        if identity in seen:
            raise ValueError(f"Há pontos repetidos na UA {row['UA']}.")
        seen.add(identity)
        row["x_utm"] = number(row["x_utm"], "x_utm")
        row["y_utm"] = number(row["y_utm"], "y_utm")
        row["crs_trabalho"] = crs_work
        # This schema is the export of RC4 raster samples, not a tree census.
        if normalized(row["status"]) == "valido":
            row["altura_m"] = number(row["altura_m"], "altura_m", positive=True)
            valid[row["UA"]] += 1
        else:
            valid.setdefault(row["UA"], 0)
        row.update(metadata("conglomerados_alturas" if require_h5 else "conglomerados_alturas_diagnostico",
                            "ponto_amostral_raster"))
        rows.append(row)
    if not rows:
        raise ValueError("Não há pontos para exportar.")
    incomplete = [ua for ua, count in valid.items() if count < 5]
    if incomplete and require_h5:
        raise ValueError("O Fazenda ECO exige cinco alturas válidas por UA. Confira: " + ", ".join(incomplete))
    return rows


def _csv_value(value, *, decimal_comma=True):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real):
        if not math.isfinite(value):
            raise ValueError("O CSV contém um número não finito. Confira os valores/NoData.")
        text = repr(float(value))
        return text.replace(".", ",") if decimal_comma else text
    return str(value)


def write_csv(path, fields, rows, *, delimiter=";", decimal_comma=True):
    """Atomic CSV; defaults retain the ECO contract and full numeric precision."""
    fields, rows = tuple(fields), list(rows)
    if not rows or len(set(fields)) != len(fields):
        raise ValueError("A exportação precisa de registros e cabeçalho sem duplicatas.")
    # Normalize/validate before opening even a temporary output.
    values = [{key: _csv_value(row.get(key), decimal_comma=decimal_comma) for key in fields} for row in rows]
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8-sig",
                                         dir=path.parent, prefix=".fazenda_csv_", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(values)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return len(rows)
