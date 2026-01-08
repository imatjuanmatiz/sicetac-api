# mercado_helper.py
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger("mercado_helper")
BASE_DIR = Path(__file__).resolve().parent

ARCHIVO_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"


def _path(name: str) -> Path:
    return BASE_DIR / name


def _to_number_currency(x: Any) -> float | None:
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

    # "3,259,305" -> "3259305"
    if s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", "")
    # "3.259.305" -> "3259305"
    if s.count(".") > 1 and s.count(",") == 0:
        s = s.replace(".", "")

    try:
        return float(s)
    except Exception:
        return None


@lru_cache(maxsize=1)
def cargar_df_valores() -> pd.DataFrame | None:
    """
    Carga el excel SOLO cuando se use.
    Si falla, retorna None (sin tumbar API).
    """
    try:
        p = _path(ARCHIVO_VALORES)
        if not p.exists():
            logger.warning(f"⚠️ No existe {ARCHIVO_VALORES}. Mercado deshabilitado.")
            return None

        df = pd.read_excel(p)
        df.columns = [str(c).strip().upper() for c in df.columns]

        # Necesitamos: RUTA_CONFIGURACION, MES, VALOR_PROMEDIO_VALPAGADOS (o similar)
        if "RUTA_CONFIGURACION" in df.columns:
            df["RUTA_CONFIGURACION"] = df["RUTA_CONFIGURACION"].astype(str).str.strip().str.upper()

        if "MES" in df.columns:
            df["MES"] = pd.to_numeric(df["MES"], errors="coerce")

        if "VALOR_PROMEDIO_VALPAGADOS" in df.columns:
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = df["VALOR_PROMEDIO_VALPAGADOS"].apply(_to_number_currency)
        else:
            # si no existe, dejamos columna numérica vacía
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = None

        return df

    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar {ARCHIVO_VALORES}: {e}")
        return None


def obtener_historico_por_llave(ruta_config: str) -> list[dict]:
    """
    ruta_config: 'COD_ORIGEN-COD_DESTINO-CONFIG'  (✅ SIEMPRE con '-')
    Ej: '11001000-13001000-3S3'

    Devuelve lista ordenada por MES:
    [{"MES": 202505, "VALOR_PROMEDIO_VALPAGADOS": 3259305.0}, ...]
    """
    try:
        df = cargar_df_valores()
        if df is None or df.empty:
            return []

        if "RUTA_CONFIGURACION" not in df.columns or "MES" not in df.columns or "VALOR_PROMEDIO_VALPAGADOS_NUM" not in df.columns:
            return []

        llave = str(ruta_config).strip().upper()
        sub = df[df["RUTA_CONFIGURACION"] == llave].copy()
        if sub.empty:
            return []

        sub = sub.dropna(subset=["MES"]).sort_values("MES")
        out = sub[["MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"]].rename(
            columns={"VALOR_PROMEDIO_VALPAGADOS_NUM": "VALOR_PROMEDIO_VALPAGADOS"}
        )
        return out.to_dict(orient="records")

    except Exception as e:
        logger.warning(f"⚠️ Mercado no disponible para llave {ruta_config}: {e}")
        return []


def obtener_ultimo_por_llave(ruta_config: str) -> dict | None:
    """
    Devuelve el último registro del histórico (mayor MES).
    """
    hist = obtener_historico_por_llave(ruta_config)
    if not hist:
        return None
    return hist[-1]
