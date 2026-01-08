# contexto_helper.py
from __future__ import annotations

import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger("contexto_helper")

BASE_DIR = Path(__file__).resolve().parent

FILE_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"


def _path(name: str) -> Path:
    return BASE_DIR / name


def limpiar_nan_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: limpiar_nan_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpiar_nan_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _to_number_currency(x):
    """
    Convierte '$ 3,259,305' -> 3259305.0
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", "")
    if s.count(".") > 1 and s.count(",") == 0:
        s = s.replace(".", "")
    try:
        return float(s)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _cargar_df_valores_safe() -> Optional[pd.DataFrame]:
    """
    Carga VALORES_CONSOLIDADOS_2025.xlsx una sola vez.
    Si falla, retorna None (sin tumbar API).
    """
    try:
        p = _path(FILE_VALORES)
        if not p.exists():
            logger.warning(f"⚠️ Archivo no disponible: {FILE_VALORES}")
            return None

        df = pd.read_excel(p)
        df.columns = [str(c).strip().upper() for c in df.columns]

        if "RUTA_CONFIGURACION" in df.columns:
            df["RUTA_CONFIGURACION"] = df["RUTA_CONFIGURACION"].astype(str).str.upper().str.strip()

        if "MES" in df.columns:
            df["MES"] = pd.to_numeric(df["MES"], errors="coerce")

        # Asegurar valor numérico consistente
        if "VALOR_PROMEDIO_VALPAGADOS" in df.columns:
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = df["VALOR_PROMEDIO_VALPAGADOS"].apply(_to_number_currency)
        else:
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = None

        return df

    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar {FILE_VALORES}: {e}")
        return None


def obtener_valores_promedio_mercado_por_llave(ruta_config: str) -> List[Dict[str, Any]]:
    """
    Busca por llave exacta en RUTA_CONFIGURACION.
    Regla: llaves SIEMPRE con '-'
    Ej: '11001000-13001000-3S3'

    Devuelve serie:
    [
      {"MES": 202505, "VALOR_PROMEDIO_VALPAGADOS": 3259305.0},
      ...
    ]
    """
    df = _cargar_df_valores_safe()
    if df is None or df.empty:
        return []

    if "RUTA_CONFIGURACION" not in df.columns:
        return []

    llave = str(ruta_config).strip().upper()
    # ✅ No hacemos conversiones '_' <-> '-' porque tú definiste que SIEMPRE es '-'
    dff = df[df["RUTA_CONFIGURACION"] == llave]
    if dff.empty:
        return []

    if "MES" in dff.columns:
        dff = dff.dropna(subset=["MES"]).sort_values("MES")

    out = dff[["MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"]].copy()
    out = out.rename(columns={"VALOR_PROMEDIO_VALPAGADOS_NUM": "VALOR_PROMEDIO_VALPAGADOS"})
    return limpiar_nan_json(out.to_dict(orient="records"))
