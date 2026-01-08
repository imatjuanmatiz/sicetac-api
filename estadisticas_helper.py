# estadisticas_helper.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

# Archivos actuales (según tu repo)
FILE_MERCANCIAS_TOP20_2025 = "consolidacion_anual_mercancia_top20_2025.xlsx"
FILE_RUTAS_2024 = "consolidacion_rutas_2024.xlsx"
FILE_RUTAS_2025 = "consolidacion_rutas_2025.xlsx"
FILE_RUTAS_VEH_2025 = "consolidacion_rutas_vehiculo_2025.xlsx"
FILE_TOP_DESTINOS_ORIGEN_2025 = "red_top20_destinos_origen_2025.xlsx"
FILE_TOP_ORIGENES_DESTINO_2025 = "red_top20_origenes_por_destino_2025.xlsx"

# Cache interno de dataframes (lazy loading)
_DF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _path(name: str) -> Path:
    return BASE_DIR / name


def _safe_read_excel(name: str) -> Optional[pd.DataFrame]:
    """Carga un Excel solo cuando se necesita. Si no existe, retorna None."""
    if name in _DF_CACHE:
        return _DF_CACHE[name]

    p = _path(name)
    if not p.exists():
        _DF_CACHE[name] = None
        return None

    df = pd.read_excel(p)
    # Normalización ligera de columnas
    df.columns = [str(c).strip().upper() for c in df.columns]
    _DF_CACHE[name] = df
    return df


def _route_key_from_codes(cod_origen: Union[str, int], cod_destino: Union[str, int]) -> str:
    return f"{int(cod_origen)}-{int(cod_destino)}"


def _filter_ruta(df: pd.DataFrame, cod_origen: int, cod_destino: int) -> pd.DataFrame:
    """
    Filtra por ruta usando:
    - RUTA == "ORIGEN-DESTINO"
    - o columnas CODIGO_ORIGEN / CODIGO_DESTINO

    IMPORTANTE: no busca sentido inverso (por decisión de diseño).
    """
    cols = set(df.columns)
    clave = _route_key_from_codes(cod_origen, cod_destino)

    if "RUTA" in cols:
        dfr = df[df["RUTA"].astype(str).str.strip() == clave]
        if not dfr.empty:
            return dfr

    if "CODIGO_ORIGEN" in cols and "CODIGO_DESTINO" in cols:
        dfr = df[(df["CODIGO_ORIGEN"] == cod_origen) & (df["CODIGO_DESTINO"] == cod_destino)]
        if not dfr.empty:
            return dfr

    return df.iloc[0:0]


def _norm_vehicle_stats(x: Any) -> str:
    """
    Normaliza config vehicular para estadísticas:
    - upper + strip
    - quita 'C' (ej. C3S3 -> 3S3)
    """
    s = "" if x is None else str(x)
    s = s.strip().upper().replace(" ", "")
    s = s.replace("C", "")
    return s


# =========================================================
# 1) Evolución viajes/toneladas (2024 y 2025, por mes y naturaleza)
# =========================================================
def obtener_evolucion_viajes_y_toneladas(codigo_origen: int, codigo_destino: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {"2024": [], "2025": []}

    df24 = _safe_read_excel(FILE_RUTAS_2024)
    if df24 is not None:
        dfr = _filter_ruta(df24, codigo_origen, codigo_destino)
        if not dfr.empty:
            dfr = dfr.copy()
            if "TOTAL_KILOGRAMOS" in dfr.columns:
                dfr["TONELADAS"] = pd.to_numeric(dfr["TOTAL_KILOGRAMOS"], errors="coerce") / 1000.0
            cols = ["AÑOMES", "NATURALEZACARGA", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "TOTAL_GALONES"]
            cols = [c for c in cols if c in dfr.columns]
            dfr = dfr[cols].sort_values(by=["AÑOMES", "NATURALEZACARGA"], ascending=True)
            out["2024"] = dfr.to_dict(orient="records")
        else:
            out["2024"] = []
    else:
        out["2024"] = [{"warning": f"Archivo no disponible: {FILE_RUTAS_2024}"}]

    df25 = _safe_read_excel(FILE_RUTAS_2025)
    if df25 is not None:
        dfr = _filter_ruta(df25, codigo_origen, codigo_destino)
        if not dfr.empty:
            dfr = dfr.copy()
            if "TOTAL_KILOGRAMOS" in dfr.columns:
                dfr["TONELADAS"] = pd.to_numeric(dfr["TOTAL_KILOGRAMOS"], errors="coerce") / 1000.0
            cols = ["AÑOMES", "NATURALEZACARGA", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "TOTAL_GALONES"]
            cols = [c for c in cols if c in dfr.columns]
            dfr = dfr[cols].sort_values(by=["AÑOMES", "NATURALEZACARGA"], ascending=True)
            out["2025"] = dfr.to_dict(orient="records")
        else:
            out["2025"] = []
    else:
        out["2025"] = [{"warning": f"Archivo no disponible: {FILE_RUTAS_2025}"}]

    return out


# =========================================================
# 2) Top 20 mercancías por ruta (2025)
# =========================================================
def obtener_top_mercancias_ruta(codigo_origen: int, codigo_destino: int, top_n: int = 20) -> List[Dict[str, Any]]:
    df = _safe_read_excel(FILE_MERCANCIAS_TOP20_2025)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_MERCANCIAS_TOP20_2025}"}]

    dfr = _filter_ruta(df, codigo_origen, codigo_destino)
    if dfr.empty:
        return []

    dfr = dfr.copy()

    for c in ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "TONELADAS_RUTA", "PCT_PARTICIPACION"]:
        if c in dfr.columns:
            dfr[c] = pd.to_numeric(dfr[c], errors="coerce")

    if "PCT_PARTICIPACION" in dfr.columns:
        dfr = dfr.sort_values("PCT_PARTICIPACION", ascending=False)
    elif "TONELADAS" in dfr.columns:
        dfr = dfr.sort_values("TONELADAS", ascending=False)
    elif "TOTAL_VIAJES" in dfr.columns:
        dfr = dfr.sort_values("TOTAL_VIAJES", ascending=False)

    cols = ["AÑO", "CODMERCANCIA", "MERCANCIA", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS", "TONELADAS_RUTA", "PCT_PARTICIPACION"]
    cols = [c for c in cols if c in dfr.columns]
    return dfr[cols].head(top_n).to_dict(orient="records")


# =========================================================
# 3) Top 20 destinos por origen (2025)
# =========================================================
def obtener_top_destinos(codigo_origen: int, top_n: int = 20) -> List[Dict[str, Any]]:
    df = _safe_read_excel(FILE_TOP_DESTINOS_ORIGEN_2025)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_TOP_DESTINOS_ORIGEN_2025}"}]

    if "CODIGO_ORIGEN" not in df.columns:
        return [{"warning": f"Columna CODIGO_ORIGEN no existe en {FILE_TOP_DESTINOS_ORIGEN_2025}"}]

    dfr = df[df["CODIGO_ORIGEN"] == int(codigo_origen)].copy()
    if dfr.empty:
        return []

    for c in ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"]:
        if c in dfr.columns:
            dfr[c] = pd.to_numeric(dfr[c], errors="coerce")

    if "TOTAL_VIAJES" in dfr.columns:
        dfr = dfr.sort_values("TOTAL_VIAJES", ascending=False)
    elif "TONELADAS" in dfr.columns:
        dfr = dfr.sort_values("TONELADAS", ascending=False)

    cols = ["AÑO", "CODIGO_ORIGEN", "MUNICIPIO_ORIGEN", "CODIGO_DESTINO", "MUNICIPIO_DESTINO", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"]
    cols = [c for c in cols if c in dfr.columns]
    return dfr[cols].head(top_n).to_dict(orient="records")


# =========================================================
# 4) Top 20 orígenes por destino (2025)
# =========================================================
def obtener_top_origenes(codigo_destino: int, top_n: int = 20) -> List[Dict[str, Any]]:
    df = _safe_read_excel(FILE_TOP_ORIGENES_DESTINO_2025)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_TOP_ORIGENES_DESTINO_2025}"}]

    if "CODIGO_DESTINO" not in df.columns:
        return [{"warning": f"Columna CODIGO_DESTINO no existe en {FILE_TOP_ORIGENES_DESTINO_2025}"}]

    dfr = df[df["CODIGO_DESTINO"] == int(codigo_destino)].copy()
    if dfr.empty:
        return []

    for c in ["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"]:
        if c in dfr.columns:
            dfr[c] = pd.to_numeric(dfr[c], errors="coerce")

    if "TOTAL_VIAJES" in dfr.columns:
        dfr = dfr.sort_values("TOTAL_VIAJES", ascending=False)
    elif "TONELADAS" in dfr.columns:
        dfr = dfr.sort_values("TONELADAS", ascending=False)

    cols = ["AÑO", "CODIGO_DESTINO", "MUNICIPIO_DESTINO", "CODIGO_ORIGEN", "MUNICIPIO_ORIGEN", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"]
    cols = [c for c in cols if c in dfr.columns]
    return dfr[cols].head(top_n).to_dict(orient="records")


# =========================================================
# 5) Distribución de vehículos por ruta (2025)
# =========================================================
def obtener_distribucion_vehiculos_ruta(
    codigo_origen: int,
    codigo_destino: int,
    vehiculo_stats: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Devuelve distribución 2025 por COD_CONFIG_VEHICULO para la ruta.

    Si vehiculo_stats viene, lo normaliza y marca cuál es el consultado (campo: ES_VEHICULO_CONSULTADO).
    """
    df = _safe_read_excel(FILE_RUTAS_VEH_2025)
    if df is None:
        return [{"warning": f"Archivo no disponible: {FILE_RUTAS_VEH_2025}"}]

    dfr = _filter_ruta(df, codigo_origen, codigo_destino)
    if dfr.empty:
        return []

    required = {"COD_CONFIG_VEHICULO", "TOTAL_VIAJES", "TOTAL_KILOGRAMOS"}
    if not required.issubset(set(dfr.columns)):
        faltan = sorted(list(required - set(dfr.columns)))
        return [{"warning": f"Faltan columnas esperadas en {FILE_RUTAS_VEH_2025}: {faltan}"}]

    dfr = dfr.copy()

    # ✅ Normaliza vehículo sin C
    dfr["COD_CONFIG_VEHICULO"] = dfr["COD_CONFIG_VEHICULO"].map(_norm_vehicle_stats)

    dfr["TOTAL_VIAJES"] = pd.to_numeric(dfr["TOTAL_VIAJES"], errors="coerce").fillna(0)
    dfr["TOTAL_KILOGRAMOS"] = pd.to_numeric(dfr["TOTAL_KILOGRAMOS"], errors="coerce").fillna(0)
    dfr["TONELADAS"] = dfr["TOTAL_KILOGRAMOS"] / 1000.0

    agg = (
        dfr.groupby("COD_CONFIG_VEHICULO", as_index=False)[["TOTAL_VIAJES", "TOTAL_KILOGRAMOS", "TONELADAS"]]
        .sum()
    )

    total_viajes = float(agg["TOTAL_VIAJES"].sum()) if not agg.empty else 0.0
    agg["PCT_VIAJES"] = (agg["TOTAL_VIAJES"] / total_viajes * 100.0) if total_viajes > 0 else 0.0

    # Marcar el vehículo consultado (opcional)
    if vehiculo_stats:
        v = _norm_vehicle_stats(vehiculo_stats)
        agg["ES_VEHICULO_CONSULTADO"] = agg["COD_CONFIG_VEHICULO"].astype(str).map(lambda x: x == v)

    agg = agg.sort_values("TOTAL_VIAJES", ascending=False)
    return agg.to_dict(orient="records")
