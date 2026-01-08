# contexto_helper.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import math
import unicodedata
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

# Archivos esperados
FILE_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"
FILE_TIEMPOS = "indice_cargue_descargue_resumen_mensual.xlsx"
FILE_COMPETITIVIDAD = "competitividad_rutas_2025.xlsx"
FILE_CONFIG_VEH = "CONFIGURACION_VEHICULAR_LIMPIO.xlsx"

_DF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}
_MAP_CACHE: Dict[str, Any] = {}


def _path(name: str) -> Path:
    return BASE_DIR / name


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")


def _norm_col(c: Any) -> str:
    c = str(c).strip().upper()
    c = _strip_accents(c)
    c = c.replace("\u00a0", " ")
    c = " ".join(c.split())
    return c


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_norm_col(c) for c in df.columns]
    return df


def _safe_read_excel(name: str) -> Optional[pd.DataFrame]:
    if name in _DF_CACHE:
        return _DF_CACHE[name]
    p = _path(name)
    if not p.exists():
        _DF_CACHE[name] = None
        return None
    df = pd.read_excel(p)
    df = _normalize_df(df)
    _DF_CACHE[name] = df
    return df


def limpiar_nan_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: limpiar_nan_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpiar_nan_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


# =========================
# Mapeo config vehicular (C3S3 -> 3S3)
# =========================
def _get_mapeo_config() -> Dict[str, str]:
    if "mapeo_config" in _MAP_CACHE:
        return _MAP_CACHE["mapeo_config"]

    df = _safe_read_excel(FILE_CONFIG_VEH)
    if df is None:
        _MAP_CACHE["mapeo_config"] = {}
        return {}

    if "TIPO_VEHICULO" not in df.columns or "CONFIGURACION_ANALISIS" not in df.columns:
        _MAP_CACHE["mapeo_config"] = {}
        return {}

    x = df.copy()
    x["TIPO_VEHICULO"] = x["TIPO_VEHICULO"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
    x["CONFIGURACION_ANALISIS"] = x["CONFIGURACION_ANALISIS"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
    m = dict(zip(x["TIPO_VEHICULO"], x["CONFIGURACION_ANALISIS"]))
    _MAP_CACHE["mapeo_config"] = m
    return m


def traducir_config(config: str) -> str:
    """
    Retorna configuración para análisis/indicadores (sin C).
    """
    v = (config or "").strip().upper().replace(" ", "")
    m = _get_mapeo_config()
    if v in m:
        return str(m[v]).strip().upper().replace(" ", "").replace("C", "")
    # fallback
    return v.replace("C", "")


# =========================
# 1) Valores promedio mercado por llave
# =========================
def obtener_valores_promedio_mercado_por_llave(ruta_config: str) -> List[Dict[str, Any]]:
    df = _safe_read_excel(FILE_VALORES)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_VALORES}"}]

    if "RUTA_CONFIGURACION" not in df.columns:
        return [{"warning": f"Falta columna RUTA_CONFIGURACION en {FILE_VALORES}"}]

    x = df.copy()
    x["RUTA_CONFIGURACION"] = x["RUTA_CONFIGURACION"].astype(str).str.upper().str.strip()

    llave = str(ruta_config).strip().upper()
    dff = x[x["RUTA_CONFIGURACION"] == llave]
    if dff.empty:
        return []

    # Orden por MES si existe
    if "MES" in dff.columns:
        dff = dff.sort_values("MES")

    # Devolver columnas relevantes
    cols = [c for c in ["MES", "VALOR_PROMEDIO_VALPAGADOS", "VALOR_PROMEDIO_MERCADO"] if c in dff.columns]
    if not cols:
        return dff.head(50).to_dict(orient="records")

    return limpiar_nan_json(dff[cols].to_dict(orient="records"))


# =========================
# 2) Indicadores (cargue/descargue)
# =========================
def obtener_indicadores(municipio_dane: Union[int, str], configuracion: str) -> Optional[Dict[str, Any]]:
    df = _safe_read_excel(FILE_TIEMPOS)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_TIEMPOS}"}

    cfg = traducir_config(configuracion)

    needed = {"CODIGO_OBJETIVO", "CONFIGURACION"}
    if not needed.issubset(set(df.columns)):
        return {"warning": f"Faltan columnas en {FILE_TIEMPOS}: {sorted(list(needed - set(df.columns)))}"}

    x = df.copy()
    x["CONFIGURACION"] = x["CONFIGURACION"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)

    filt = (x["CODIGO_OBJETIVO"] == int(municipio_dane)) & (x["CONFIGURACION"] == str(cfg).upper())
    dff = x[filt]
    if dff.empty:
        return None

    fila = dff.iloc[0].to_dict()
    return limpiar_nan_json(fila)


# =========================
# 3) Competitividad por ruta 2025
# =========================
def evaluar_competitividad(origen: Union[int, str], destino: Union[int, str], configuracion: str) -> Optional[Dict[str, Any]]:
    df = _safe_read_excel(FILE_COMPETITIVIDAD)
    if df is None:
        return {"warning": f"Archivo no disponible: {FILE_COMPETITIVIDAD}"}

    cfg = traducir_config(configuracion)

    needed = {"CODIGO_ORIGEN", "CODIGO_DESTINO", "CONFIGURACION"}
    if not needed.issubset(set(df.columns)):
        return {"warning": f"Faltan columnas en {FILE_COMPETITIVIDAD}: {sorted(list(needed - set(df.columns)))}"}

    x = df.copy()
    x["CONFIGURACION"] = x["CONFIGURACION"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)

    dff = x[
        (x["CODIGO_ORIGEN"] == int(origen)) &
        (x["CODIGO_DESTINO"] == int(destino)) &
        (x["CONFIGURACION"] == str(cfg).upper())
    ]
    if dff.empty:
        return None
    return limpiar_nan_json(dff.iloc[0].to_dict())


# =========================
# 4) Meses disponibles (flexible)
# =========================
def obtener_meses_disponibles_indicador(
    df: Optional[pd.DataFrame],
    codigo_objetivo: Union[int, str],
    configuracion: str
) -> List[int]:
    if df is None:
        df = _safe_read_excel(FILE_TIEMPOS)
    if df is None:
        return []

    cfg = traducir_config(configuracion)

    # Detectar columna mes
    col_mes = None
    for cand in ["ANOMES", "AÑOMES", "AÑO MES", "MES"]:
        c = _norm_col(cand)
        if c in df.columns:
            col_mes = c
            break
    if not col_mes:
        return []

    x = df.copy()
    if "CODIGO_OBJETIVO" in x.columns:
        x = x[x["CODIGO_OBJETIVO"] == int(codigo_objetivo)]
    if "CONFIGURACION" in x.columns:
        x["CONFIGURACION"] = x["CONFIGURACION"].astype(str).str.upper().str.strip().str.replace(" ", "", regex=False)
        x = x[x["CONFIGURACION"] == str(cfg).upper()]

    meses = []
    for v in x[col_mes].dropna().unique().tolist():
        try:
            meses.append(int(str(v).strip()))
        except Exception:
            pass
    return sorted(list(set(meses)))
