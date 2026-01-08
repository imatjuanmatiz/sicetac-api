# mercado_helper.py
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

logger = logging.getLogger("mercado_helper")

BASE_DIR = Path(__file__).resolve().parent

ARCHIVO_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"
ARCHIVO_CONFIG = "CONFIGURACION_VEHICULAR_LIMPIO.xlsx"


def _path(name: str) -> Path:
    return BASE_DIR / name


def _to_number_currency(x):
    """
    Convierte '$ 3,259,305' -> 3259305.0
    Maneja None/NaN y strings ya numéricos.
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    # deja solo dígitos y punto/coma/-
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
def _cargar_mapeo_config() -> dict:
    """
    Carga mapeo TIPO_VEHICULO (C3S3) -> CONFIGURACION_ANALISIS (3S3)
    """
    p = _path(ARCHIVO_CONFIG)
    if not p.exists():
        logger.warning(f"⚠️ No existe {ARCHIVO_CONFIG}. Se usará fallback quitando 'C'.")
        return {}

    df = pd.read_excel(p)
    df.columns = [str(c).strip().upper() for c in df.columns]

    if "TIPO_VEHICULO" not in df.columns or "CONFIGURACION_ANALISIS" not in df.columns:
        logger.warning("⚠️ CONFIGURACION_VEHICULAR_LIMPIO.xlsx no tiene columnas esperadas.")
        return {}

    df["TIPO_VEHICULO"] = df["TIPO_VEHICULO"].astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)
    df["CONFIGURACION_ANALISIS"] = (
        df["CONFIGURACION_ANALISIS"].astype(str).str.strip().str.upper().str.replace(" ", "", regex=False)
    )
    return dict(zip(df["TIPO_VEHICULO"], df["CONFIGURACION_ANALISIS"]))


def traducir_config_a_analisis(vehiculo_sicetac: str) -> str:
    """
    C3S3 -> 3S3 (según archivo CONFIGURACION_VEHICULAR_LIMPIO.xlsx)
    Fallback: quitar 'C'
    """
    if not vehiculo_sicetac:
        return ""
    v = str(vehiculo_sicetac).strip().upper().replace(" ", "")
    m = _cargar_mapeo_config()
    return m.get(v, v.replace("C", ""))


@lru_cache(maxsize=1)
def _cargar_df_valores_safe() -> pd.DataFrame | None:
    """
    Carga el Excel de valores RNDC. Si falla, retorna None (sin tumbar API).
    """
    try:
        p = _path(ARCHIVO_VALORES)
        if not p.exists():
            logger.warning(f"⚠️ No existe {ARCHIVO_VALORES}. Mercado RNDC deshabilitado.")
            return None

        df = pd.read_excel(p)
        df.columns = [str(c).strip().upper() for c in df.columns]

        # Normalizar columnas clave
        for col in ["RUTA_ANALISIS", "CONFIGURACION_ANALISIS"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.upper()

        if "MES" in df.columns:
            df["MES"] = pd.to_numeric(df["MES"], errors="coerce")

        if "VALOR_PROMEDIO_VALPAGADOS" in df.columns:
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = df["VALOR_PROMEDIO_VALPAGADOS"].apply(_to_number_currency)
        else:
            df["VALOR_PROMEDIO_VALPAGADOS_NUM"] = None

        return df

    except Exception as e:
        logger.warning(f"⚠️ No se pudo cargar mercado RNDC ({ARCHIVO_VALORES}): {e}")
        return None


def obtener_serie_mercado_rndc(cod_origen: int, cod_destino: int, vehiculo_sicetac: str) -> list[dict]:
    """
    Devuelve serie mensual RNDC para ruta+vehículo:
    [
      {"MES": 202505, "VALOR_PROMEDIO_VALPAGADOS": 3259305.0},
      ...
    ]

    Importante:
    - La llave de ruta siempre es con "-" => "COD_ORIGEN-COD_DESTINO"
    - CONFIGURACION_ANALISIS viene sin 'C' (ej: 3S3)
    """
    try:
        df = _cargar_df_valores_safe()
        if df is None or df.empty:
            return []

        requeridas = {"RUTA_ANALISIS", "CONFIGURACION_ANALISIS", "MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"}
        if not requeridas.issubset(set(df.columns)):
            return []

        ruta = f"{int(cod_origen)}-{int(cod_destino)}"  # ✅ siempre "-"
        config_analisis = traducir_config_a_analisis(vehiculo_sicetac)

        sub = df[(df["RUTA_ANALISIS"] == ruta) & (df["CONFIGURACION_ANALYSIS".upper()] == config_analisis)] \
            if "CONFIGURACION_ANALYSIS".upper() in df.columns else df[(df["RUTA_ANALISIS"] == ruta) & (df["CONFIGURACION_ANALISIS"] == config_analisis)]

        if sub.empty:
            return []

        sub = sub.dropna(subset=["MES"]).sort_values("MES")
        out = sub[["MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"]].copy()
        out = out.rename(columns={"VALOR_PROMEDIO_VALPAGADOS_NUM": "VALOR_PROMEDIO_VALPAGADOS"})
        return out.to_dict(orient="records")

    except Exception as e:
        logger.warning(f"⚠️ Mercado RNDC no disponible para {cod_origen}-{cod_destino} ({vehiculo_sicetac}): {e}")
        return []
