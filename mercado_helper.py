import pandas as pd
import re
from functools import lru_cache

ARCHIVO_VALORES = "VALORES_CONSOLIDADOS_2025.xlsx"
ARCHIVO_CONFIG = "CONFIGURACION_VEHICULAR_LIMPIO.xlsx"


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
    # deja solo dígitos y punto/coma
    s = re.sub(r"[^\d,.\-]", "", s)
    # casos: "3,259,305" -> "3259305"
    # si hay varios separadores, asumimos coma como miles
    if s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", "")
    # si viene "3.259.305" (raro), quitar puntos
    if s.count(".") > 1 and s.count(",") == 0:
        s = s.replace(".", "")
    # si viene "3259305.00"
    try:
        return float(s)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _cargar_mapeo_config() -> dict:
    """
    Carga mapeo TIPO_VEHICULO (C3S3) -> CONFIGURACION_ANALISIS (3S3)
    """
    df = pd.read_excel(ARCHIVO_CONFIG)
    df.columns = [str(c).strip().upper() for c in df.columns]

    if "TIPO_VEHICULO" not in df.columns or "CONFIGURACION_ANALISIS" not in df.columns:
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
def _cargar_df_valores() -> pd.DataFrame:
    df = pd.read_excel(ARCHIVO_VALORES)
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


def obtener_serie_mercado_rndc(cod_origen: int, cod_destino: int, vehiculo_sicetac: str) -> list[dict]:
    """
    Devuelve serie mensual RNDC para ruta+vehículo:
    [
      {"MES": 202505, "VALOR_PROMEDIO_VALPAGADOS": 3259305.0},
      ...
    ]
    """
    ruta = f"{int(cod_origen)}-{int(cod_destino)}"
    config_analisis = traducir_config_a_analisis(vehiculo_sicetac)

    df = _cargar_df_valores()

    requeridas = {"RUTA_ANALISIS", "CONFIGURACION_ANALISIS", "MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"}
    if not requeridas.issubset(set(df.columns)):
        return []

    sub = df[(df["RUTA_ANALISIS"] == ruta) & (df["CONFIGURACION_ANALISIS"] == config_analisis)]
    if sub.empty:
        return []

    sub = sub.dropna(subset=["MES"]).sort_values("MES")
    out = sub[["MES", "VALOR_PROMEDIO_VALPAGADOS_NUM"]].copy()
    out = out.rename(columns={"VALOR_PROMEDIO_VALPAGADOS_NUM": "VALOR_PROMEDIO_VALPAGADOS"})
    return out.to_dict(orient="records")
