"""CSV contracts for Fazenda ECO rev7; no QGIS, CNN or carbon calculations.

One row is a raster sample, a delimited tree, or an RGB classification patch.
Those observation units must never be interchanged to manufacture predictors.
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
TREE_ECO_FIELDS = (
    "arvore_id", "UA", "especie", "area_copa_m2", "altura_m",
    "diametro_copa_max_m", "diametro_copa_equivalente_m", "x_arvore", "y_arvore",
    "crs_trabalho", "predicted_class", "final_class", "confidence", "threshold",
    "status", "prob_Araucaria_angustifolia", "prob_Cedrela_fissilis",
    "prob_Ocotea_porosa", "crs_mds", "crs_mdt", "crs_rgb", "mds_no_ponto",
    "mdt_no_ponto", "status_altura", "metodo_altura", "metodo_diametro",
    "metodo_area", "metodo_classificacao", "patch_path", "crown_coords",
    "detalhe_classificacao", "especie_origem", "calculo_disponivel",
    *CSV_METADATA_FIELDS,
)
SPECIES_DIAGNOSTIC_FIELDS = (
    "UA", "amostra_id", "linha", "coluna", "x_utm", "y_utm", "grid_size_m",
    "patch_size_m", "predicted_class", "final_class", "confidence", "threshold",
    "status", "prob_Araucaria_angustifolia", "prob_Cedrela_fissilis",
    "prob_Ocotea_porosa", "patch_path", "crs_trabalho", "crs_rgb",
    *CSV_METADATA_FIELDS,
)
SPECIES_NAMES = {name: name for name in (
    "Araucaria angustifolia", "Cedrela fissilis", "Ocotea porosa",
)}


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


def prepare_tree_rows(records):
    rows, seen = [], set()
    for record in records:
        source = record.as_csv_row()  # Blocks pending inference/incomplete crown.
        if source["status"] != "aceita" or source["final_class"] not in SPECIES_NAMES:
            raise ValueError(f"Fazenda ECO: a árvore {record.arvore_id} precisa de uma classificação aceita de "
                             "araucária, cedro ou imbuia. Para dados sem classificação aceita, "
                             "escolha o relatório completo, que preserva o diagnóstico.")
        tree_id = str(record.arvore_id).strip()
        ua = str(record.ua).strip()
        if not tree_id:
            raise ValueError("Informe o identificador da árvore antes de exportar.")
        if (ua, tree_id) in seen:
            raise ValueError("Há identificadores de árvore repetidos na mesma UA.")
        seen.add((ua, tree_id))
        row = {key: source.get(key) for key in TREE_ECO_FIELDS}
        area = number(source["area_copa"], "Área de copa (m²)", positive=True)
        height = source["altura"]
        if height is not None:
            height = number(height, "Altura (m)", positive=True)
        for key in ("confidence", "threshold", "prob_Araucaria_angustifolia",
                    "prob_Cedrela_fissilis", "prob_Ocotea_porosa"):
            if row[key] is not None:
                row[key] = number(row[key], key)
                if not 0 <= row[key] <= 1:
                    raise ValueError(f"{key} deve estar entre 0 e 1, sem conversão para porcentagem.")
        if row["confidence"] is None or row["threshold"] is None or row["confidence"] < row["threshold"]:
            raise ValueError("A classificação aceita precisa manter confiança e limiar coerentes.")
        row.update(arvore_id=tree_id, UA=ua, especie=source["final_class"],
                   area_copa_m2=area, altura_m=height,
                   diametro_copa_max_m=number(source["diametro_copa"], "Diâmetro máximo (m)", positive=True),
                   diametro_copa_equivalente_m=2 * math.sqrt(area / math.pi),
                   especie_origem="CNN_aceita", calculo_disponivel="DAP_e_AGC" if height is not None else "somente_DAP")
        row.update(metadata("arvore_copa", "arvore_individual_delimitada"))
        rows.append(row)
    if not rows:
        raise ValueError("Não há árvores para exportar.")
    return rows


def prepare_species_diagnostic_rows(records, crs_work):
    names = {"predicted_class": "pred_class", "prob_Araucaria_angustifolia": "prob_AA",
             "prob_Cedrela_fissilis": "prob_CF", "prob_Ocotea_porosa": "prob_OP"}
    rows = []
    for source in records:
        row = {key: source.get(names.get(key, key)) for key in SPECIES_DIAGNOSTIC_FIELDS}
        row["crs_trabalho"] = crs_work
        row.update(metadata("classificacao_grade_diagnostico", "recorte_RGB_grade_nao_e_arvore"))
        rows.append(row)
    if not rows:
        raise ValueError("Não há classificações para exportar.")
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
